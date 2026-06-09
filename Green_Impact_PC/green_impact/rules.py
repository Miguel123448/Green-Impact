from __future__ import annotations

INITIAL_CREDITS = 3
HELP_COST = 3
QUESTION_TIME_LIMIT = 40
RESEARCH_BONUS_SECONDS = 20
CLASSIC_MAX_POSITION = 10

# No novo tabuleiro existem casas intermediárias de sorte/revés entre:
# 1 e 2, 4 e 5, 7 e 8, 11 e 12.
# Por isso o modo com dado usa índice de trilha, não apenas o número impresso da casa.
# Trilha: 0 INÍCIO, 1 casa 1, 2 sorte/revés, 3 casa 2, ..., 17 FIM.
DICE_TRACK = [
    "INÍCIO",
    "1",
    "Sorte/Revés 1-2",
    "2",
    "3",
    "4",
    "Sorte/Revés 4-5",
    "5",
    "6",
    "7",
    "Sorte/Revés 7-8",
    "8",
    "9",
    "10",
    "11",
    "Sorte/Revés 11-12",
    "12",
    "FIM",
]
DICE_MAX_POSITION = len(DICE_TRACK) - 1
MAX_POSITION = DICE_MAX_POSITION

# Índices da trilha que representam casas de sorte/revés.
LUCK_POSITIONS = {2, 6, 10, 15}

# Mapeamento de índice da trilha para o número da casa do tabuleiro.
# Usado para escolher a dificuldade das perguntas.
TRACK_TO_NUMERIC_HOUSE = {
    1: 1,
    3: 2,
    4: 3,
    5: 4,
    7: 5,
    8: 6,
    9: 7,
    11: 8,
    12: 9,
    13: 10,
    14: 11,
    16: 12,
    17: 12,
}

CREDITS_BY_DIFFICULTY = {
    "easy": 13,
    "medium": 25,
    "hard": 37,
}

LUCK_EVENTS = [
    ("Sorte: projeto de reciclagem aprovado. Ganhou 5 créditos de carbono.", 5),
    ("Sorte: economia de energia na comunidade. Ganhou 4 créditos de carbono.", 4),
    ("Sorte: mutirão de plantio urbano. Ganhou 3 créditos de carbono.", 3),
    ("Revés: desperdício de água detectado. Perdeu 3 créditos de carbono.", -3),
    ("Revés: descarte irregular de resíduos. Perdeu 4 créditos de carbono.", -4),
    ("Revés: aumento de emissão de carbono. Perdeu 5 créditos de carbono.", -5),
]


def max_position_for_mode(game_mode: str) -> int:
    return CLASSIC_MAX_POSITION if game_mode == "classic" else DICE_MAX_POSITION


def is_luck_position(position: int, game_mode: str = "dice_board") -> bool:
    return game_mode != "classic" and int(position) in LUCK_POSITIONS


def track_label(position: int, game_mode: str = "dice_board") -> str:
    if game_mode == "classic":
        if int(position) <= 0:
            return "Início"
        if int(position) >= CLASSIC_MAX_POSITION:
            return "10/FIM"
        return str(int(position))
    pos = max(0, min(DICE_MAX_POSITION, int(position)))
    return DICE_TRACK[pos]


def numeric_house_for_position(position: int, game_mode: str = "dice_board") -> int:
    if game_mode == "classic":
        return max(0, min(CLASSIC_MAX_POSITION, int(position)))
    pos = max(0, min(DICE_MAX_POSITION, int(position)))
    return TRACK_TO_NUMERIC_HOUSE.get(pos, 0)


def difficulty_for_position(position: int, game_mode: str = "dice_board") -> str:
    """Mapeia a posição para o baralho de perguntas.

    classic: mantém a regra antiga do modo um jogador.
    dice_board: usa o novo tabuleiro com casas intermediárias de sorte/revés.
    Casas numéricas 1-5 = fácil, 6-9 = médio, 10-12 = difícil.
    """
    if game_mode == "classic":
        if position <= 3:
            return "easy"
        if position <= 6:
            return "medium"
        return "hard"

    house = numeric_house_for_position(position, game_mode)
    if house <= 5:
        return "easy"
    if house <= 9:
        return "medium"
    return "hard"
