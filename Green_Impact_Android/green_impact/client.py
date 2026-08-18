from __future__ import annotations

import argparse
import asyncio
import json
import math
import socket
import textwrap
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pygame
import websockets

from .common import COLOR_LABELS, PLAYER_RGB
from .rules import track_label

BASE_DIR = Path(__file__).resolve().parents[1]
ASSET_DIR = BASE_DIR / "assets"

WINDOW_W, WINDOW_H = 1280, 720
BG = (235, 238, 214)
PANEL = (245, 246, 225)
DARK = (18, 77, 48)
TEXT = (35, 45, 38)
DISABLED = (165, 165, 155)
WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
RED = (180, 40, 40)

COLOR_ORDER = ["green", "yellow", "red", "blue"]
COLOR_NAMES = {"green": "Verde", "yellow": "Amarelo", "red": "Vermelho", "blue": "Azul"}

# Coordenadas aproximadas no tabuleiro original 1024 x 1536.
BOARD_ORIGINAL_W = 1024
BOARD_ORIGINAL_H = 1536
PATH_X = {
    "green": 190,
    "yellow": 410,
    "red": 633,
    "blue": 855,
}
PATH_Y = {
    0: 1350,
    1: 1242,
    2: 1134,
    3: 1024,
    4: 914,
    5: 803,
    6: 691,
    7: 579,
    8: 468,
    9: 356,
    10: 245,
}


def split_server_url(server_url: str) -> tuple[str, str]:
    """Extrai host e porta de uma URL ws://host:porta para preencher o menu."""
    value = (server_url or "").replace("ws://", "").replace("wss://", "")
    if "/" in value:
        value = value.split("/", 1)[0]
    if ":" in value:
        host, port = value.rsplit(":", 1)
        return host or "127.0.0.1", port or "8765"
    return value or "127.0.0.1", "8765"


def build_server_url(host: str, port: str) -> str:
    host = (host or "127.0.0.1").strip()
    port = (port or "8765").strip()
    if host.startswith("ws://") or host.startswith("wss://"):
        return host
    return f"ws://{host}:{port}"


def get_lan_ip() -> str:
    """Tenta descobrir o IP local para outros computadores da mesma rede."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def wrap_text(text: str, width: int = 60) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        if not paragraph:
            lines.append("")
        else:
            lines.extend(textwrap.wrap(paragraph, width=width, replace_whitespace=False))
    return lines


class Button:
    def __init__(self, rect: pygame.Rect, text: str, callback: Callable[[], None], enabled: bool = True):
        self.rect = rect
        self.text = text
        self.callback = callback
        self.enabled = enabled

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small: bool = False) -> None:
        mouse = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse)
        if not self.enabled:
            fill = (200, 205, 188)
            border = DISABLED
            color = (120, 120, 120)
        elif hover:
            fill = (226, 238, 203)
            border = DARK
            color = DARK
        else:
            fill = (239, 245, 218)
            border = DARK
            color = DARK
        pygame.draw.rect(screen, fill, self.rect, border_radius=12)
        pygame.draw.rect(screen, border, self.rect, width=2, border_radius=12)
        label = font.render(self.text, True, color)
        screen.blit(label, label.get_rect(center=self.rect.center))

    def click(self) -> None:
        if self.enabled:
            self.callback()




class InputBox:
    def __init__(self, rect: pygame.Rect, label: str, value: str = ""):
        self.rect = rect
        self.label = label
        self.value = value
        self.active = False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, label_font: pygame.font.Font) -> None:
        label = label_font.render(self.label, True, DARK)
        screen.blit(label, (self.rect.x, self.rect.y - 24))
        fill = WHITE if self.active else (248, 249, 235)
        border = DARK if self.active else (125, 150, 120)
        pygame.draw.rect(screen, fill, self.rect, border_radius=10)
        pygame.draw.rect(screen, border, self.rect, width=2, border_radius=10)
        shown = self.value if self.value else ""
        text = font.render(shown, True, TEXT)
        screen.blit(text, (self.rect.x + 12, self.rect.y + 10))
        if self.active:
            caret_x = self.rect.x + 12 + text.get_width() + 2
            pygame.draw.line(screen, TEXT, (caret_x, self.rect.y + 10), (caret_x, self.rect.y + self.rect.h - 10), 2)

    def handle_key(self, event: pygame.event.Event) -> None:
        if not self.active:
            return
        if event.key == pygame.K_BACKSPACE:
            self.value = self.value[:-1]
        elif event.key in (pygame.K_RETURN, pygame.K_TAB, pygame.K_ESCAPE):
            self.active = False
        elif event.unicode and len(self.value) < 40:
            # Caracteres comuns para nome, IP, porta e código da sala.
            if event.unicode.isprintable():
                self.value += event.unicode

class GreenImpactClient:
    def __init__(self, server_url: str = "", name: str = "Jogador", room: str | None = None, start_in_menu: bool = True):
        self.server_url = server_url
        self.name = name
        self.join_room = room.upper() if room else None
        self.in_menu = start_in_menu
        self.ws: Any = None
        self.state: dict[str, Any] | None = None
        self.you: str | None = None
        self.room_code: str | None = None
        self.server_delta = 0.0
        self.messages: list[str] = []
        self.private_tip: str | None = None
        self.running = True
        self.buttons: list[Button] = []
        self.timeout_sent_for_question: str | None = None
        self.connection_error: str | None = None
        self.connecting = False
        self.local_server_thread: threading.Thread | None = None
        self.local_server_error: str | None = None
        self.local_server_port = 8765
        self.lan_ip = get_lan_ip()

        pygame.init()
        pygame.display.set_caption("Green Impact - Uma Jornada Sustentável")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 22)
        self.font_small = pygame.font.SysFont("arial", 18)
        self.font_big = pygame.font.SysFont("arial", 34, bold=True)
        self.font_title = pygame.font.SysFont("arial", 44, bold=True)

        self.board_rect = pygame.Rect(20, 20, 455, 682)
        self.board_img = self.load_image(ASSET_DIR / "board.jpg", self.board_rect.size)
        self.logo_img = self.load_image(ASSET_DIR / "logo.png", (320, 160), keep_alpha=True)

        initial_host, initial_port = split_server_url(server_url or "ws://127.0.0.1:8765")
        # Campos do menu. Eles ficam mais abaixo para não sobrepor o título/descrição.
        self.menu_inputs: dict[str, InputBox] = {
            "name": InputBox(pygame.Rect(565, 310, 270, 42), "Seu nome", name or "Jogador"),
            "host": InputBox(pygame.Rect(565, 382, 270, 42), "IP do servidor", initial_host),
            "port": InputBox(pygame.Rect(865, 382, 120, 42), "Porta", initial_port),
            "room": InputBox(pygame.Rect(565, 454, 190, 42), "Código da sala", (room or "").upper()),
        }

    def load_image(self, path: Path, size: tuple[int, int], keep_alpha: bool = False) -> pygame.Surface | None:
        try:
            img = pygame.image.load(str(path))
            img = img.convert_alpha() if keep_alpha else img.convert()
            return pygame.transform.smoothscale(img, size)
        except Exception:
            return None

    async def connect(self) -> None:
        await self.connect_to(self.server_url, self.name, self.join_room)

    async def connect_from_menu(self, create_room: bool) -> None:
        name = self.menu_inputs["name"].value.strip() or "Jogador"
        host = self.menu_inputs["host"].value.strip() or "127.0.0.1"
        port = self.menu_inputs["port"].value.strip() or "8765"
        room = self.menu_inputs["room"].value.strip().upper()

        if not create_room and not room:
            self.connection_error = "Digite o código da sala para entrar."
            self.messages.append("Erro: digite o código da sala para entrar.")
            return

        await self.connect_to(build_server_url(host, port), name, None if create_room else room)

    async def connect_to(self, server_url: str, name: str, room: str | None = None) -> None:
        if self.connecting:
            return
        self.connecting = True
        self.connection_error = None
        self.server_url = server_url
        self.name = name.strip()[:20] or "Jogador"
        self.join_room = room.upper() if room else None
        self.state = None
        self.you = None
        self.room_code = None
        self.timeout_sent_for_question = None

        try:
            self.messages.append("Conectando ao servidor selecionado...")
            self.ws = await websockets.connect(self.server_url, ping_interval=30, ping_timeout=90, close_timeout=10, max_queue=64)
            asyncio.create_task(self.listen())
            self.in_menu = False
            if self.join_room:
                await self.send({"type": "join", "room": self.join_room, "name": self.name})
            else:
                await self.send({"type": "create", "name": self.name})
        except Exception as exc:
            self.connection_error = f"Não foi possível conectar: {exc}"
            self.messages.append("Erro: " + self.connection_error)
            self.in_menu = True
            self.ws = None
        finally:
            self.connecting = False

    def start_local_server(self, port: int = 8765) -> None:
        if self.local_server_thread and self.local_server_thread.is_alive():
            return

        self.local_server_port = port
        self.local_server_error = None

        def server_thread() -> None:
            try:
                from . import server as local_server

                async def runner() -> None:
                    local_server.QUESTIONS = local_server.load_questions()
                    async with websockets.serve(
                        local_server.handler, "0.0.0.0", port,
                        ping_interval=30, ping_timeout=90, close_timeout=10, max_queue=64,
                    ):
                        await asyncio.Future()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(runner())
            except Exception as exc:
                self.local_server_error = str(exc)

        self.local_server_thread = threading.Thread(target=server_thread, daemon=True)
        self.local_server_thread.start()
        self.messages.append(f"Servidor local aberto na porta {port}.")

    async def start_local_and_create(self) -> None:
        name = self.menu_inputs["name"].value.strip() or "Jogador"
        port_text = self.menu_inputs["port"].value.strip() or "8765"
        try:
            port = int(port_text)
        except ValueError:
            self.connection_error = "A porta precisa ser um número."
            self.messages.append("Erro: a porta precisa ser um número.")
            return
        self.start_local_server(port)
        await asyncio.sleep(0.45)
        if self.local_server_error:
            self.connection_error = "Erro ao abrir servidor local: " + self.local_server_error
            self.messages.append(self.connection_error)
            return
        self.menu_inputs["host"].value = "127.0.0.1"
        await self.connect_to(f"ws://127.0.0.1:{port}", name, None)

    async def back_to_menu(self) -> None:
        if self.ws:
            try:
                await self.ws.send(json.dumps({"type": "leave"}, ensure_ascii=False))
                await asyncio.sleep(0.05)
            except Exception:
                pass
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None
        self.state = None
        self.you = None
        self.room_code = None
        self.in_menu = True
        self.connecting = False

    async def listen(self) -> None:
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                msg_type = data.get("type")
                if msg_type in {"created", "joined"}:
                    self.you = data.get("player_id")
                    self.room_code = data.get("room_code")
                    self.messages.append(f"Conectado à sala {self.room_code}.")
                elif msg_type == "state":
                    self.you = data.get("you") or self.you
                    if data.get("server_ts"):
                        self.server_delta = float(data["server_ts"]) - time.time()
                    self.state = data.get("room")
                    if self.state:
                        self.room_code = self.state.get("code") or self.room_code
                elif msg_type == "join_rejected":
                    message = str(data.get("message") or "Não foi possível entrar na sala.")
                    self.connection_error = message
                    self.messages.append("Erro: " + message)
                    self.state = None
                    self.you = None
                    self.room_code = None
                    self.in_menu = True
                    try:
                        await self.ws.close()
                    except Exception:
                        pass
                    break
                elif msg_type == "error":
                    message = str(data.get("message"))
                    self.connection_error = message
                    self.messages.append("Erro: " + message)
                elif msg_type == "private_tip":
                    self.private_tip = str(data.get("message"))
                    self.messages.append(self.private_tip)
                elif msg_type == "pong":
                    pass
        except Exception as exc:
            self.messages.append(f"Conexão encerrada: {exc}")

    async def send(self, payload: dict[str, Any]) -> None:
        if self.ws:
            await self.ws.send(json.dumps(payload, ensure_ascii=False))

    def fire_and_forget(self, payload: dict[str, Any]) -> None:
        asyncio.create_task(self.send(payload))

    def me(self) -> dict[str, Any] | None:
        if not self.state or not self.you:
            return None
        for p in self.state.get("players", []):
            if p.get("id") == self.you:
                return p
        return None

    def current_player(self) -> dict[str, Any] | None:
        if not self.state:
            return None
        current_id = self.state.get("current_player_id")
        for p in self.state.get("players", []):
            if p.get("id") == current_id:
                return p
        return None

    def is_my_turn(self) -> bool:
        return bool(self.state and self.you and self.state.get("current_player_id") == self.you)

    def board_to_screen(self, color: str, position: int) -> tuple[int, int]:
        ox = PATH_X.get(color, 512)
        oy = PATH_Y.get(position, PATH_Y[0])
        x = self.board_rect.x + int((ox / BOARD_ORIGINAL_W) * self.board_rect.w)
        y = self.board_rect.y + int((oy / BOARD_ORIGINAL_H) * self.board_rect.h)
        return x, y

    def draw_text(self, text: str, pos: tuple[int, int], font: pygame.font.Font | None = None, color: tuple[int, int, int] = TEXT) -> None:
        font = font or self.font
        surf = font.render(str(text), True, color)
        self.screen.blit(surf, pos)

    def draw_wrapped(self, text: str, x: int, y: int, max_chars: int, font: pygame.font.Font | None = None, color: tuple[int, int, int] = TEXT, line_h: int = 24) -> int:
        font = font or self.font
        for line in wrap_text(text, max_chars):
            surf = font.render(line, True, color)
            self.screen.blit(surf, (x, y))
            y += line_h
        return y

    def add_button(self, rect: pygame.Rect, text: str, callback: Callable[[], None], enabled: bool = True) -> None:
        btn = Button(rect, text, callback, enabled)
        self.buttons.append(btn)
        btn.draw(self.screen, self.font_small)

    def draw_menu(self) -> None:
        self.screen.fill(BG)
        # Painel visual esquerdo.
        if self.board_img:
            self.screen.blit(self.board_img, self.board_rect)
        else:
            pygame.draw.rect(self.screen, (210, 230, 190), self.board_rect, border_radius=16)

        panel = pygame.Rect(500, 20, 755, 682)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=18)
        pygame.draw.rect(self.screen, DARK, panel, width=2, border_radius=18)
        x, y = panel.x + 48, panel.y + 28

        if self.logo_img:
            self.screen.blit(self.logo_img, (x + 170, panel.y + 14))
        else:
            self.draw_text("GREEN IMPACT", (x + 180, panel.y + 42), self.font_title, DARK)

        # Posições fixas evitam que o HUD fique sobreposto em resoluções 1280x720.
        title_y = panel.y + 178
        self.draw_text("Menu de conexão", (x, title_y), self.font_big, DARK)
        self.draw_wrapped(
            "Escolha como quer jogar: conectar manualmente por IP ou abrir um servidor local neste computador.",
            x,
            title_y + 44,
            72,
            self.font_small,
            TEXT,
            22,
        )

        for box in self.menu_inputs.values():
            box.draw(self.screen, self.font, self.font_small)

        # Botões principais.
        self.add_button(
            pygame.Rect(565, 512, 220, 44),
            "Criar sala no IP",
            lambda: asyncio.create_task(self.connect_from_menu(create_room=True)),
            enabled=not self.connecting,
        )
        self.add_button(
            pygame.Rect(805, 512, 220, 44),
            "Entrar na sala",
            lambda: asyncio.create_task(self.connect_from_menu(create_room=False)),
            enabled=not self.connecting,
        )
        self.add_button(
            pygame.Rect(565, 570, 460, 46),
            "Abrir servidor local e criar sala",
            lambda: asyncio.create_task(self.start_local_and_create()),
            enabled=not self.connecting,
        )

        help_y = 632
        self.draw_wrapped(
            f"Para jogar no mesmo PC: use servidor local. Para outros computadores da mesma rede, eles devem colocar o IP do seu computador. Possível IP local: {self.lan_ip}",
            545,
            help_y,
            82,
            self.font_small,
            TEXT,
            22,
        )
        if self.local_server_thread and self.local_server_thread.is_alive():
            self.draw_wrapped(
                f"Servidor local ativo na porta {self.local_server_port}. Outros jogadores usam IP {self.lan_ip} e porta {self.local_server_port}.",
                545,
                help_y + 44,
                82,
                self.font_small,
                DARK,
                22,
            )
        if self.connection_error:
            self.draw_wrapped("Erro: " + self.connection_error, 545, 670, 82, self.font_small, RED, 22)

    def draw_connecting(self) -> None:
        self.screen.fill(BG)
        self.draw_board()
        right = pygame.Rect(500, 20, 755, 682)
        pygame.draw.rect(self.screen, PANEL, right, border_radius=18)
        pygame.draw.rect(self.screen, DARK, right, width=2, border_radius=18)
        x, y = right.x + 42, right.y + 230
        self.draw_text("Conectando...", (x, y), self.font_title, DARK)
        y += 62
        self.draw_wrapped("Conectando ao servidor selecionado...", x, y, 70, self.font_small)
        y += 40
        if self.connection_error:
            self.draw_wrapped("Erro: " + self.connection_error, x, y, 70, self.font_small, RED)
            y += 70
            self.add_button(
                pygame.Rect(x, y, 180, 44),
                "Voltar ao menu",
                lambda: asyncio.create_task(self.back_to_menu()),
                enabled=True,
            )

    def draw_board(self) -> None:
        if self.board_img:
            self.screen.blit(self.board_img, self.board_rect)
        else:
            pygame.draw.rect(self.screen, (210, 230, 190), self.board_rect, border_radius=16)
            self.draw_text("Tabuleiro", (self.board_rect.x + 150, self.board_rect.y + 20), self.font_big, DARK)

        if not self.state:
            return
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for p in self.state.get("players", []):
            color = p.get("color") or "green"
            key = (color, int(p.get("position", 0)))
            grouped.setdefault(key, []).append(p)

        for (color, position), players in grouped.items():
            base_x, base_y = self.board_to_screen(color, position)
            n = len(players)
            for idx, p in enumerate(players):
                angle = (2 * math.pi * idx / max(n, 1)) if n > 1 else 0
                offset = 13 if n > 1 else 0
                x = base_x + int(math.cos(angle) * offset)
                y = base_y + int(math.sin(angle) * offset)
                rgb = PLAYER_RGB.get(color, (80, 80, 80))
                if p.get("eliminated"):
                    rgb = (105, 105, 105)
                elif p.get("stopped"):
                    rgb = (145, 145, 145)
                pygame.draw.circle(self.screen, WHITE, (x, y), 17)
                pygame.draw.circle(self.screen, rgb, (x, y), 14)
                pygame.draw.circle(self.screen, BLACK, (x, y), 14, width=2)
                initial = str(p.get("name", "?"))[:1].upper()
                label = self.font_small.render(initial, True, WHITE)
                self.screen.blit(label, label.get_rect(center=(x, y)))

    def draw_players_panel(self, x: int, y: int) -> int:
        if not self.state:
            return y
        self.draw_text("Jogadores", (x, y), self.font_big, DARK)
        y += 42
        current_id = self.state.get("current_player_id")
        for p in self.state.get("players", []):
            color = p.get("color") or "?"
            rgb = PLAYER_RGB.get(color, (100, 100, 100))
            prefix = "▶ " if p.get("id") == current_id else "  "
            status = ""
            if p.get("eliminated"):
                status = " eliminado"
            elif p.get("stopped"):
                status = " parou"
            elif int(p.get("skip_turns") or 0) > 0:
                status = " perde próxima"
            elif not p.get("connected", True):
                status = " offline"
            pygame.draw.circle(self.screen, rgb, (x + 12, y + 12), 10)
            line = f"{prefix}{p.get('name')} | casa {track_label(int(p.get('position', 0)), self.state.get('game_mode', 'dice_board') if self.state else 'dice_board')} | {p.get('credits')} créditos{status}"
            self.draw_text(line, (x + 30, y), self.font_small, TEXT)
            y += 28
        return y + 8


    def draw_players_compact_panel(self, x: int, y: int, max_width: int = 705) -> int:
        """Desenha os jogadores em formato compacto durante a partida.

        A tela 1280x720 tem pouco espaço vertical no painel direito. O painel
        antigo colocava o título "Jogadores" grande e uma linha por jogador,
        empurrando pergunta, botões e histórico para a mesma região. Este
        formato em duas colunas evita sobreposição.
        """
        if not self.state:
            return y

        self.draw_text("Jogadores", (x, y), self.font, DARK)
        y += 28
        current_id = self.state.get("current_player_id")
        players = list(self.state.get("players", []))
        col_w = max_width // 2
        row_h = 24

        for idx, p in enumerate(players):
            col = idx % 2
            row = idx // 2
            px = x + col * col_w
            py = y + row * row_h
            color = p.get("color") or "?"
            rgb = PLAYER_RGB.get(color, (100, 100, 100))
            prefix = "▶ " if p.get("id") == current_id else "  "
            status = ""
            if p.get("eliminated"):
                status = " elim."
            elif p.get("stopped"):
                status = " parou"
            elif int(p.get("skip_turns") or 0) > 0:
                status = " perde próxima"
            elif not p.get("connected", True):
                status = " off"
            pygame.draw.circle(self.screen, rgb, (px + 10, py + 11), 9)
            line = f"{prefix}{p.get('name')} | casa {track_label(int(p.get('position', 0)), self.state.get('game_mode', 'dice_board') if self.state else 'dice_board')} | {p.get('credits')} cr.{status}"
            self.draw_text(line[:42], (px + 26, py), self.font_small, TEXT)

        rows = max(1, math.ceil(len(players) / 2))
        return y + rows * row_h + 8

    def draw_lobby(self) -> None:
        right = pygame.Rect(500, 20, 755, 682)
        pygame.draw.rect(self.screen, PANEL, right, border_radius=18)
        pygame.draw.rect(self.screen, DARK, right, width=2, border_radius=18)
        x, y = right.x + 30, right.y + 24

        if self.logo_img:
            self.screen.blit(self.logo_img, (x + 160, y - 40))
            y += 140
        else:
            self.draw_text("GREEN IMPACT", (x, y), self.font_title, DARK)
            y += 65

        self.draw_text(f"Sala: {self.room_code or 'conectando...'}", (x, y), self.font_big, DARK)
        y += 48
        self.draw_wrapped("Escolha uma cor. Quando todos escolherem, o criador da sala pode iniciar a partida.", x, y, 70, self.font_small)
        y += 56

        players = self.state.get("players", []) if self.state else []
        chosen = {p.get("color") for p in players if p.get("color")}
        me = self.me()
        for i, color in enumerate(COLOR_ORDER):
            bx = x + (i % 2) * 190
            by = y + (i // 2) * 62
            taken_by_me = bool(me and me.get("color") == color)
            enabled = color not in chosen or taken_by_me
            label = COLOR_NAMES[color] + (" [X]" if taken_by_me else "")
            self.add_button(
                pygame.Rect(bx, by, 160, 44),
                label,
                lambda c=color: self.fire_and_forget({"type": "choose_color", "color": c}),
                enabled=enabled,
            )
        y += 140
        y = self.draw_players_panel(x, y)

        is_host = bool(me and me.get("is_host"))
        can_start = bool(is_host and me and me.get("color") and all(p.get("color") for p in players))
        self.add_button(pygame.Rect(x, right.bottom - 80, 220, 52), "Iniciar partida", lambda: self.fire_and_forget({"type": "start"}), enabled=can_start)
        self.draw_wrapped("Dica: abra outro cliente com o mesmo código da sala para jogar em rede.", x + 250, right.bottom - 76, 50, self.font_small)

    def draw_game(self) -> None:
        right = pygame.Rect(500, 20, 755, 682)
        pygame.draw.rect(self.screen, PANEL, right, border_radius=18)
        pygame.draw.rect(self.screen, DARK, right, width=2, border_radius=18)
        x, y = right.x + 24, right.y + 18
        self.draw_text(f"Sala {self.room_code}", (x, y), self.font_big, DARK)
        y += 38
        y = self.draw_players_compact_panel(x, y)

        if not self.state:
            return
        q = self.state.get("current_question")
        cp = self.current_player()
        my_turn = self.is_my_turn()

        # Áreas fixas do painel. Assim a pergunta, os botões e o histórico
        # nunca disputam o mesmo espaço, mesmo com 4 jogadores.
        content_w = 705
        log_top = right.bottom - 92
        button_y = log_top - 48

        if cp:
            self.draw_text(f"Vez: {cp.get('name')}", (x, y), self.font_small, DARK)
        else:
            self.draw_text("Aguardando próxima jogada...", (x, y), self.font_small, DARK)
        y += 26

        remaining = None
        if self.state.get("deadline_ts"):
            remaining = max(0, int(float(self.state["deadline_ts"]) - (time.time() + self.server_delta)))
            self.draw_text(f"Tempo: {remaining}s", (x, y), self.font_big, RED if remaining <= 10 else DARK)
            y += 38

        if q:
            qid = str(q.get("id"))
            if my_turn and remaining == 0 and self.timeout_sent_for_question != qid:
                self.timeout_sent_for_question = qid
                self.fire_and_forget({"type": "timeout"})
            elif remaining and remaining > 0:
                self.timeout_sent_for_question = None

            diff = q.get("difficulty", "")
            diff_label = {"easy": "Fácil / Verde", "medium": "Médio / Amarelo", "hard": "Difícil / Vermelho"}.get(diff, diff)
            self.draw_text(f"Pergunta: {diff_label}", (x, y), self.font_small, DARK)
            y += 24

            # Alturas compactas para caber tudo sem sobreposição.
            question_h = 92
            option_h = 36
            option_gap = 8
            question_rect = pygame.Rect(x, y, content_w, question_h)
            pygame.draw.rect(self.screen, WHITE, question_rect, border_radius=12)
            pygame.draw.rect(self.screen, (190, 204, 170), question_rect, width=2, border_radius=12)
            self.draw_wrapped(q.get("prompt", ""), x + 14, y + 12, 74, self.font_small, TEXT, 20)
            y += question_h + 16

            eliminated = set(q.get("eliminated_options") or [])
            letters = ["A", "B", "C", "D"]
            options = q.get("options") or []
            for idx, option in enumerate(options):
                oy = y + idx * (option_h + option_gap)
                disabled = idx in eliminated or not my_turn
                text = f"{letters[idx]}) {option}"
                self.add_button(
                    pygame.Rect(x, oy, content_w, option_h),
                    text[:92],
                    lambda i=idx: self.fire_and_forget({"type": "answer", "answer_index": i}),
                    enabled=not disabled,
                )

            # Os botões de ação ficam acima do histórico reservado no rodapé.
            used_helps = set((cp or {}).get("used_helps") or [])
            help_used_this_turn = bool(self.state.get("help_used_this_turn"))
            saldo = int((cp or {}).get("credits", 0))
            can_buy_help = my_turn and not help_used_this_turn and saldo >= HELP_COST
            self.add_button(pygame.Rect(x, button_y, 120, 38), "Parar", lambda: self.fire_and_forget({"type": "stop"}), enabled=my_turn)
            self.add_button(pygame.Rect(x + 130, button_y, 150, 38), "Eliminar 2" if "eliminate2" not in used_helps else "Eliminar 2 (usada)", lambda: self.fire_and_forget({"type": "help", "help": "eliminate2"}), enabled=can_buy_help and "eliminate2" not in used_helps)
            self.add_button(pygame.Rect(x + 290, button_y, 150, 38), "Pesquisa" if "research" not in used_helps else "Pesquisa (usada)", lambda: self.fire_and_forget({"type": "help", "help": "research"}), enabled=can_buy_help and "research" not in used_helps)
            self.add_button(pygame.Rect(x + 450, button_y, 120, 38), "Especialista" if "expert" not in used_helps else "Esp. (usada)", lambda: self.fire_and_forget({"type": "help", "help": "expert"}), enabled=can_buy_help and "expert" not in used_helps)
            self.add_button(pygame.Rect(x + 580, button_y, 125, 38), "Pular" if "skip" not in used_helps else "Pular (usada)", lambda: self.fire_and_forget({"type": "help", "help": "skip"}), enabled=can_buy_help and "skip" not in used_helps)
        else:
            turn_phase = self.state.get("turn_phase")
            pending_diff = self.state.get("pending_question_difficulty")
            diff_label = {"easy": "Fácil / Verde", "medium": "Médio / Amarelo", "hard": "Difícil / Vermelho"}.get(pending_diff, pending_diff or "")

            if turn_phase == "awaiting_question" and cp:
                self.draw_text("Pausa antes da pergunta", (x, y), self.font_big, DARK)
                y += 48
                self.draw_wrapped(
                    f"{cp.get('name')} avançou para a casa {cp.get('position')}. A pergunta será {diff_label}. Clique em iniciar quando o jogador estiver pronto.",
                    x,
                    y,
                    72,
                    self.font_small,
                    TEXT,
                    24,
                )
                y += 96
                self.add_button(
                    pygame.Rect(x, y, 260, 48),
                    "Iniciar pergunta",
                    lambda: self.fire_and_forget({"type": "begin_question"}),
                    enabled=my_turn,
                )
                if not my_turn:
                    self.draw_wrapped("Aguardando o jogador da vez iniciar a pergunta.", x + 280, y + 8, 48, self.font_small, TEXT, 22)
            else:
                self.draw_wrapped("Aguardando o servidor preparar a próxima rodada...", x, y, 70, self.font_small)

        self.draw_event_log(500, 20, 755, 682)

    def draw_event_log(self, panel_x: int, panel_y: int, panel_w: int, panel_h: int) -> None:
        if not self.state:
            return

        # Histórico em área fixa no rodapé. Os botões de ação agora são
        # posicionados acima deste retângulo, evitando qualquer sobreposição.
        events = list(self.state.get("event_log") or [])[-2:]
        x = panel_x + 24
        y = panel_y + panel_h - 84

        log_rect = pygame.Rect(x - 8, y - 5, panel_w - 40, 78)
        pygame.draw.rect(self.screen, (239, 245, 218), log_rect, border_radius=10)
        pygame.draw.rect(self.screen, (170, 190, 150), log_rect, width=1, border_radius=10)

        self.draw_text("Histórico", (x, y), self.font_small, DARK)
        y += 22
        for ev in events:
            self.draw_wrapped("• " + ev, x, y, 82, self.font_small, TEXT, 18)
            y += 18

    def draw_ended(self) -> None:
        right = pygame.Rect(500, 20, 755, 682)
        pygame.draw.rect(self.screen, PANEL, right, border_radius=18)
        pygame.draw.rect(self.screen, DARK, right, width=2, border_radius=18)
        x, y = right.x + 34, right.y + 32
        self.draw_text("Fim de jogo", (x, y), self.font_title, DARK)
        y += 70
        ranking = self.state.get("ranking", []) if self.state else []
        for idx, row in enumerate(ranking, start=1):
            color = row.get("color") or "green"
            rgb = PLAYER_RGB.get(color, (100, 100, 100))
            pygame.draw.circle(self.screen, rgb, (x + 14, y + 15), 11)
            status = ""
            if row.get("eliminated"):
                status = " - eliminado"
            elif row.get("stopped"):
                status = " - parou"
            text = f"{idx}º {row.get('name')} | casa {row.get('display_position', row.get('position'))} | {row.get('credits')} créditos{status}"
            self.draw_text(text, (x + 35, y), self.font, TEXT)
            y += 38
        self.draw_event_log(500, 20, 755, 682)

    def draw_messages(self) -> None:
        if not self.messages:
            return
        messages = self.messages[-3:]
        y = WINDOW_H - 86
        for msg in messages:
            surf = self.font_small.render(msg[:120], True, WHITE)
            rect = pygame.Rect(20, y, surf.get_width() + 24, 25)
            pygame.draw.rect(self.screen, (20, 80, 48), rect, border_radius=8)
            self.screen.blit(surf, (rect.x + 12, rect.y + 4))
            y += 27

    def draw(self) -> None:
        self.buttons.clear()
        if self.in_menu:
            self.draw_menu()
        else:
            self.screen.fill(BG)
            self.draw_board()
            if not self.state:
                self.draw_connecting()
            elif self.state.get("status") == "waiting":
                self.draw_lobby()
            elif self.state.get("status") == "playing":
                self.draw_game()
            elif self.state.get("status") == "ended":
                self.draw_ended()
        self.draw_messages()
        pygame.display.flip()

    async def run(self) -> None:
        if not self.in_menu:
            await self.connect()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if self.in_menu:
                        for box in self.menu_inputs.values():
                            box.handle_key(event)
                    elif event.key == pygame.K_ESCAPE:
                        self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.in_menu:
                        clicked_input = False
                        for box in self.menu_inputs.values():
                            box.active = box.rect.collidepoint(event.pos)
                            clicked_input = clicked_input or box.active
                        if clicked_input:
                            continue
                    for btn in reversed(self.buttons):
                        if btn.rect.collidepoint(event.pos):
                            btn.click()
                            break

            self.draw()
            self.clock.tick(60)
            await asyncio.sleep(0)

        if self.ws:
            await self.ws.close()
        pygame.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cliente do Green Impact")
    parser.add_argument("--server", default="ws://127.0.0.1:8765", help="URL do servidor WebSocket")
    parser.add_argument("--name", default="Jogador", help="Nome do jogador")
    parser.add_argument("--room", default=None, help="Código da sala para entrar. Se omitido, cria uma sala nova.")
    parser.add_argument("--auto-connect", action="store_true", help="Conecta automaticamente usando os argumentos acima, sem abrir o menu.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = GreenImpactClient(args.server, args.name, args.room, start_in_menu=not args.auto_connect)
    asyncio.run(client.run())


if __name__ == "__main__":
    main()
