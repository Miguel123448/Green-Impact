from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import secrets
import string
import time
import uuid
from pathlib import Path
from typing import Any

import websockets

from .common import COLORS, COLOR_LABELS, Player, Question, Room
from .rules import (
    CREDITS_BY_DIFFICULTY,
    HELP_COST,
    INITIAL_CREDITS,
    QUESTION_TIME_LIMIT,
    RESEARCH_BONUS_SECONDS,
    LUCK_EVENTS,
    LUCK_POSITIONS,
    difficulty_for_position,
    max_position_for_mode,
    track_label,
)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

ROOMS: dict[str, Room] = {}
SOCKETS_BY_ROOM: dict[str, set[Any]] = {}
ROOM_BY_SOCKET: dict[Any, str] = {}
PLAYER_BY_SOCKET: dict[Any, str] = {}
QUESTIONS: dict[str, list[Question]] = {}


def load_questions() -> dict[str, list[Question]]:
    mapping = {
        "easy": DATA_DIR / "questions_easy.json",
        "medium": DATA_DIR / "questions_medium.json",
        "hard": DATA_DIR / "questions_hard.json",
    }
    result: dict[str, list[Question]] = {}
    for difficulty, path in mapping.items():
        with path.open("r", encoding="utf-8") as f:
            rows = json.load(f)
        result[difficulty] = [Question(**row) for row in rows]
    return result


def room_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(4))
        if code not in ROOMS:
            return code


def now() -> float:
    return time.time()


async def send(ws: Any, payload: dict[str, Any]) -> None:
    await ws.send(json.dumps(payload, ensure_ascii=False))


async def broadcast(room: Room, event: str | None = None, reveal_answer: bool = False) -> None:
    if event:
        room.event_log.append(event)
    payload = {
        "type": "state",
        "you": None,
        "server_ts": now(),
        "room": room.public(reveal_answer=reveal_answer),
    }
    sockets = list(SOCKETS_BY_ROOM.get(room.code, set()))
    for ws in sockets:
        if getattr(ws, "closed", False):
            continue
        payload["you"] = PLAYER_BY_SOCKET.get(ws)
        try:
            await send(ws, payload)
        except Exception:
            pass


def active_player_ids(room: Room) -> list[str]:
    return [p.id for p in room.ordered_players() if not p.eliminated and not p.stopped]


def make_ranking(room: Room) -> list[dict[str, Any]]:
    players = room.ordered_players()
    ranked = sorted(players, key=lambda p: (p.position, p.credits, not p.eliminated), reverse=True)
    return [
        {
            "name": p.name,
            "color": p.color,
            "position": p.position,
            "display_position": track_label(p.position, room.game_mode),
            "credits": p.credits,
            "eliminated": p.eliminated,
            "stopped": p.stopped,
        }
        for p in ranked
    ]


async def end_game(room: Room, reason: str) -> None:
    room.status = "ended"
    room.current_question = None
    room.deadline_ts = None
    room.current_player_id = None
    room.turn_phase = "idle"
    room.pending_question_difficulty = None
    room.last_roll = None
    room.ranking = make_ranking(room)
    await broadcast(room, f"Fim de jogo: {reason}")


async def next_turn(room: Room) -> None:
    if room.status != "playing":
        return

    active = active_player_ids(room)
    if not active:
        await end_game(room, "todos os jogadores pararam ou foram eliminados")
        return

    players = room.ordered_players()
    attempts = 0
    while attempts < len(players):
        room.current_turn_index = (room.current_turn_index + 1) % len(players)
        player = players[room.current_turn_index]
        if player.id in active:
            break
        attempts += 1
    else:
        await end_game(room, "nenhum jogador ativo")
        return

    room.current_player_id = player.id
    room.current_question = None
    room.deadline_ts = None
    room.help_used_this_turn = False
    room.pending_question_difficulty = None
    room.special_event = None
    room.turn_result = None
    room.last_roll = None

    if room.game_mode == "classic":
        if player.position < max_position_for_mode(room.game_mode):
            player.position += 1
        difficulty = difficulty_for_position(player.position, room.game_mode)
        room.pending_question_difficulty = difficulty
        room.turn_phase = "awaiting_question"
        await broadcast(room, f"Vez de {player.name}. Casa {track_label(player.position, room.game_mode)}. Clique em iniciar pergunta quando estiver pronto.")
    else:
        room.turn_phase = "awaiting_roll"
        await broadcast(room, f"Vez de {player.name}. Jogue o dado para avançar no tabuleiro.")


async def after_landing(room: Room, player: Player) -> None:
    max_pos = max_position_for_mode(room.game_mode)
    if player.position >= max_pos:
        room.pending_question_difficulty = difficulty_for_position(player.position, room.game_mode)
        room.turn_phase = "awaiting_question"
        await broadcast(room, f"{player.name} chegou ao {track_label(player.position, room.game_mode)}. Responda a pergunta final para vencer.")
        return

    if room.game_mode != "classic" and player.position in LUCK_POSITIONS:
        message, delta = random.choice(LUCK_EVENTS)
        old = player.credits
        player.credits = max(0, player.credits + delta)
        applied_delta = player.credits - old
        room.special_event = f"{message} ({old} → {player.credits} créditos)"
        room.turn_result = {
            "kind": "luck_gain" if applied_delta >= 0 else "luck_loss",
            "title": "Sorte: créditos recebidos" if applied_delta >= 0 else "Revés: créditos perdidos",
            "message": message,
            "player_name": player.name,
            "old_credits": old,
            "new_credits": player.credits,
            "credit_delta": applied_delta,
            "old_position": player.position,
            "new_position": player.position,
            "position_label": track_label(player.position, room.game_mode),
            "eliminated": False,
            "stopped": False,
        }
        room.turn_phase = "luck_result"
        await broadcast(room, f"{player.name} caiu em uma casa de sorte/revés. {room.special_event}")
        return

    difficulty = difficulty_for_position(player.position, room.game_mode)
    room.pending_question_difficulty = difficulty
    room.turn_phase = "awaiting_question"
    await broadcast(room, f"{player.name} caiu na casa {track_label(player.position, room.game_mode)}. Clique em iniciar pergunta quando estiver pronto.")


async def handle_roll(ws: Any, data: dict[str, Any] | None = None) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    player = get_current_player_for_ws(room, player_id)
    if not player:
        await send(ws, {"type": "error", "message": "Não é sua vez."})
        return
    if room.turn_phase != "awaiting_roll":
        await send(ws, {"type": "error", "message": "O dado só pode ser jogado no início do turno."})
        return
    # O cliente anima o dado, revela o número por 1 segundo e então
    # envia o valor sorteado. Se o valor não vier, o servidor sorteia.
    try:
        roll = int((data or {}).get("roll", 0))
    except Exception:
        roll = 0
    if roll < 1 or roll > 6:
        roll = random.randint(1, 6)
    max_pos = max_position_for_mode(room.game_mode)
    player.position = min(max_pos, player.position + roll)
    room.last_roll = roll
    await broadcast(room, f"{player.name} tirou {roll} no dado e avançou para {track_label(player.position, room.game_mode)}.")
    await after_landing(room, player)


async def handle_continue(ws: Any) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    player = get_current_player_for_ws(room, player_id)
    if not player or room.turn_phase not in {"luck_result", "turn_result"}:
        return
    room.turn_phase = "idle"
    room.special_event = None
    room.turn_result = None
    await next_turn(room)


async def start_question(room: Room, player: Player) -> None:
    if room.status != "playing":
        return
    if room.turn_phase != "awaiting_question" or room.current_player_id != player.id:
        return

    difficulty = room.pending_question_difficulty or difficulty_for_position(player.position, room.game_mode)
    question = random.choice(QUESTIONS[difficulty])
    room.current_question = Question(
        id=question.id,
        difficulty=question.difficulty,
        prompt=question.prompt,
        options=list(question.options),
        answer_index=question.answer_index,
        source=question.source,
    )
    room.deadline_ts = now() + QUESTION_TIME_LIMIT
    room.help_used_this_turn = False
    room.turn_phase = "question"
    await broadcast(room, f"Pergunta iniciada para {player.name}. Tempo: {QUESTION_TIME_LIMIT}s.")


async def apply_wrong_answer(room: Room, player: Player, reason: str = "resposta incorreta") -> None:
    question = room.current_question
    correct_answer = ""
    if question and 0 <= question.answer_index < len(question.options):
        correct_answer = question.options[question.answer_index]

    old_credits = player.credits
    old_position = player.position
    timed_out = reason == "tempo esgotado"

    if player.reset_used:
        player.eliminated = True
        player.credits = 0
        title = "Tempo esgotado - jogador eliminado" if timed_out else "Resposta incorreta - jogador eliminado"
        event = f"{player.name} errou novamente e foi eliminado ({reason}). Saldo: {player.credits} créditos."
    else:
        player.reset_used = True
        player.position = 0
        player.credits = 0
        title = "Tempo esgotado - retorno ao início" if timed_out else "Resposta incorreta - retorno ao início"
        event = f"{player.name} errou e voltou ao início, perdendo todos os créditos ({reason}). Saldo: {player.credits} créditos."

    room.current_question = None
    room.deadline_ts = None
    room.turn_phase = "turn_result"
    room.pending_question_difficulty = None
    room.special_event = event
    room.turn_result = {
        "kind": "timeout" if timed_out else "incorrect",
        "title": title,
        "message": event,
        "player_name": player.name,
        "old_credits": old_credits,
        "new_credits": player.credits,
        "credit_delta": player.credits - old_credits,
        "old_position": old_position,
        "new_position": player.position,
        "old_position_label": track_label(old_position, room.game_mode),
        "new_position_label": track_label(player.position, room.game_mode),
        "correct_answer": correct_answer,
        "eliminated": player.eliminated,
        "stopped": player.stopped,
    }
    await broadcast(room, event, reveal_answer=True)


async def expire_if_needed(room: Room) -> bool:
    if room.status != "playing" or not room.current_question or not room.deadline_ts:
        return False
    if now() < room.deadline_ts:
        return False
    player = room.players.get(room.current_player_id or "")
    if not player:
        return False
    await apply_wrong_answer(room, player, "tempo esgotado")
    return True


async def deadline_monitor(interval: float = 0.25) -> None:
    """Expira perguntas no servidor, mesmo se o cliente estiver em segundo plano.

    Antes, o servidor dependia de o aparelho enviar uma mensagem de timeout.
    Isso podia deixar a tela parada quando o Android suspendia o app ou quando
    o contador mostrava 0 antes do instante real do prazo.
    """
    while True:
        for room in list(ROOMS.values()):
            try:
                await expire_if_needed(room)
            except Exception as exc:
                print(f"Falha ao verificar tempo da sala {room.code}: {exc}")
        await asyncio.sleep(interval)


def get_current_player(room: Room, player_id: str) -> Player | None:
    if room.current_player_id != player_id:
        return None
    return room.players.get(player_id)


def get_current_player_for_ws(room: Room, player_id: str) -> Player | None:
    # No multijogador local, um único dispositivo controla todos os jogadores.
    if room.local_multiplayer and player_id == room.host_id and room.current_player_id:
        return room.players.get(room.current_player_id)
    return get_current_player(room, player_id)


async def handle_create(ws: Any, data: dict[str, Any]) -> None:
    name = str(data.get("name") or "Jogador").strip()[:20] or "Jogador"
    mode = str(data.get("game_mode") or "dice_board")
    if mode not in {"classic", "dice_board"}:
        mode = "dice_board"
    code = room_code()
    player_id = str(uuid.uuid4())
    player = Player(id=player_id, name=name, credits=INITIAL_CREDITS, is_host=True)
    room = Room(code=code, host_id=player_id, players={player_id: player}, game_mode=mode)
    ROOMS[code] = room
    SOCKETS_BY_ROOM[code] = {ws}
    ROOM_BY_SOCKET[ws] = code
    PLAYER_BY_SOCKET[ws] = player_id
    await send(ws, {"type": "created", "room_code": code, "player_id": player_id})
    await broadcast(room, f"Sala {code} criada por {name}.")


async def handle_create_local(ws: Any, data: dict[str, Any]) -> None:
    count = int(data.get("count") or 2)
    count = max(2, min(4, count))
    raw_names = data.get("names") or []
    if not isinstance(raw_names, list):
        raw_names = []
    base_name = str(data.get("name") or "Jogador").strip()[:16] or "Jogador"
    names: list[str] = []
    for i in range(count):
        value = ""
        if i < len(raw_names):
            value = str(raw_names[i] or "").strip()[:20]
        names.append(value or f"Jogador {i + 1}")
    code = room_code()
    host_id = str(uuid.uuid4())
    players: dict[str, Player] = {}
    for i in range(count):
        pid = host_id if i == 0 else str(uuid.uuid4())
        players[pid] = Player(
            id=pid,
            name=names[i],
            color=COLORS[i],
            credits=INITIAL_CREDITS,
            is_host=(i == 0),
        )
    room = Room(code=code, host_id=host_id, players=players, game_mode="dice_board", local_multiplayer=True)
    ROOMS[code] = room
    SOCKETS_BY_ROOM[code] = {ws}
    ROOM_BY_SOCKET[ws] = code
    PLAYER_BY_SOCKET[ws] = host_id
    await send(ws, {"type": "created", "room_code": code, "player_id": host_id})
    await broadcast(room, f"Multijogador local criado com {count} jogadores.")
    room.status = "playing"
    room.current_turn_index = -1
    await broadcast(room, "Partida local iniciada.")
    await next_turn(room)


async def handle_join(ws: Any, data: dict[str, Any]) -> None:
    code = str(data.get("room") or "").strip().upper()
    name = str(data.get("name") or "Jogador").strip()[:20] or "Jogador"
    room = ROOMS.get(code)
    if not room:
        await send(ws, {"type": "error", "message": "Sala não encontrada."})
        return
    if room.status != "waiting":
        await send(ws, {"type": "error", "message": "A partida já começou."})
        return
    if len(room.players) >= 4:
        await send(ws, {"type": "error", "message": "A sala já tem 4 jogadores."})
        return

    player_id = str(uuid.uuid4())
    room.players[player_id] = Player(id=player_id, name=name, credits=INITIAL_CREDITS)
    SOCKETS_BY_ROOM.setdefault(code, set()).add(ws)
    ROOM_BY_SOCKET[ws] = code
    PLAYER_BY_SOCKET[ws] = player_id
    await send(ws, {"type": "joined", "room_code": code, "player_id": player_id})
    await broadcast(room, f"{name} entrou na sala.")


async def handle_choose_color(ws: Any, data: dict[str, Any]) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    if room.local_multiplayer:
        return
    if room.status != "waiting":
        await send(ws, {"type": "error", "message": "Não é possível trocar cor depois que o jogo começa."})
        return
    color = str(data.get("color") or "").lower()
    if color not in COLORS:
        await send(ws, {"type": "error", "message": "Cor inválida."})
        return
    for p in room.players.values():
        if p.id != player_id and p.color == color:
            await send(ws, {"type": "error", "message": "Essa cor já foi escolhida."})
            return
    room.players[player_id].color = color
    await broadcast(room, f"{room.players[player_id].name} escolheu {COLOR_LABELS[color]}.")


async def handle_start(ws: Any) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    if room.status != "waiting":
        return
    if player_id != room.host_id:
        await send(ws, {"type": "error", "message": "Apenas o criador da sala pode iniciar."})
        return
    if len(room.players) < 1:
        await send(ws, {"type": "error", "message": "É necessário pelo menos 1 jogador para testar."})
        return
    missing = [p.name for p in room.players.values() if not p.color]
    if missing:
        await send(ws, {"type": "error", "message": "Todos precisam escolher uma cor antes de iniciar."})
        return
    room.status = "playing"
    room.current_turn_index = -1
    for p in room.players.values():
        p.position = 0
        p.credits = INITIAL_CREDITS
        p.reset_used = False
        p.eliminated = False
        p.stopped = False
    await broadcast(room, "Partida iniciada.")
    await next_turn(room)


async def handle_answer(ws: Any, data: dict[str, Any]) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    if await expire_if_needed(room):
        return
    player = get_current_player_for_ws(room, player_id)
    if not player or not room.current_question:
        await send(ws, {"type": "error", "message": "Não é sua vez."})
        return
    answer_index = int(data.get("answer_index", -1))
    question = room.current_question
    if answer_index == question.answer_index:
        reward = CREDITS_BY_DIFFICULTY[question.difficulty]
        old_credits = player.credits
        correct_answer = question.options[question.answer_index] if 0 <= question.answer_index < len(question.options) else ""
        player.credits += reward
        event = f"{player.name} acertou. Ganhou {reward} créditos de carbono. Saldo atual: {player.credits} créditos."
        room.current_question = None
        room.deadline_ts = None
        room.turn_phase = "turn_result"
        room.pending_question_difficulty = None
        room.special_event = event
        room.turn_result = {
            "kind": "correct",
            "title": "Resposta correta",
            "message": event,
            "player_name": player.name,
            "old_credits": old_credits,
            "new_credits": player.credits,
            "credit_delta": reward,
            "old_position": player.position,
            "new_position": player.position,
            "position_label": track_label(player.position, room.game_mode),
            "correct_answer": correct_answer,
            "eliminated": False,
            "stopped": False,
        }
        await broadcast(room, event, reveal_answer=True)
        if player.position >= max_position_for_mode(room.game_mode):
            await end_game(room, f"{player.name} completou o percurso com {player.credits} créditos")
            return
    else:
        await apply_wrong_answer(room, player)


async def handle_stop(ws: Any) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    if await expire_if_needed(room):
        return
    player = get_current_player_for_ws(room, player_id)
    if not player or not room.current_question:
        await send(ws, {"type": "error", "message": "Inicie a pergunta antes de decidir parar."})
        return
    player.stopped = True
    old = player.credits
    old_position = player.position
    player.credits = player.credits // 2
    event = f"{player.name} decidiu parar. Créditos: {old} → {player.credits}. Ele não participa das próximas rodadas."
    room.current_question = None
    room.deadline_ts = None
    room.turn_phase = "turn_result"
    room.pending_question_difficulty = None
    room.special_event = event
    room.turn_result = {
        "kind": "stopped",
        "title": "Jogador decidiu parar",
        "message": event,
        "player_name": player.name,
        "old_credits": old,
        "new_credits": player.credits,
        "credit_delta": player.credits - old,
        "old_position": old_position,
        "new_position": player.position,
        "position_label": track_label(player.position, room.game_mode),
        "eliminated": False,
        "stopped": True,
    }
    await broadcast(room, event)


async def handle_timeout(ws: Any) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    if get_current_player_for_ws(room, player_id):
        await expire_if_needed(room)


async def handle_begin_question(ws: Any) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    player = get_current_player_for_ws(room, player_id)
    if not player:
        await send(ws, {"type": "error", "message": "Não é sua vez."})
        return
    if room.turn_phase != "awaiting_question":
        await send(ws, {"type": "error", "message": "A pergunta já foi iniciada ou a rodada ainda não está pronta."})
        return
    await start_question(room, player)


async def handle_help(ws: Any, data: dict[str, Any]) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    if await expire_if_needed(room):
        return
    player = get_current_player_for_ws(room, player_id)
    if not player or not room.current_question:
        await send(ws, {"type": "error", "message": "Não é sua vez."})
        return
    if room.help_used_this_turn:
        await send(ws, {"type": "error", "message": "Você já usou uma ajuda nesta rodada."})
        return
    if player.credits < HELP_COST:
        await send(ws, {"type": "error", "message": "Créditos insuficientes para comprar ajuda."})
        return

    help_type = str(data.get("help") or "")
    player.credits -= HELP_COST
    room.help_used_this_turn = True

    if help_type == "eliminate2":
        wrong = [i for i in range(len(room.current_question.options)) if i != room.current_question.answer_index]
        random.shuffle(wrong)
        eliminated = wrong[:2]
        room.current_question.eliminated_options = sorted(set(room.current_question.eliminated_options + eliminated))
        await broadcast(room, f"{player.name} comprou ajuda: eliminar 2 alternativas. Custo: {HELP_COST} créditos. Saldo: {player.credits} créditos.")
    elif help_type == "research":
        if room.deadline_ts:
            room.deadline_ts += RESEARCH_BONUS_SECONDS
        await broadcast(room, f"{player.name} comprou pesquisa na internet (+{RESEARCH_BONUS_SECONDS}s). Custo: {HELP_COST} créditos. Saldo: {player.credits} créditos.")
    elif help_type == "expert":
        tip = "Dica do especialista: pense no conceito central da ODS relacionada à pergunta e elimine opções que aumentam desigualdade, poluição ou desperdício."
        await send(ws, {"type": "private_tip", "message": tip})
        await broadcast(room, f"{player.name} comprou ajuda do especialista. Custo: {HELP_COST} créditos. Saldo: {player.credits} créditos.")
    elif help_type == "skip":
        question = room.current_question
        correct_answer = question.options[question.answer_index] if 0 <= question.answer_index < len(question.options) else ""
        event = f"{player.name} usou Pular pergunta. Custo: {HELP_COST} créditos. Saldo atual: {player.credits} créditos."
        room.current_question = None
        room.deadline_ts = None
        room.turn_phase = "turn_result"
        room.pending_question_difficulty = None
        room.special_event = event
        room.turn_result = {
            "kind": "skipped",
            "title": "Pergunta pulada",
            "message": event,
            "player_name": player.name,
            "old_credits": player.credits + HELP_COST,
            "new_credits": player.credits,
            "credit_delta": -HELP_COST,
            "old_position": player.position,
            "new_position": player.position,
            "position_label": track_label(player.position, room.game_mode),
            "correct_answer": correct_answer,
            "eliminated": False,
            "stopped": False,
        }
        await broadcast(room, event)
    else:
        player.credits += HELP_COST
        room.help_used_this_turn = False
        await send(ws, {"type": "error", "message": "Ajuda inválida."})


async def handler(ws: Any, path: str | None = None) -> None:
    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await send(ws, {"type": "error", "message": "Mensagem inválida."})
                continue
            msg_type = data.get("type")
            if msg_type == "create":
                await handle_create(ws, data)
            elif msg_type == "create_local":
                await handle_create_local(ws, data)
            elif msg_type == "join":
                await handle_join(ws, data)
            elif msg_type == "choose_color":
                await handle_choose_color(ws, data)
            elif msg_type == "start":
                await handle_start(ws)
            elif msg_type == "roll":
                await handle_roll(ws, data)
            elif msg_type == "continue":
                await handle_continue(ws)
            elif msg_type == "begin_question":
                await handle_begin_question(ws)
            elif msg_type == "answer":
                await handle_answer(ws, data)
            elif msg_type == "stop":
                await handle_stop(ws)
            elif msg_type == "help":
                await handle_help(ws, data)
            elif msg_type == "timeout":
                await handle_timeout(ws)
            elif msg_type == "ping":
                await send(ws, {"type": "pong"})
            else:
                await send(ws, {"type": "error", "message": f"Tipo de mensagem desconhecido: {msg_type}"})
    finally:
        code = ROOM_BY_SOCKET.pop(ws, None)
        player_id = PLAYER_BY_SOCKET.pop(ws, None)
        if code and code in SOCKETS_BY_ROOM:
            SOCKETS_BY_ROOM[code].discard(ws)
        if code and player_id and code in ROOMS:
            room = ROOMS[code]
            if player_id in room.players:
                room.players[player_id].connected = False
                await broadcast(room, f"{room.players[player_id].name} desconectou.")


async def main() -> None:
    global QUESTIONS
    parser = argparse.ArgumentParser(description="Servidor online do Green Impact")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    QUESTIONS = load_questions()
    monitor_task = asyncio.create_task(deadline_monitor())
    try:
        async with websockets.serve(handler, args.host, args.port):
            print(f"Servidor Green Impact rodando em ws://{args.host}:{args.port}")
            print("Pressione Ctrl+C para encerrar.")
            await asyncio.Future()
    finally:
        monitor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor_task


if __name__ == "__main__":
    asyncio.run(main())
