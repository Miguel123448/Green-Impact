from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from green_impact import server
from green_impact.common import Player, Question, Room


class FakeWebSocket:
    pass


class RewardByDifficultyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        server.ROOMS.clear()
        server.SOCKETS_BY_ROOM.clear()
        server.ROOM_BY_SOCKET.clear()
        server.PLAYER_BY_SOCKET.clear()

    async def assert_reward(self, difficulty: str, expected_reward: int) -> None:
        player = Player(id="p1", name="Jogador", credits=10, position=1)
        question = Question(
            id=f"q-{difficulty}",
            difficulty=difficulty,
            prompt="Pergunta?",
            options=["A", "B", "C", "D"],
            answer_index=1,
        )
        room = Room(
            code="TEST",
            host_id=player.id,
            players={player.id: player},
            status="playing",
            current_player_id=player.id,
            current_question=question,
            deadline_ts=time.time() + 30,
            turn_phase="question",
            game_mode="classic",
        )
        ws = FakeWebSocket()
        server.ROOMS[room.code] = room
        server.SOCKETS_BY_ROOM[room.code] = set()
        server.ROOM_BY_SOCKET[ws] = room.code
        server.PLAYER_BY_SOCKET[ws] = player.id

        await server.handle_answer(ws, {"answer_index": question.answer_index})

        self.assertEqual(player.credits, 10 + expected_reward)
        self.assertEqual(room.turn_result["credit_delta"], expected_reward)
        self.assertIn(f"Ganhou {expected_reward} crédito", room.turn_result["message"])

    async def test_easy_question_gives_one_credit(self) -> None:
        await self.assert_reward("easy", 1)

    async def test_medium_question_gives_two_credits(self) -> None:
        await self.assert_reward("medium", 2)

    async def test_hard_question_gives_three_credits(self) -> None:
        await self.assert_reward("hard", 3)


if __name__ == "__main__":
    unittest.main()
