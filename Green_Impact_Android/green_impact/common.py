from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

MAX_PLAYERS = 4
COLORS = ["green", "yellow", "red", "blue"]
COLOR_LABELS = {
    "green": "Verde",
    "yellow": "Amarelo",
    "red": "Vermelho",
    "blue": "Azul",
}

PLAYER_RGB = {
    "green": (33, 132, 50),
    "yellow": (230, 170, 38),
    "red": (207, 51, 51),
    "blue": (40, 125, 200),
}

DIFFICULTY_LABELS = {
    "easy": "Fácil / Verde",
    "medium": "Médio / Amarelo",
    "hard": "Difícil / Vermelho",
}

@dataclass
class Player:
    id: str
    name: str
    color: str | None = None
    position: int = 0
    credits: int = 3
    skip_turns: int = 0
    used_helps: list[str] = field(default_factory=list)
    eliminated: bool = False
    stopped: bool = False
    connected: bool = True
    is_host: bool = False

    def public(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Question:
    id: str
    difficulty: str
    prompt: str
    options: list[str]
    answer_index: int
    expert_tip: str = ""
    source: str = "Banco de perguntas do protótipo"
    eliminated_options: list[int] = field(default_factory=list)

    def public(self, reveal_answer: bool = False) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "difficulty": self.difficulty,
            "prompt": self.prompt,
            "options": self.options,
            "eliminated_options": self.eliminated_options,
            "source": self.source,
        }
        if reveal_answer:
            payload["answer_index"] = self.answer_index
        return payload

@dataclass
class Room:
    code: str
    host_id: str
    players: dict[str, Player] = field(default_factory=dict)
    status: str = "waiting"  # waiting, playing, ended
    current_turn_index: int = -1
    current_question: Question | None = None
    current_player_id: str | None = None
    deadline_ts: float | None = None
    # turn_phase:
    # idle, awaiting_roll, awaiting_question, question, luck_result
    turn_phase: str = "idle"
    pending_question_difficulty: str | None = None
    help_used_this_turn: bool = False
    event_log: list[str] = field(default_factory=list)
    ranking: list[dict[str, Any]] = field(default_factory=list)
    # classic = tabuleiro antigo / avanço automático de 1 casa.
    # dice_board = tabuleiro novo / dado / casas de sorte-revés.
    game_mode: str = "dice_board"
    local_multiplayer: bool = False
    last_roll: int | None = None
    special_event: str | None = None
    # Posição em que o jogador iniciou o turno, usada para devolver o peão
    # à casa de origem quando a pergunta é respondida incorretamente.
    turn_start_position: int | None = None

    def ordered_players(self) -> list[Player]:
        return list(self.players.values())

    def active_players(self) -> list[Player]:
        return [p for p in self.ordered_players() if not p.eliminated and not p.stopped]

    def public(self, reveal_answer: bool = False) -> dict[str, Any]:
        return {
            "code": self.code,
            "host_id": self.host_id,
            "status": self.status,
            "players": [p.public() for p in self.ordered_players()],
            "current_player_id": self.current_player_id,
            "current_question": self.current_question.public(reveal_answer) if self.current_question else None,
            "deadline_ts": self.deadline_ts,
            "turn_phase": self.turn_phase,
            "pending_question_difficulty": self.pending_question_difficulty,
            "help_used_this_turn": self.help_used_this_turn,
            "event_log": self.event_log[-8:],
            "ranking": self.ranking,
            "game_mode": self.game_mode,
            "local_multiplayer": self.local_multiplayer,
            "last_roll": self.last_roll,
            "special_event": self.special_event,
            "turn_start_position": self.turn_start_position,
            "max_players": MAX_PLAYERS,
            "is_full": len(self.players) >= MAX_PLAYERS,
        }
