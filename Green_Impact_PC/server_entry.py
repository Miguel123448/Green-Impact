"""Ponto de entrada para empacotar o servidor com PyInstaller.

Não execute green_impact/server.py diretamente no PyInstaller, pois ele usa
imports relativos dentro do pacote green_impact.
"""

import asyncio

from green_impact.server import main


if __name__ == "__main__":
    asyncio.run(main())
