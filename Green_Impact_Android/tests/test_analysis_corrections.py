from __future__ import annotations

import asyncio
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


class AnalysisCorrectionsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        server.ROOMS.clear()
        server.SOCKETS_BY_ROOM.clear()
        server.ROOM_BY_SOCKET.clear()
        server.PLAYER_BY_SOCKET.clear()

    def make_room(self, code: str, credits: int = 5, position: int = 4) -> tuple[Room, Player]:
        player = Player(
            id="p1",
            name="Jogador 1",
            color="green",
            credits=credits,
            position=position,
        )
        question = Question(
            id="q1",
            difficulty="easy",
            prompt="Pergunta de teste?",
            options=["A", "B", "C", "D"],
            answer_index=2,
        )
        room = Room(
            code=code,
            host_id=player.id,
            players={player.id: player},
            status="playing",
            current_player_id=player.id,
            current_question=question,
            deadline_ts=time.time() + 30,
            turn_phase="question",
            game_mode="classic",
        )
        server.ROOMS[code] = room
        server.SOCKETS_BY_ROOM[code] = set()
        return room, player

    async def test_expired_question_becomes_timeout_consequence(self) -> None:
        room, player = self.make_room("TIME", credits=8, position=5)
        room.deadline_ts = time.time() - 0.1

        changed = await server.expire_if_needed(room)

        self.assertTrue(changed)
        self.assertEqual(room.turn_phase, "turn_result")
        self.assertEqual(room.turn_result["kind"], "timeout")
        self.assertEqual(room.turn_result["correct_answer"], "C")
        self.assertEqual(player.position, 0)
        self.assertEqual(player.credits, 0)

    async def test_server_monitor_expires_without_client_message(self) -> None:
        room, _player = self.make_room("MON")
        room.deadline_ts = time.time() - 0.01
        task = asyncio.create_task(server.deadline_monitor(0.01))
        await asyncio.sleep(0.04)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertEqual(room.turn_result["kind"], "timeout")

    async def test_skip_records_cost_and_correct_answer(self) -> None:
        room, player = self.make_room("SKIP", credits=6)
        ws = FakeWebSocket()
        server.ROOM_BY_SOCKET[ws] = room.code
        server.PLAYER_BY_SOCKET[ws] = player.id

        await server.handle_help(ws, {"help": "skip"})

        self.assertEqual(room.turn_result["kind"], "skipped")
        self.assertEqual(room.turn_result["old_credits"], 6)
        self.assertEqual(room.turn_result["new_credits"], 3)
        self.assertEqual(room.turn_result["correct_answer"], "C")

    def test_android_source_has_requested_visual_sections(self) -> None:
        source = (PROJECT_DIR / "main.py").read_text(encoding="utf-8")
        self.assertIn("SALDO DE CARBONO", source)
        self.assertIn("São recursos opcionais, não respostas", source)
        self.assertIn("PARAR DE JOGAR", source)
        self.assertIn("CONSEQUÊNCIA", source)
        self.assertIn("math.ceil", source)
        self.assertNotIn('self.label("Pausa antes da pergunta"', source)
        self.assertLess(source.index("self.add(self.event_log_box())"), source.index("self.render_stop_area(my_turn)"))


if __name__ == "__main__":
    unittest.main()
