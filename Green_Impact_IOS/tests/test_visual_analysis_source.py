from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


class IOSVisualAnalysisSourceTests(unittest.TestCase):
    def test_main_source_parses_and_contains_requested_hud(self) -> None:
        source = (PROJECT / "main.py").read_text(encoding="utf-8")
        ast.parse(source)
        for text in (
            "JOGANDO AGORA",
            "SALDO DE CARBONO",
            "São recursos opcionais, não respostas",
            "PARAR",
            "CONSEQUÊNCIA",
            "math.ceil",
        ):
            self.assertIn(text, source)


if __name__ == "__main__":
    unittest.main()
