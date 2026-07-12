from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


class PCVisualAnalysisSourceTests(unittest.TestCase):
    def test_client_source_parses_and_contains_requested_hud(self) -> None:
        source = (PROJECT / "green_impact" / "client.py").read_text(encoding="utf-8")
        ast.parse(source)
        for text in (
            "SUA VEZ",
            "SALDO DE CARBONO",
            "AJUDAS",
            "não são respostas",
            "PARAR NÃO É AJUDA",
            "CONSEQUÊNCIA",
            "math.ceil",
        ):
            self.assertIn(text, source)


if __name__ == "__main__":
    unittest.main()
