from __future__ import annotations

import argparse
import asyncio
import json
import random
import secrets
import string
import time
import uuid
from pathlib import Path
from typing import Any

import websockets

from .common import MAX_PLAYERS, COLORS, COLOR_LABELS, Player, Question, Room
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

VALID_HELP_TYPES = {"eliminate2", "research", "expert", "skip"}
HELP_TYPE_LABELS = {
    "eliminate2": "Eliminar 2 alternativas",
    "research": "Pesquisa rápida",
    "expert": "Ajuda do especialista",
    "skip": "Pular pergunta",
}


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
    failed: list[Any] = []
    for ws in sockets:
        if getattr(ws, "closed", False):
            failed.append(ws)
            continue
        payload["you"] = PLAYER_BY_SOCKET.get(ws)
        try:
            await send(ws, payload)
        except Exception:
            # Uma falha de envio significa que a conexão já não é utilizável.
            # A limpeza abaixo remove o socket e o jogador, evitando vagas
            # "fantasmas" que deixavam a sala cheia após uma desconexão.
            failed.append(ws)

    for dead_ws in failed:
        if dead_ws in ROOM_BY_SOCKET or dead_ws in PLAYER_BY_SOCKET:
            await remove_player_from_room(dead_ws, reason="perdeu a conexão", announce=True)


async def reject_join(ws: Any, reason: str, message: str) -> None:
    """Recusa uma entrada sem deixar um WebSocket órfão no servidor."""
    await send(ws, {"type": "join_rejected", "reason": reason, "message": message})


async def remove_player_from_room(
    ws: Any, *, reason: str = "desconectou", announce: bool = True
) -> None:
    """Remove definitivamente da sala o jogador associado a ``ws``.

    A implementação antiga apenas marcava ``connected=False``. Isso mantinha o
    jogador ocupando uma das quatro vagas e impedia uma nova entrada. Também
    deixava turnos presos quando o jogador da vez desaparecia. Agora a saída é
    definitiva para aquela participação. Se a partida ainda não começou, a
    pessoa pode entrar novamente como um novo jogador, desde que haja vaga.
    """
    code = ROOM_BY_SOCKET.pop(ws, None)
    player_id = PLAYER_BY_SOCKET.pop(ws, None)
    if code and code in SOCKETS_BY_ROOM:
        SOCKETS_BY_ROOM[code].discard(ws)

    if not code or not player_id:
        return
    room = ROOMS.get(code)
    if not room:
        return

    # Multijogador local usa um único socket para todos os jogadores. Ao fechar
    # esse socket, a sala inteira deixa de existir.
    if room.local_multiplayer:
        ROOMS.pop(code, None)
        SOCKETS_BY_ROOM.pop(code, None)
        return

    ordered_ids = list(room.players.keys())
    if player_id not in room.players:
        return
    removed_index = ordered_ids.index(player_id)
    player = room.players.pop(player_id)
    was_current = room.current_player_id == player_id

    # Mantém o índice apontando para o mesmo jogador lógico depois que a lista
    # diminui. Se quem saiu era o atual, next_turn() avançará para o seguinte.
    if removed_index <= room.current_turn_index:
        room.current_turn_index -= 1
    if room.players:
        room.current_turn_index = min(room.current_turn_index, len(room.players) - 1)
    else:
        room.current_turn_index = -1

    # Sala vazia: remove tudo imediatamente para não acumular salas mortas.
    if not room.players:
        ROOMS.pop(code, None)
        SOCKETS_BY_ROOM.pop(code, None)
        return

    host_changed = False
    if room.host_id == player_id:
        new_host = next(iter(room.players.values()))
        room.host_id = new_host.id
        for p in room.players.values():
            p.is_host = p.id == new_host.id
        host_changed = True

    if was_current and room.status == "playing":
        # Nunca deixa a partida aguardando resposta/ação de um jogador que não
        # existe mais. O turno dele é cancelado e seguimos para o próximo.
        room.current_question = None
        room.deadline_ts = None
        room.current_player_id = None
        room.turn_phase = "idle"
        room.pending_question_difficulty = None
        room.help_used_this_turn = False
        room.special_event = None
        room.last_roll = None
        room.turn_start_position = None
        room.answer_feedback = None
        room.pending_end_reason = None
        if announce:
            suffix = " O criador da sala foi transferido para outro jogador." if host_changed else ""
            await broadcast(room, f"{player.name} {reason} e foi removido da partida.{suffix}")
        await next_turn(room)
        return

    if announce:
        suffix = " O criador da sala agora é outro jogador." if host_changed else ""
        await broadcast(room, f"{player.name} {reason} e foi removido da sala.{suffix}")


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
    room.answer_feedback = None
    room.pending_end_reason = None
    room.ranking = make_ranking(room)
    await broadcast(room, f"Fim de jogo: {reason}")


async def next_turn(room: Room) -> None:
    if room.status != "playing":
        return

    active = active_player_ids(room)
    if not active:
        await end_game(room, "não há jogadores ativos")
        return

    players = room.ordered_players()
    player: Player | None = None
    skipped_names: list[str] = []

    # Procura o próximo jogador apto. Quem recebeu a penalidade de erro
    # perde exatamente a próxima rodada e volta a participar normalmente
    # nas rodadas seguintes.
    attempts = 0
    while attempts < len(players):
        room.current_turn_index = (room.current_turn_index + 1) % len(players)
        candidate = players[room.current_turn_index]
        attempts += 1
        if candidate.id not in active:
            continue
        if candidate.skip_turns > 0:
            candidate.skip_turns -= 1
            skipped_names.append(candidate.name)
            continue
        player = candidate
        break

    # Se todos os jogadores ativos precisavam pular esta rodada, a rodada é
    # considerada consumida e uma nova sequência começa imediatamente. Isso
    # também mantém o modo Um jogador funcional.
    if player is None and skipped_names:
        attempts = 0
        while attempts < len(players):
            room.current_turn_index = (room.current_turn_index + 1) % len(players)
            candidate = players[room.current_turn_index]
            attempts += 1
            if candidate.id in active:
                player = candidate
                break

    if player is None:
        await end_game(room, "nenhum jogador apto para continuar")
        return

    if skipped_names:
        if len(skipped_names) == 1:
            room.event_log.append(f"{skipped_names[0]} ficou uma rodada sem jogar por causa do erro anterior.")
        else:
            room.event_log.append(f"{', '.join(skipped_names)} ficaram uma rodada sem jogar por causa do erro anterior.")

    room.current_player_id = player.id
    room.current_question = None
    room.deadline_ts = None
    room.help_used_this_turn = False
    room.pending_question_difficulty = None
    room.special_event = None
    room.last_roll = None
    room.turn_start_position = player.position
    room.answer_feedback = None
    room.pending_end_reason = None

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


async def after_landing(room: Room, player: Player, *, movement_source: str = "other") -> None:
    """Processa somente os efeitos provocados pelo movimento que acabou de ocorrer.

    Casas de sorte/revés devem ser ativadas apenas quando o peão *cai nelas
    por causa de uma jogada de dado*. Retornos causados por erro/timeout não
    constituem uma nova chegada à casa e, portanto, nunca podem sortear o
    evento novamente.
    """
    max_pos = max_position_for_mode(room.game_mode)
    if player.position >= max_pos:
        room.pending_question_difficulty = difficulty_for_position(player.position, room.game_mode)
        room.turn_phase = "awaiting_question"
        await broadcast(room, f"{player.name} chegou ao {track_label(player.position, room.game_mode)}. Responda a pergunta final para vencer.")
        return

    if room.game_mode != "classic" and player.position in LUCK_POSITIONS:
        # Proteção importante: um peão pode voltar para uma casa de
        # sorte/revés após errar uma pergunta. Esse retorno é apenas uma
        # penalidade de posição e NÃO deve disparar um novo sorteio.
        if movement_source != "dice_roll":
            return

        message, delta = random.choice(LUCK_EVENTS)
        old = player.credits
        player.credits = max(0, player.credits + delta)
        # Mostra a operação completa para evitar ambiguidade no mobile:
        # ganho: 3 + 4 = 7; perda: 3 - 4 = 0.
        if delta >= 0:
            operation = f"{old} + {delta} = {player.credits}"
        else:
            operation = f"{old} - {abs(delta)} = {player.credits}"
        room.special_event = f"{message} ({operation} créditos)"
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
    if room.turn_start_position is None:
        room.turn_start_position = player.position
    player.position = min(max_pos, player.position + roll)
    room.last_roll = roll
    await broadcast(room, f"{player.name} tirou {roll} no dado e avançou para {track_label(player.position, room.game_mode)}.")
    await after_landing(room, player, movement_source="dice_roll")


async def handle_continue(ws: Any) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    player = get_current_player_for_ws(room, player_id)
    if not player:
        return

    # Depois que uma alternativa é escolhida, mostramos primeiro o gabarito.
    # Só após o jogador tocar em Continuar a interface avança para a tela de
    # consequência (créditos/retorno de casas) ou para o fim da partida.
    if room.turn_phase == "answer_feedback" and room.answer_feedback and room.current_question:
        was_correct = bool(room.answer_feedback.get("is_correct"))
        room.answer_feedback = None
        room.deadline_ts = None
        room.pending_question_difficulty = None

        if was_correct:
            reward = CREDITS_BY_DIFFICULTY[room.current_question.difficulty]
            player.credits += reward
            event = (
                f"{player.name} acertou. Ganhou {reward} créditos de carbono. "
                f"Saldo atual: {player.credits} créditos."
            )
            room.current_question = None
            room.turn_phase = "turn_result"
            room.special_event = event
            room.turn_start_position = None
            if player.position >= max_position_for_mode(room.game_mode):
                room.pending_end_reason = f"{player.name} completou o percurso com {player.credits} créditos"
            await broadcast(room, event)
            return

        # A penalidade de erro é aplicada somente depois que o jogador conferiu
        # o gabarito. Isso impede que o peão/placar mudem antes da tela educativa
        # com as alternativas corretas e incorretas.
        await apply_wrong_answer(room, player)
        return

    if room.turn_phase not in {"luck_result", "turn_result"}:
        return
    if room.turn_phase == "turn_result" and room.pending_end_reason:
        reason = room.pending_end_reason
        room.pending_end_reason = None
        await end_game(room, reason)
        return
    room.turn_phase = "idle"
    room.special_event = None
    await next_turn(room)


def choose_unused_question(room: Room, difficulty: str) -> Question:
    """Sorteia sem repetir enquanto houver questões inéditas no nível.

    Quando todas as questões daquele nível já tiverem aparecido na partida,
    inicia-se um novo ciclo. Assim, a repetição só é possível depois de esgotar
    o conjunto disponível daquele nível.
    """
    bank = QUESTIONS[difficulty]
    used = set(room.used_question_ids.setdefault(difficulty, []))
    available = [question for question in bank if question.id not in used]
    if not available:
        room.used_question_ids[difficulty] = []
        available = list(bank)
    question = random.choice(available)
    room.used_question_ids[difficulty].append(question.id)
    return question


async def start_question(room: Room, player: Player) -> None:
    if room.status != "playing":
        return
    if room.turn_phase != "awaiting_question" or room.current_player_id != player.id:
        return

    difficulty = room.pending_question_difficulty or difficulty_for_position(player.position, room.game_mode)
    question = choose_unused_question(room, difficulty)
    room.current_question = Question(
        id=question.id,
        difficulty=question.difficulty,
        prompt=question.prompt,
        options=list(question.options),
        answer_index=question.answer_index,
        expert_tip=question.expert_tip,
        source=question.source,
    )
    room.deadline_ts = now() + QUESTION_TIME_LIMIT
    room.help_used_this_turn = False
    room.answer_feedback = None
    room.turn_phase = "question"
    await broadcast(room, f"Pergunta iniciada para {player.name}. Tempo: {QUESTION_TIME_LIMIT}s.")


async def apply_wrong_answer(
    room: Room,
    player: Player,
    reason: str = "resposta incorreta",
    selected_index: int | None = None,
) -> None:
    # Regra original do Green Impact: ao errar ou não responder, o jogador
    # retorna à casa de onde partiu naquele turno, paga em créditos a
    # quantidade de casas retornadas (sem saldo negativo) e perde a próxima
    # rodada. Não existe eliminação por quantidade de erros.
    landed_position = player.position
    origin_position = room.turn_start_position
    if origin_position is None:
        # Fallback defensivo para partidas/estados antigos.
        if room.game_mode == "classic":
            origin_position = max(0, landed_position - 1)
        else:
            origin_position = max(0, landed_position - int(room.last_roll or 0))

    origin_position = max(0, min(int(origin_position), landed_position))
    returned_houses = max(0, landed_position - origin_position)
    old_credits = player.credits
    player.position = origin_position
    player.credits = max(0, old_credits - returned_houses)
    player.skip_turns = max(player.skip_turns, 1)

    event = (
        f"{player.name} errou ({reason}). Retornou de "
        f"{track_label(landed_position, room.game_mode)} para "
        f"{track_label(origin_position, room.game_mode)}, pagou {returned_houses} "
        f"crédito{'s' if returned_houses != 1 else ''} de carbono "
        f"({old_credits} -> {player.credits}) e ficará uma rodada sem jogar."
    )

    room.deadline_ts = None
    room.pending_question_difficulty = None
    room.special_event = event
    # O retorno por erro não é uma nova jogada de dado. Limpa o último dado
    # para impedir que qualquer atualização tardia interprete o rollback como
    # uma nova chegada e reaplique sorte/revés.
    room.last_roll = None
    room.turn_start_position = None

    if selected_index is not None and room.current_question is not None:
        # Resposta efetivamente escolhida: mantém a pergunta apenas durante a
        # tela de gabarito. O jogador vê a correta em verde e todas as
        # incorretas em vermelho antes da consequência da rodada.
        room.answer_feedback = {
            "player_id": player.id,
            "selected_index": selected_index,
            "correct_index": room.current_question.answer_index,
            "is_correct": False,
            "message": "Resposta incorreta.",
        }
        room.turn_phase = "answer_feedback"
        await broadcast(room, event, reveal_answer=True)
        return

    # Tempo esgotado continua indo diretamente para a consequência, pois não
    # houve uma alternativa selecionada pelo jogador.
    room.current_question = None
    room.answer_feedback = None
    room.turn_phase = "turn_result"
    await broadcast(room, event, reveal_answer=True)


async def expire_if_needed(room: Room) -> bool:
    if room.status != "playing" or not room.current_question or not room.deadline_ts:
        return False
    if now() <= room.deadline_ts:
        return False
    player = room.players[room.current_player_id]
    await apply_wrong_answer(room, player, "tempo esgotado")
    return True


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
        await reject_join(ws, "room_not_found", "Sala não encontrada. Confira o código e tente novamente.")
        return
    # A lotação é verificada antes do estado da partida para que uma sala com
    # quatro pessoas sempre responda claramente que está cheia.
    if len(room.players) >= MAX_PLAYERS:
        await reject_join(ws, "room_full", f"Sala cheia. Limite máximo de {MAX_PLAYERS} jogadores.")
        return
    if room.status != "waiting":
        await reject_join(
            ws,
            "game_started",
            "A partida já começou. Jogadores que saíram não podem retornar nesta partida.",
        )
        return

    player_id = str(uuid.uuid4())
    room.players[player_id] = Player(id=player_id, name=name, credits=INITIAL_CREDITS)
    SOCKETS_BY_ROOM.setdefault(code, set()).add(ws)
    ROOM_BY_SOCKET[ws] = code
    PLAYER_BY_SOCKET[ws] = player_id
    await send(ws, {"type": "joined", "room_code": code, "player_id": player_id})
    await broadcast(room, f"{name} entrou na sala.")


async def handle_leave(ws: Any) -> None:
    """Saída voluntária: libera a vaga antes mesmo do fechamento do socket."""
    await remove_player_from_room(ws, reason="saiu", announce=True)
    try:
        await ws.close(code=1000, reason="Jogador saiu da sala")
    except Exception:
        pass


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
    room.answer_feedback = None
    room.pending_end_reason = None
    room.used_question_ids = {"easy": [], "medium": [], "hard": []}
    for p in room.players.values():
        p.position = 0
        p.credits = INITIAL_CREDITS
        p.skip_turns = 0
        p.used_helps.clear()
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
    if not player or not room.current_question or room.turn_phase != "question":
        await send(ws, {"type": "error", "message": "Não é sua vez ou a pergunta já foi respondida."})
        return

    answer_index = int(data.get("answer_index", -1))
    if not 0 <= answer_index < len(room.current_question.options):
        await send(ws, {"type": "error", "message": "Alternativa inválida."})
        return

    is_correct = answer_index == room.current_question.answer_index
    room.deadline_ts = None
    room.pending_question_difficulty = None
    room.answer_feedback = {
        "player_id": player.id,
        "selected_index": answer_index,
        "correct_index": room.current_question.answer_index,
        "is_correct": is_correct,
        "message": "Resposta correta!" if is_correct else "Resposta incorreta.",
    }
    room.turn_phase = "answer_feedback"
    # Nenhuma consequência é aplicada ainda. Primeiro todos veem o gabarito;
    # apenas o jogador da vez pode avançar para a tela de resultado da rodada.
    await broadcast(room, reveal_answer=True)


async def handle_stop(ws: Any) -> None:
    code = ROOM_BY_SOCKET.get(ws)
    player_id = PLAYER_BY_SOCKET.get(ws)
    if not code or not player_id:
        return
    room = ROOMS[code]
    if await expire_if_needed(room):
        return
    player = get_current_player_for_ws(room, player_id)
    if not player or not room.current_question or room.turn_phase != "question":
        await send(ws, {"type": "error", "message": "Inicie uma pergunta ativa antes de decidir parar."})
        return
    player.stopped = True
    old_credits = player.credits
    old_position = player.position
    player.credits = player.credits // 2
    player.position = 0
    event = (
        f"{player.name} decidiu parar. Voltou de {track_label(old_position, room.game_mode)} para o Início "
        f"e perdeu metade do saldo: {old_credits} -> {player.credits} créditos. "
        "Ele não participa das próximas rodadas."
    )
    room.current_question = None
    room.deadline_ts = None
    room.answer_feedback = None
    room.turn_phase = "turn_result"
    room.pending_question_difficulty = None
    room.special_event = event
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
    if not player or not room.current_question or room.turn_phase != "question":
        await send(ws, {"type": "error", "message": "Não é sua vez ou a pergunta não está mais ativa."})
        return
    help_type = str(data.get("help") or "")
    if help_type not in VALID_HELP_TYPES:
        await send(ws, {"type": "error", "message": "Ajuda inválida."})
        return
    if help_type in player.used_helps:
        await send(ws, {
            "type": "error",
            "message": f"A carta '{HELP_TYPE_LABELS[help_type]}' já foi utilizada por você nesta partida.",
        })
        return
    if room.help_used_this_turn:
        await send(ws, {"type": "error", "message": "Você já usou uma ajuda nesta rodada."})
        return
    if player.credits < HELP_COST:
        await send(ws, {"type": "error", "message": "Créditos insuficientes para comprar ajuda."})
        return

    player.credits -= HELP_COST
    room.help_used_this_turn = True
    player.used_helps.append(help_type)

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
        expert_tip = (room.current_question.expert_tip or "").strip()
        if not expert_tip:
            # Todas as perguntas do banco atual possuem expert_tip. Este fallback
            # evita revelar a resposta caso um banco antigo seja carregado por engano.
            expert_tip = "Dica indisponível para esta pergunta."
        await send(ws, {"type": "private_tip", "question_id": room.current_question.id, "message": f"Dica do especialista: {expert_tip}"})
        await broadcast(room, f"{player.name} comprou ajuda do especialista. Custo: {HELP_COST} créditos. Saldo: {player.credits} créditos.")
    elif help_type == "skip":
        event = f"{player.name} usou Pular pergunta. Custo: {HELP_COST} créditos. Saldo atual: {player.credits} créditos."
        room.current_question = None
        room.deadline_ts = None
        room.answer_feedback = None
        room.turn_phase = "turn_result"
        room.pending_question_difficulty = None
        room.special_event = event
        await broadcast(room, event)


async def handler(ws: Any, path: str | None = None) -> None:
    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await send(ws, {"type": "error", "message": "Mensagem inválida."})
                continue

            msg_type = data.get("type")
            try:
                if msg_type == "create":
                    await handle_create(ws, data)
                elif msg_type == "create_local":
                    await handle_create_local(ws, data)
                elif msg_type == "join":
                    await handle_join(ws, data)
                elif msg_type == "leave":
                    await handle_leave(ws)
                    break
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
            except Exception as exc:
                # Um comando inválido ou uma corrida de estado não deve derrubar
                # o WebSocket inteiro. Registramos o erro e mantemos a sessão
                # viva; se a conexão em si tiver caído, o loop/finally fará a
                # limpeza normal.
                print(f"Erro ao processar mensagem {msg_type!r}: {exc}")
                try:
                    await send(ws, {
                        "type": "error",
                        "message": "Não foi possível processar essa ação. O servidor manteve sua conexão ativa.",
                    })
                except Exception:
                    break
    finally:
        # Desconexão real, fechamento do aplicativo ou perda de rede: o jogador
        # é retirado definitivamente, liberando a vaga e evitando turnos presos.
        await remove_player_from_room(ws, reason="desconectou", announce=True)


async def main() -> None:
    global QUESTIONS
    parser = argparse.ArgumentParser(description="Servidor online do Green Impact")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    QUESTIONS = load_questions()
    async with websockets.serve(
        handler,
        args.host,
        args.port,
        ping_interval=30,
        ping_timeout=90,
        close_timeout=10,
        max_queue=64,
    ):
        print(f"Servidor Green Impact rodando em ws://{args.host}:{args.port}")
        print("Pressione Ctrl+C para encerrar.")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
