from __future__ import annotations

INITIAL_CREDITS = 3
HELP_COST = 3
QUESTION_TIME_LIMIT = 40
RESEARCH_BONUS_SECONDS = 20
MAX_POSITION = 10

CREDITS_BY_DIFFICULTY = {
    "easy": 13,
    "medium": 25,
    "hard": 37,
}


def difficulty_for_position(position: int) -> str:
    """Mapeia as casas do tabuleiro para os baralhos de perguntas.

    O tabuleiro físico possui casas com cores diferentes. Neste protótipo,
    usamos a progressão: casas 1-3 fáceis, 4-6 médias e 7-10 difíceis.
    """
    if position <= 3:
        return "easy"
    if position <= 6:
        return "medium"
    return "hard"
