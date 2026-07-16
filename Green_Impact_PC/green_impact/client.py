from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import socket
import textwrap
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pygame
import websockets

from .common import COLOR_LABELS, PLAYER_RGB
from .rules import HELP_COST, RESEARCH_BONUS_SECONDS, track_label

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
ANSWER_FILL = (248, 250, 245)
HELP_FILL = (247, 230, 161)
HELP_CARD = (255, 248, 210)
WARNING_FILL = (255, 230, 210)
SUCCESS_FILL = (220, 244, 214)
ERROR_FILL = (255, 218, 214)
INFO_FILL = (220, 238, 250)
SOFT_BORDER = (170, 190, 150)

COLOR_ORDER = ["green", "yellow", "red", "blue"]
COLOR_NAMES = {"green": "Verde", "yellow": "Amarelo", "red": "Vermelho", "blue": "Azul"}

DEFAULT_SERVER_HOST = "147.15.100.214"
DEFAULT_SERVER_PORT = "8765"
LOCALHOST = "127.0.0.1"

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

# Novo tabuleiro (PDF Tabuleiro.pdf), renderizado em assets/board_new.jpg.
NEW_BOARD_ORIGINAL_W = 2382
NEW_BOARD_ORIGINAL_H = 1684
NEW_PATH = {
    0: (350, 1442),   # INÍCIO
    1: (720, 1442),   # casa 1
    2: (1070, 1420),  # sorte/revés entre 1 e 2
    3: (1454, 1210),  # casa 2
    4: (1582, 884),   # casa 3
    5: (1361, 663),   # casa 4
    6: (1010, 620),   # sorte/revés entre 4 e 5
    7: (954, 1001),   # casa 5
    8: (582, 989),    # casa 6
    9: (268, 698),    # casa 7
    10: (245, 470),   # sorte/revés entre 7 e 8
    11: (558, 326),   # casa 8
    12: (1105, 337),  # casa 9
    13: (1559, 419),  # casa 10
    14: (1884, 593),  # casa 11
    15: (1900, 840),  # sorte/revés entre 11 e 12
    16: (2210, 465),  # casa 12
    17: (2210, 190),  # FIM
}


def split_server_url(server_url: str) -> tuple[str, str]:
    """Extrai host e porta de uma URL ws://host:porta para preencher o menu."""
    value = (server_url or "").replace("ws://", "").replace("wss://", "")
    if "/" in value:
        value = value.split("/", 1)[0]
    if ":" in value:
        host, port = value.rsplit(":", 1)
        return host or DEFAULT_SERVER_HOST, port or DEFAULT_SERVER_PORT
    return value or DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT


def build_server_url(host: str, port: str) -> str:
    host = (host or DEFAULT_SERVER_HOST).strip()
    port = (port or DEFAULT_SERVER_PORT).strip()
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
    def __init__(
        self,
        rect: pygame.Rect,
        text: str,
        callback: Callable[[], None],
        enabled: bool = True,
        fill_color: tuple[int, int, int] | None = None,
        hover_color: tuple[int, int, int] | None = None,
        border_color: tuple[int, int, int] | None = None,
        text_color: tuple[int, int, int] | None = None,
        font: pygame.font.Font | None = None,
    ):
        self.rect = rect
        self.text = text
        self.callback = callback
        self.enabled = enabled
        self.fill_color = fill_color
        self.hover_color = hover_color
        self.border_color = border_color
        self.text_color = text_color
        self.font = font

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, small: bool = False) -> None:
        mouse = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse)
        if not self.enabled:
            fill = (200, 205, 188)
            border = DISABLED
            color = (120, 120, 120)
        else:
            fill = self.hover_color if hover and self.hover_color else (self.fill_color or ((226, 238, 203) if hover else (239, 245, 218)))
            border = self.border_color or DARK
            color = self.text_color or DARK
        pygame.draw.rect(screen, fill, self.rect, border_radius=12)
        pygame.draw.rect(screen, border, self.rect, width=2, border_radius=12)

        draw_font = self.font or font
        lines = str(self.text).split("\n")
        rendered = [draw_font.render(line, True, color) for line in lines]
        line_gap = 2
        total_h = sum(surface.get_height() for surface in rendered) + line_gap * max(0, len(rendered) - 1)
        y = self.rect.centery - total_h // 2
        for surface in rendered:
            screen.blit(surface, surface.get_rect(centerx=self.rect.centerx, y=y))
            y += surface.get_height() + line_gap

    def click(self) -> None:
        if self.enabled:
            self.callback()


class GearButton(Button):
    """Botão de engrenagem desenhado com primitivas do pygame.

    O ícone não depende de fonte ou emoji, então funciona da mesma forma no
    Windows, Android, iOS e macOS.
    """

    def __init__(self, rect: pygame.Rect, callback: Callable[[], None], enabled: bool = True):
        super().__init__(rect, "", callback, enabled)

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
        center = self.rect.center
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            inner = (center[0] + int(math.cos(rad) * 11), center[1] + int(math.sin(rad) * 11))
            outer = (center[0] + int(math.cos(rad) * 17), center[1] + int(math.sin(rad) * 17))
            pygame.draw.line(screen, color, inner, outer, width=5)
        pygame.draw.circle(screen, color, center, 12, width=4)
        pygame.draw.circle(screen, fill, center, 4)


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
        self.ui_mode = "home" if start_in_menu else "game"  # home, connection, how_to_play, game
        self.rules_return_context: tuple[bool, str] | None = None
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
        self.show_server_settings = False
        self.local_server_thread: threading.Thread | None = None
        self.local_server_error: str | None = None
        self.local_server_port = 8765
        self.lan_ip = get_lan_ip()
        self.create_game_mode = "dice_board"
        self.create_local_count: int | None = None
        self.local_count = 2
        self.create_local_names: list[str] = []
        self.local_name_inputs: list[InputBox] = []
        self.dice_animating = False
        self.dice_revealing = False
        self.dice_value = 1
        self.dice_final_value = 1
        self.dice_spin_end = 0.0
        self.dice_reveal_end = 0.0
        self.dice_roll_sent = False

        pygame.init()
        pygame.display.set_caption("Green Impact - Uma Jornada Sustentável")
        try:
            pygame.display.set_icon(pygame.image.load(str(ASSET_DIR / "app_icon.png")))
        except Exception:
            pass
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 22)
        self.font_small = pygame.font.SysFont("arial", 18)
        self.font_tiny = pygame.font.SysFont("arial", 15)
        self.font_button_small = pygame.font.SysFont("arial", 16)
        self.font_turn = pygame.font.SysFont("arial", 27, bold=True)
        self.font_big = pygame.font.SysFont("arial", 34, bold=True)
        self.font_title = pygame.font.SysFont("arial", 44, bold=True)

        self.board_rect = pygame.Rect(20, 20, 455, 682)
        self.board_new_rect = pygame.Rect(16, 150, 500, 354)
        # No jogo com dado, o tabuleiro novo é horizontal. Por isso há uma
        # versão maior e mais larga usada durante a partida.
        self.board_new_game_rect = pygame.Rect(16, 88, 720, 509)
        self.board_img = self.load_image(ASSET_DIR / "board.jpg", self.board_rect.size)
        self.board_new_img = self.load_image(ASSET_DIR / "board_new.jpg", self.board_new_rect.size)
        self.board_new_game_img = self.load_image(ASSET_DIR / "board_new.jpg", self.board_new_game_rect.size)
        self.logo_img = self.load_image(ASSET_DIR / "logo.png", (320, 160), keep_alpha=True)

        initial_host, initial_port = split_server_url(server_url or f"ws://{DEFAULT_SERVER_HOST}:{DEFAULT_SERVER_PORT}")
        # Campos do menu. Eles ficam mais abaixo para não sobrepor o título/descrição.
        self.menu_inputs: dict[str, InputBox] = {
            "name": InputBox(pygame.Rect(565, 310, 270, 42), "Seu nome", name or "Jogador"),
            "host": InputBox(pygame.Rect(565, 382, 270, 42), "IP do servidor", initial_host),
            "port": InputBox(pygame.Rect(865, 382, 120, 42), "Porta", initial_port),
            "room": InputBox(pygame.Rect(565, 454, 190, 42), "Código da sala", (room or "").upper()),
        }
        self.home_name_input = InputBox(pygame.Rect(610, 382, 300, 42), "Seu nome", name or "Jogador")
        self.ensure_local_name_inputs()

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
        host = self.menu_inputs["host"].value.strip() or DEFAULT_SERVER_HOST
        port = self.menu_inputs["port"].value.strip() or DEFAULT_SERVER_PORT
        room = self.menu_inputs["room"].value.strip().upper()

        if not create_room and not room:
            self.connection_error = "Digite o código da sala para entrar."
            self.messages.append("Erro: digite o código da sala para entrar.")
            return

        self.create_game_mode = "dice_board"
        self.create_local_count = None
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
            self.messages.append(f"Conectando em {self.server_url}...")
            self.ws = await websockets.connect(self.server_url)
            asyncio.create_task(self.listen())
            self.in_menu = False
            self.ui_mode = "game"
            if self.join_room:
                await self.send({"type": "join", "room": self.join_room, "name": self.name})
            elif self.create_local_count:
                await self.send({"type": "create_local", "name": self.name, "count": self.create_local_count, "names": self.create_local_names})
            else:
                await self.send({"type": "create", "name": self.name, "game_mode": self.create_game_mode})
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
                    monitor_task = asyncio.create_task(local_server.deadline_monitor())
                    try:
                        async with websockets.serve(local_server.handler, "0.0.0.0", port):
                            await asyncio.Future()
                    finally:
                        monitor_task.cancel()
                        try:
                            await monitor_task
                        except asyncio.CancelledError:
                            pass

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
        port_text = self.menu_inputs["port"].value.strip() or DEFAULT_SERVER_PORT
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
        self.menu_inputs["host"].value = LOCALHOST
        await self.connect_to(f"ws://{LOCALHOST}:{port}", name, None)

    async def back_to_menu(self) -> None:
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None
        self.state = None
        self.you = None
        self.room_code = None
        self.in_menu = True
        self.ui_mode = "home"
        self.connecting = False

    async def open_rules_from_game(self) -> None:
        """Abre as regras sem sair da sala atual.

        Antes, este botão chamava back_to_menu(), então qualquer clique em
        "Como jogar/Regras" derrubava a conexão e voltava para o menu.
        Agora guardamos a tela anterior para que o botão Voltar retorne ao
        estado exato de onde o jogador abriu as regras: lobby, partida, fim
        de jogo, conexão ou menu principal.
        """
        if self.ui_mode != "how_to_play":
            self.rules_return_context = (self.in_menu, self.ui_mode)
        self.in_menu = True
        self.ui_mode = "how_to_play"

    def close_rules(self) -> None:
        if self.rules_return_context is not None:
            self.in_menu, self.ui_mode = self.rules_return_context
        else:
            self.in_menu = True
            self.ui_mode = "home"
        self.rules_return_context = None

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
                    old_question = (self.state or {}).get("current_question") or {}
                    self.state = data.get("room") or {}
                    new_question = self.state.get("current_question") or {}
                    if old_question.get("id") != new_question.get("id"):
                        self.timeout_sent_for_question = None
                    if self.state:
                        self.room_code = self.state.get("code") or self.room_code
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

    def start_dice_animation(self) -> None:
        """Anima o dado, revela o número sorteado por 1 segundo e só então move."""
        if self.dice_animating:
            return
        self.dice_animating = True
        self.dice_revealing = False
        self.dice_roll_sent = False
        self.dice_final_value = random.randint(1, 6)
        self.dice_value = random.randint(1, 6)
        now = time.time()
        self.dice_spin_end = now + 0.90
        self.dice_reveal_end = now + 1.90

    def update_dice_animation(self) -> None:
        if not self.dice_animating:
            return
        now = time.time()
        if not self.dice_revealing and now < self.dice_spin_end:
            # Troca o número rapidamente durante a rolagem.
            self.dice_value = random.randint(1, 6)
            return
        if not self.dice_revealing:
            # Resultado revelado: fica parado na tela por 1 segundo.
            self.dice_revealing = True
            self.dice_value = self.dice_final_value
            return
        if now >= self.dice_reveal_end and not self.dice_roll_sent:
            self.dice_roll_sent = True
            self.dice_animating = False
            self.dice_revealing = False
            self.fire_and_forget({"type": "roll", "roll": self.dice_final_value})

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
        if not self.state or not self.you:
            return False
        if self.state.get("local_multiplayer"):
            return True
        return self.state.get("current_player_id") == self.you

    def current_new_board_rect(self) -> pygame.Rect:
        """Usa o tabuleiro novo grande apenas durante a partida.

        Em lobby/telas de opção, a versão anterior usava o tabuleiro grande
        e ele ficava por baixo do painel da direita. Aqui o tabuleiro compacto
        fica totalmente visível à esquerda; durante a partida ele volta ao
        tamanho máximo permitido pelo HUD próprio do modo com dado.
        """
        if self.state and self.state.get("status") == "playing":
            return self.board_new_game_rect
        return self.board_new_rect

    def board_to_screen(self, color: str, position: int) -> tuple[int, int]:
        """Converte a casa do jogador para coordenadas reais na tela.

        O tabuleiro novo possui outro formato e uma trilha em espiral, então
        não pode usar as mesmas colunas fixas do tabuleiro antigo. No modo
        dice_board, cada casa usa um ponto manualmente medido no novo PDF.
        """
        if self.state and self.state.get("game_mode") != "classic":
            pos = max(0, min(17, int(position)))
            ox, oy = NEW_PATH.get(pos, NEW_PATH[0])
            rect = self.current_new_board_rect()
            x = rect.x + int((ox / NEW_BOARD_ORIGINAL_W) * rect.w)
            y = rect.y + int((oy / NEW_BOARD_ORIGINAL_H) * rect.h)
            return x, y

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

    def add_button(
        self,
        rect: pygame.Rect,
        text: str,
        callback: Callable[[], None],
        enabled: bool = True,
        fill_color: tuple[int, int, int] | None = None,
        hover_color: tuple[int, int, int] | None = None,
        border_color: tuple[int, int, int] | None = None,
        text_color: tuple[int, int, int] | None = None,
        font: pygame.font.Font | None = None,
    ) -> None:
        btn = Button(
            rect, text, callback, enabled,
            fill_color=fill_color, hover_color=hover_color,
            border_color=border_color, text_color=text_color, font=font,
        )
        self.buttons.append(btn)
        btn.draw(self.screen, self.font_small)

    def add_gear_button(self, rect: pygame.Rect, callback: Callable[[], None], enabled: bool = True) -> None:
        btn = GearButton(rect, callback, enabled)
        self.buttons.append(btn)
        btn.draw(self.screen, self.font_small)

    def menu_input_keys(self) -> tuple[str, ...]:
        """Retorna apenas os campos que podem receber foco na tela atual."""
        return ("host", "port") if self.show_server_settings else ("name", "room")

    def toggle_server_settings(self) -> None:
        self.show_server_settings = not self.show_server_settings
        for box in self.menu_inputs.values():
            box.active = False
        self.connection_error = None

    def reset_server_settings(self) -> None:
        self.menu_inputs["host"].value = DEFAULT_SERVER_HOST
        self.menu_inputs["port"].value = DEFAULT_SERVER_PORT
        self.connection_error = None

    def apply_server_settings(self) -> None:
        host = self.menu_inputs["host"].value.strip()
        port_text = self.menu_inputs["port"].value.strip() or DEFAULT_SERVER_PORT
        if not host:
            self.connection_error = "Informe o IP ou endereço do servidor."
            return
        if not host.startswith(("ws://", "wss://")):
            try:
                port = int(port_text)
            except ValueError:
                self.connection_error = "A porta precisa ser um número."
                return
            if not 1 <= port <= 65535:
                self.connection_error = "A porta deve estar entre 1 e 65535."
                return
            port_text = str(port)
        self.menu_inputs["host"].value = host
        self.menu_inputs["port"].value = port_text
        self.server_url = build_server_url(host, port_text)
        self.connection_error = None
        self.show_server_settings = False
        for box in self.menu_inputs.values():
            box.active = False

    def draw_server_settings_overlay(self, panel: pygame.Rect) -> None:
        shade = pygame.Surface(panel.size, pygame.SRCALPHA)
        shade.fill((18, 77, 48, 58))
        self.screen.blit(shade, panel.topleft)

        card = pygame.Rect(panel.x + 72, panel.y + 178, panel.w - 144, 360)
        pygame.draw.rect(self.screen, WHITE, card, border_radius=18)
        pygame.draw.rect(self.screen, DARK, card, width=3, border_radius=18)
        x = card.x + 34
        y = card.y + 28
        self.draw_text("Servidor online", (x, y), self.font_big, DARK)
        self.draw_wrapped(
            "Digite manualmente o IP ou domínio do servidor. A porta padrão é 8765. Também é possível informar uma URL completa começando com ws:// ou wss://.",
            x,
            y + 46,
            62,
            self.font_small,
            TEXT,
            21,
        )

        host_box = self.menu_inputs["host"]
        port_box = self.menu_inputs["port"]
        host_box.rect = pygame.Rect(x, card.y + 150, 330, 42)
        port_box.rect = pygame.Rect(x + 350, card.y + 150, 120, 42)
        host_box.label = "IP ou endereço"
        port_box.label = "Porta"
        host_box.draw(self.screen, self.font, self.font_small)
        port_box.draw(self.screen, self.font, self.font_small)

        preview = build_server_url(host_box.value, port_box.value)
        self.draw_wrapped(f"Conexão: {preview}", x, card.y + 212, 64, self.font_small, DARK, 20)
        if self.connection_error:
            self.draw_wrapped("Erro: " + self.connection_error, x, card.y + 242, 64, self.font_small, RED, 20)

        self.add_button(pygame.Rect(x, card.bottom - 66, 150, 42), "Salvar", self.apply_server_settings, enabled=True)
        self.add_button(pygame.Rect(x + 166, card.bottom - 66, 150, 42), "Usar padrão", self.reset_server_settings, enabled=True)
        self.add_button(pygame.Rect(x + 332, card.bottom - 66, 138, 42), "Fechar", self.toggle_server_settings, enabled=True)

    def open_multiplayer_menu(self) -> None:
        self.ui_mode = "connection"
        self.create_game_mode = "dice_board"
        self.create_local_count = None
        self.menu_inputs["name"].value = self.home_name_input.value.strip() or "Jogador"
        self.connection_error = None
        self.show_server_settings = False

    def ensure_local_name_inputs(self) -> None:
        """Garante um campo de nome independente para cada jogador local."""
        defaults = ["Jogador 1", "Jogador 2", "Jogador 3", "Jogador 4"]
        while len(self.local_name_inputs) < 4:
            idx = len(self.local_name_inputs)
            self.local_name_inputs.append(InputBox(pygame.Rect(0, 0, 260, 40), f"Nome do jogador {idx + 1}", defaults[idx]))

    def local_player_names(self) -> list[str]:
        self.ensure_local_name_inputs()
        names = []
        for i in range(self.local_count):
            value = self.local_name_inputs[i].value.strip() or f"Jogador {i + 1}"
            names.append(value[:20])
        return names

    async def start_single_player(self) -> None:
        self.menu_inputs["name"].value = self.home_name_input.value.strip() or "Jogador"
        self.menu_inputs["host"].value = DEFAULT_SERVER_HOST
        self.menu_inputs["port"].value = DEFAULT_SERVER_PORT
        self.menu_inputs["room"].value = ""
        self.create_game_mode = "classic"
        self.create_local_count = None
        await self.start_local_and_create()

    def open_local_multiplayer_setup(self) -> None:
        self.ui_mode = "local_setup"
        self.connection_error = None

    async def start_local_multiplayer(self) -> None:
        names = self.local_player_names()
        self.menu_inputs["name"].value = names[0] if names else "Jogador"
        self.menu_inputs["host"].value = LOCALHOST
        self.menu_inputs["port"].value = DEFAULT_SERVER_PORT
        self.menu_inputs["room"].value = ""
        self.create_game_mode = "dice_board"
        self.create_local_count = self.local_count
        self.create_local_names = names
        await self.start_local_and_create()
        self.create_local_count = None
        self.create_local_names = []

    def draw_home_menu(self) -> None:
        self.screen.fill(BG)
        if self.board_img:
            self.screen.blit(self.board_img, self.board_rect)
        else:
            pygame.draw.rect(self.screen, (210, 230, 190), self.board_rect, border_radius=16)

        panel = pygame.Rect(535, 20, 720, 682)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=18)
        pygame.draw.rect(self.screen, DARK, panel, width=2, border_radius=18)
        x = panel.x + 48

        if self.logo_img:
            self.screen.blit(self.logo_img, (x + 170, panel.y + 14))
        else:
            self.draw_text("GREEN IMPACT", (x + 180, panel.y + 42), self.font_title, DARK)

        self.draw_text("Menu principal", (x, panel.y + 178), self.font_big, DARK)
        self.draw_wrapped(
            "Escolha se quer jogar sozinho, criar/entrar em uma partida multiplayer ou ler as regras do Green Impact.",
            x,
            panel.y + 222,
            72,
            self.font_small,
            TEXT,
            22,
        )

        self.home_name_input.draw(self.screen, self.font, self.font_small)

        self.add_button(
            pygame.Rect(610, 438, 300, 44),
            "Um jogador",
            lambda: asyncio.create_task(self.start_single_player()),
            enabled=not self.connecting,
        )
        self.add_button(
            pygame.Rect(610, 492, 300, 44),
            "Multijogador online",
            self.open_multiplayer_menu,
            enabled=not self.connecting,
        )
        self.add_button(
            pygame.Rect(610, 546, 300, 44),
            "Multijogador local",
            self.open_local_multiplayer_setup,
            enabled=not self.connecting,
        )
        self.add_button(
            pygame.Rect(610, 600, 300, 44),
            "Como jogar",
            lambda: asyncio.create_task(self.open_rules_from_game()),
            enabled=True,
        )

        self.draw_wrapped(
            f"No modo Um jogador, o jogo abre um servidor local automaticamente. IP local para multiplayer na mesma rede: {self.lan_ip}",
            x,
            640,
            82,
            self.font_small,
            TEXT,
            22,
        )
        if self.connection_error:
            self.draw_wrapped("Erro: " + self.connection_error, x, 668, 82, self.font_small, RED, 22)


    def draw_local_setup(self) -> None:
        self.screen.fill(BG)
        if self.board_new_img:
            self.screen.blit(self.board_new_img, self.board_new_rect)
        elif self.board_img:
            self.screen.blit(self.board_img, self.board_rect)

        self.ensure_local_name_inputs()
        panel = pygame.Rect(535, 20, 720, 682)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=18)
        pygame.draw.rect(self.screen, DARK, panel, width=2, border_radius=18)
        x = panel.x + 42
        y = panel.y + 34

        self.draw_text("Multijogador local", (x, y), self.font_title, DARK)
        y += 58
        y = self.draw_wrapped(
            "Escolha a quantidade de jogadores e informe o nome de cada um. Todos jogam no mesmo dispositivo.",
            x, y, 70, self.font_small, TEXT, 23,
        )
        y += 18

        self.draw_text(f"Quantidade: {self.local_count} jogadores", (x, y), self.font_big, DARK)
        y += 48
        for i, count in enumerate([2, 3, 4]):
            self.add_button(
                pygame.Rect(x + i * 150, y, 132, 44),
                f"{count}" + (" [X]" if self.local_count == count else ""),
                lambda c=count: setattr(self, "local_count", c),
                enabled=True,
            )
        y += 62

        self.draw_text("Nomes dos jogadores", (x, y), self.font_big, DARK)
        y += 42
        for i in range(self.local_count):
            bx = x + (i % 2) * 320
            by = y + (i // 2) * 74
            box = self.local_name_inputs[i]
            box.rect = pygame.Rect(bx, by + 24, 285, 40)
            box.label = f"Jogador {i + 1}"
            box.draw(self.screen, self.font, self.font_small)
        y += 160

        self.add_button(
            pygame.Rect(x, panel.bottom - 82, 260, 50),
            "Iniciar local",
            lambda: asyncio.create_task(self.start_local_multiplayer()),
            enabled=not self.connecting,
        )
        self.add_button(
            pygame.Rect(x + 280, panel.bottom - 82, 170, 50),
            "Voltar",
            lambda: setattr(self, "ui_mode", "home"),
            enabled=True,
        )
        self.add_button(
            pygame.Rect(x + 470, panel.bottom - 82, 170, 50),
            "Como jogar",
            lambda: asyncio.create_task(self.open_rules_from_game()),
            enabled=True,
        )
        if self.connection_error:
            self.draw_wrapped("Erro: " + self.connection_error, x, panel.bottom - 120, 72, self.font_small, RED, 22)

    def draw_how_to_play(self) -> None:
        self.screen.fill(BG)
        if self.board_img:
            self.screen.blit(self.board_img, self.board_rect)
        else:
            pygame.draw.rect(self.screen, (210, 230, 190), self.board_rect, border_radius=16)

        panel = pygame.Rect(535, 20, 720, 682)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=18)
        pygame.draw.rect(self.screen, DARK, panel, width=2, border_radius=18)
        x, y = panel.x + 36, panel.y + 28
        self.draw_text("Como jogar", (x, y), self.font_title, DARK)
        y += 58

        sections = [
            ("Objetivo", "Chegue primeiro à casa 10/FIM respondendo perguntas sobre sustentabilidade e ODS."),
            ("Turno", "No modo Um jogador, o peão avança 1 casa. No multijogador online/local, o jogador lança um dado e anda a quantidade sorteada."),
            ("Perguntas", "No novo tabuleiro multiplayer: casas 1 a 5 usam perguntas fáceis, 6 a 9 usam médias e 10 a 12 usam difíceis. O cronômetro começa quando a pergunta é iniciada."),
            ("Sorte/Revés", "Casas com símbolo de planta ativam um bônus ou revés de créditos de carbono em vez de pergunta."),
            ("Créditos", "Você começa com 3 créditos de carbono. Ao acertar, ganha créditos conforme a dificuldade. As ajudas custam 3 créditos."),
            ("Erro", "Ao errar, volta ao Início e perde todos os créditos. Se errar novamente depois do reinício, é eliminado."),
            ("Parar", "Volta para o início e perde metade do saldo."),
            ("Ajudas", "Eliminar 2 alternativas, Pesquisa, Especialista e Pular pergunta. Só é possível usar uma ajuda por rodada."),
            ("Vitória", "Vence quem completar o percurso primeiro. Se houver empate, ganha quem tiver mais créditos."),
        ]
        for title, body in sections:
            self.draw_text(title + ":", (x, y), self.font_small, DARK)
            y = self.draw_wrapped(body, x + 118, y, 66, self.font_small, TEXT, 20)
            y += 6
        self.add_button(pygame.Rect(x, panel.bottom - 62, 180, 44), "Voltar", self.close_rules, enabled=True)

    def draw_menu(self) -> None:
        self.screen.fill(BG)
        if self.board_img:
            self.screen.blit(self.board_img, self.board_rect)
        else:
            pygame.draw.rect(self.screen, (210, 230, 190), self.board_rect, border_radius=16)

        panel = pygame.Rect(535, 20, 720, 682)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=18)
        pygame.draw.rect(self.screen, DARK, panel, width=2, border_radius=18)
        x = panel.x + 48
        y = panel.y + 34

        if self.logo_img:
            self.screen.blit(self.logo_img, (x + 170, panel.y + 12))
            y = panel.y + 170
        else:
            self.draw_text("GREEN IMPACT", (x + 160, panel.y + 42), self.font_title, DARK)
            y = panel.y + 170

        self.draw_text("Multijogador online", (x, y), self.font_big, DARK)
        self.draw_text("Servidor", (panel.right - 160, y + 12), self.font_small, DARK)
        self.add_gear_button(
            pygame.Rect(panel.right - 82, y - 3, 48, 48),
            self.toggle_server_settings,
            enabled=not self.connecting,
        )
        y += 46
        self.draw_wrapped(
            "Crie uma sala ou entre usando o código recebido. Para trocar o servidor, abra a engrenagem ao lado do título.",
            x, y, 72, self.font_small, TEXT, 22,
        )
        y += 70

        name_box = self.menu_inputs["name"]
        name_box.rect = pygame.Rect(x, y + 24, 300, 42)
        name_box.label = "Seu nome"
        name_box.draw(self.screen, self.font, self.font_small)
        y += 86

        room_box = self.menu_inputs["room"]
        room_box.rect = pygame.Rect(x, y + 24, 210, 42)
        room_box.label = "Código da sala"
        room_box.draw(self.screen, self.font, self.font_small)
        self.draw_wrapped("O código aparece para quem criou a sala. Ex.: MDNI.", x + 230, y + 26, 44, self.font_small, TEXT, 21)
        y += 92

        controls_enabled = not self.connecting and not self.show_server_settings
        self.add_button(pygame.Rect(x, y, 230, 48), "Criar nova sala", lambda: asyncio.create_task(self.connect_from_menu(create_room=True)), enabled=controls_enabled)
        self.add_button(pygame.Rect(x + 250, y, 230, 48), "Entrar com código", lambda: asyncio.create_task(self.connect_from_menu(create_room=False)), enabled=controls_enabled)
        y += 62
        self.add_button(pygame.Rect(x, y, 260, 46), "Abrir servidor local", lambda: asyncio.create_task(self.start_local_and_create()), enabled=controls_enabled)
        self.add_button(pygame.Rect(x + 280, y, 140, 46), "Voltar", lambda: setattr(self, "ui_mode", "home"), enabled=not self.show_server_settings)
        self.add_button(pygame.Rect(x + 440, y, 160, 46), "Como jogar", lambda: asyncio.create_task(self.open_rules_from_game()), enabled=not self.show_server_settings)

        current_server = build_server_url(self.menu_inputs["host"].value, self.menu_inputs["port"].value)
        self.draw_wrapped(
            f"Servidor selecionado: {current_server}",
            x, panel.bottom - 70, 70, self.font_small, DARK, 20,
        )
        if self.connection_error and not self.show_server_settings:
            self.draw_wrapped("Erro: " + self.connection_error, x, panel.bottom - 112, 72, self.font_small, RED, 22)

        if self.show_server_settings:
            self.draw_server_settings_overlay(panel)

    def draw_connecting(self) -> None:
        self.screen.fill(BG)
        self.draw_board()
        right = pygame.Rect(535, 20, 720, 682)
        pygame.draw.rect(self.screen, PANEL, right, border_radius=18)
        pygame.draw.rect(self.screen, DARK, right, width=2, border_radius=18)
        x, y = right.x + 42, right.y + 230
        self.draw_text("Conectando...", (x, y), self.font_title, DARK)
        y += 62
        self.draw_wrapped(f"Servidor: {self.server_url}", x, y, 70, self.font_small)
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
        new_mode = bool(self.state and self.state.get("game_mode") != "classic")
        rect = self.current_new_board_rect() if new_mode else self.board_rect
        img = self.board_new_game_img if new_mode and self.state and self.state.get("status") == "playing" and self.board_new_game_img else (self.board_new_img if new_mode and self.board_new_img else self.board_img)
        if img:
            self.screen.blit(img, rect)
        else:
            pygame.draw.rect(self.screen, (210, 230, 190), rect, border_radius=16)
            self.draw_text("Tabuleiro", (rect.x + 150, rect.y + 20), self.font_big, DARK)

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

    def remaining_seconds(self) -> int:
        if not self.state or not self.state.get("current_question") or not self.state.get("deadline_ts"):
            return 0
        # Arredondar para cima impede o HUD de mostrar 0 antes do prazo real.
        return max(0, math.ceil(float(self.state["deadline_ts"]) - (time.time() + self.server_delta)))

    def draw_card(self, rect: pygame.Rect, fill: tuple[int, int, int], border: tuple[int, int, int] = DARK, width: int = 2, radius: int = 12) -> None:
        pygame.draw.rect(self.screen, fill, rect, border_radius=radius)
        pygame.draw.rect(self.screen, border, rect, width=width, border_radius=radius)

    def draw_centered(self, text: str, rect: pygame.Rect, font: pygame.font.Font, color: tuple[int, int, int] = TEXT) -> None:
        surface = font.render(str(text), True, color)
        self.screen.blit(surface, surface.get_rect(center=rect.center))

    def draw_turn_banner(self, x: int, y: int, width: int, cp: dict[str, Any] | None, my_turn: bool, compact: bool = False) -> int:
        height = 52 if compact else 58
        rect = pygame.Rect(x, y, width, height)
        self.draw_card(rect, (226, 240, 205), DARK, 2, 12)
        if not cp:
            self.draw_centered("Aguardando próximo jogador", rect, self.font_turn if not compact else self.font, DARK)
            return y + height + 7
        phase = (self.state or {}).get("turn_phase")
        if phase in {"turn_result", "luck_result"}:
            heading = f"RESULTADO DE {cp.get('name')}"
        elif my_turn and not (self.state or {}).get("local_multiplayer"):
            heading = f"SUA VEZ: {cp.get('name')}"
        else:
            heading = f"VEZ DE {cp.get('name')}"
        heading_font = self.font_turn if not compact else self.font
        heading_surface = heading_font.render(heading, True, DARK)
        self.screen.blit(heading_surface, heading_surface.get_rect(centerx=rect.centerx, y=rect.y + 5))
        details = f"casa {track_label(int(cp.get('position', 0)), (self.state or {}).get('game_mode', 'dice_board'))} | saldo: {cp.get('credits')} créditos"
        detail_surface = self.font_tiny.render(details, True, TEXT)
        self.screen.blit(detail_surface, detail_surface.get_rect(centerx=rect.centerx, bottom=rect.bottom - 5))
        return y + height + 7

    def draw_balance_card(self, x: int, y: int, width: int, cp: dict[str, Any] | None, compact: bool = False) -> int:
        height = 42 if compact else 48
        rect = pygame.Rect(x, y, width, height)
        self.draw_card(rect, (232, 244, 213), DARK, 2, 10)
        saldo = int((cp or {}).get("credits", 0))
        cost_color = DARK if saldo >= HELP_COST else RED
        cost = self.font_tiny.render(f"Cada ajuda custa {HELP_COST} créditos", True, cost_color)
        if compact:
            balance = self.font_button_small.render(f"SALDO DE CARBONO: {saldo} créditos", True, DARK)
            self.screen.blit(balance, (rect.x + 10, rect.y + 10))
        else:
            title = self.font_button_small.render("SALDO DE CARBONO", True, DARK)
            value = self.font.render(f"{saldo} créditos", True, DARK)
            self.screen.blit(title, (rect.x + 12, rect.y + 5))
            self.screen.blit(value, (rect.x + 190, rect.y + 3))
        self.screen.blit(cost, (rect.right - cost.get_width() - 10, rect.y + 12))
        return y + height + 6

    def draw_help_section(self, x: int, y: int, width: int, cp: dict[str, Any] | None, my_turn: bool, compact: bool = False) -> int:
        saldo = int((cp or {}).get("credits", 0))
        help_used = bool((self.state or {}).get("help_used_this_turn"))
        disabled = (not my_turn) or help_used or saldo < HELP_COST
        header_h = 27 if compact else 31
        btn_h = 32 if compact else 36
        gap = 6
        section_h = header_h + btn_h * 2 + gap * 3
        rect = pygame.Rect(x, y, width, section_h)
        self.draw_card(rect, HELP_CARD, (165, 120, 20), 2, 11)
        status = f"AJUDAS — custo {HELP_COST} cada; não são respostas"
        if help_used:
            status += " | já usada"
        elif saldo < HELP_COST:
            status += " | saldo insuficiente"
        self.draw_text(status, (x + 10, y + 5), self.font_tiny if compact else self.font_button_small, RED if disabled else DARK)
        col_gap = 7
        btn_w = (width - 20 - col_gap) // 2
        labels = [
            (f"Eliminar 2 respostas\nCusto: {HELP_COST}", {"type": "help", "help": "eliminate2"}),
            (f"Pesquisa +{RESEARCH_BONUS_SECONDS}s\nCusto: {HELP_COST}", {"type": "help", "help": "research"}),
            (f"Dica do especialista\nCusto: {HELP_COST}", {"type": "help", "help": "expert"}),
            (f"Pular pergunta\nCusto: {HELP_COST}", {"type": "help", "help": "skip"}),
        ]
        start_y = y + header_h
        for i, (label, payload) in enumerate(labels):
            bx = x + 7 + (i % 2) * (btn_w + col_gap)
            by = start_y + (i // 2) * (btn_h + gap)
            self.add_button(
                pygame.Rect(bx, by, btn_w, btn_h), label,
                lambda p=payload: self.fire_and_forget(p),
                enabled=not disabled,
                fill_color=HELP_FILL,
                hover_color=(252, 237, 174),
                border_color=(145, 105, 20),
                font=self.font_tiny,
            )
        return y + section_h + 6

    def draw_stop_section(self, x: int, y: int, width: int, my_turn: bool, compact: bool = False) -> int:
        height = 40 if compact else 44
        rect = pygame.Rect(x, y, width, height)
        self.draw_card(rect, WARNING_FILL, RED, 2, 10)
        self.draw_text("PARAR", (x + 10, y + 3), self.font_tiny, RED)
        self.draw_text("Volta ao início e perde metade do saldo", (x + 10, y + 20), self.font_tiny, TEXT)
        btn_w = 190 if width > 520 else 162
        self.add_button(
            pygame.Rect(rect.right - btn_w - 6, rect.y + 5, btn_w, rect.h - 10),
            "Parar", lambda: self.fire_and_forget({"type": "stop"}),
            enabled=my_turn, fill_color=ERROR_FILL, hover_color=(255, 226, 220),
            border_color=RED, text_color=RED, font=self.font_button_small,
        )
        return y + height + 4

    def draw_consequence(self, x: int, y: int, width: int, bottom: int, cp: dict[str, Any] | None, my_turn: bool, compact: bool = False) -> None:
        result = dict((self.state or {}).get("turn_result") or {})
        kind = str(result.get("kind") or "result")
        styles = {
            "correct": (SUCCESS_FILL, DARK, "RESPOSTA CORRETA"),
            "incorrect": (ERROR_FILL, RED, "RESPOSTA INCORRETA"),
            "timeout": (ERROR_FILL, RED, "TEMPO ESGOTADO"),
            "skipped": (INFO_FILL, DARK, "PERGUNTA PULADA"),
            "stopped": (WARNING_FILL, RED, "JOGADOR PAROU"),
            "luck_gain": (SUCCESS_FILL, DARK, "CONSEQUÊNCIA DA CASA"),
            "luck_loss": (WARNING_FILL, RED, "CONSEQUÊNCIA DA CASA"),
        }
        fill, accent, fallback = styles.get(kind, (INFO_FILL, DARK, "CONSEQUÊNCIA"))
        height = max(250, bottom - y - 58)
        rect = pygame.Rect(x, y, width, height)
        self.draw_card(rect, fill, accent, 3, 14)
        title = str(result.get("title") or fallback)
        self.draw_centered("CONSEQUÊNCIA", pygame.Rect(x, y + 8, width, 24), self.font_button_small, accent)
        self.draw_centered(title.upper(), pygame.Rect(x, y + 34, width, 38), self.font_turn if not compact else self.font, accent)
        cursor = y + 79
        message = str(result.get("message") or (self.state or {}).get("special_event") or "Rodada concluída.")
        cursor = self.draw_wrapped(message, x + 16, cursor, 72 if width > 550 else 48, self.font_small if not compact else self.font_tiny, TEXT, 20 if not compact else 18)
        old_credits, new_credits = result.get("old_credits"), result.get("new_credits")
        if old_credits is not None and new_credits is not None:
            delta = int(result.get("credit_delta") or 0)
            delta_txt = f"+{delta}" if delta > 0 else str(delta)
            self.draw_text(f"Saldo de carbono: {old_credits} → {new_credits} créditos ({delta_txt})", (x + 16, cursor + 4), self.font if not compact else self.font_small, DARK)
            cursor += 31
        old_pos, new_pos = result.get("old_position_label"), result.get("new_position_label")
        if old_pos and new_pos and old_pos != new_pos:
            self.draw_text(f"Posição: {old_pos} → {new_pos}", (x + 16, cursor), self.font_small, DARK)
            cursor += 27
        correct = str(result.get("correct_answer") or "").strip()
        if correct:
            cursor = self.draw_wrapped(f"Resposta correta: {correct}", x + 16, cursor, 70 if width > 550 else 47, self.font_small, DARK, 20)
        if result.get("eliminated"):
            self.draw_text("O jogador foi eliminado.", (x + 16, cursor + 2), self.font_small, RED)
        elif result.get("stopped"):
            self.draw_text("O jogador não participa das próximas rodadas.", (x + 16, cursor + 2), self.font_small, RED)
        self.add_button(
            pygame.Rect(x + 14, rect.bottom - 50, min(270, width - 28), 40),
            "Próximo jogador" if kind not in {"luck_gain", "luck_loss"} else "Continuar",
            lambda: self.fire_and_forget({"type": "continue"}),
            enabled=my_turn, fill_color=(232, 244, 213), font=self.font_button_small,
        )

    def draw_mini_event_log(self, x: int, y: int, width: int, compact: bool = False) -> int:
        events = list((self.state or {}).get("event_log") or [])[-1:]
        height = 44 if compact else 48
        rect = pygame.Rect(x, y, width, height)
        self.draw_card(rect, (239, 245, 218), SOFT_BORDER, 1, 9)
        self.draw_text("Histórico", (x + 8, y + 3), self.font_tiny, DARK)
        if events:
            line = "• " + str(events[-1])
            max_chars = 78 if width > 550 else 49
            shown = line if len(line) <= max_chars else line[: max_chars - 1] + "…"
            self.draw_text(shown, (x + 8, y + 22), self.font_tiny, TEXT)
        return y + height + 5

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

        self.draw_text("Jogadores", (x, y), self.font_tiny, DARK)
        y += 20
        current_id = self.state.get("current_player_id")
        players = list(self.state.get("players", []))
        col_w = max_width // 2
        row_h = 20

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
            elif not p.get("connected", True):
                status = " off"
            pygame.draw.circle(self.screen, rgb, (px + 9, py + 9), 7)
            line = f"{prefix}{p.get('name')} | casa {track_label(int(p.get('position', 0)), self.state.get('game_mode', 'dice_board') if self.state else 'dice_board')} | {p.get('credits')} cr.{status}"
            max_chars = 44 if col_w >= 300 else 27
            shown = line if len(line) <= max_chars else line[: max_chars - 1] + "…"
            self.draw_text(shown, (px + 21, py), self.font_tiny, TEXT)

        rows = max(1, math.ceil(len(players) / 2))
        return y + rows * row_h + 5

    def draw_lobby(self) -> None:
        right = pygame.Rect(535, 20, 720, 682)
        pygame.draw.rect(self.screen, PANEL, right, border_radius=18)
        pygame.draw.rect(self.screen, DARK, right, width=2, border_radius=18)
        x, y = right.x + 30, right.y + 24

        if self.logo_img:
            self.screen.blit(self.logo_img, (x + 160, y - 40))
            y += 140
        else:
            self.draw_text("GREEN IMPACT", (x, y), self.font_title, DARK)
            y += 65

        self.draw_text(f"Código da sala: {self.room_code or 'conectando...'}", (x, y), self.font_big, DARK)
        y += 48
        self.draw_wrapped("Compartilhe este código com os outros jogadores. Escolha uma cor; quando todos escolherem, o criador inicia a partida.", x, y, 70, self.font_small)
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
        self.add_button(pygame.Rect(x, right.bottom - 80, 190, 52), "Iniciar partida", lambda: self.fire_and_forget({"type": "start"}), enabled=can_start)
        self.add_button(pygame.Rect(x + 205, right.bottom - 80, 150, 52), "Menu", lambda: asyncio.create_task(self.back_to_menu()), enabled=True)
        self.add_button(pygame.Rect(x + 370, right.bottom - 80, 160, 52), "Como jogar", lambda: asyncio.create_task(self.open_rules_from_game()), enabled=True)
        self.draw_wrapped("Criar sala = abrir uma partida nova. Entrar = usar o código de uma sala já criada.", x + 540, right.bottom - 76, 22, self.font_small)

    def draw_game(self) -> None:
        if self.state and self.state.get("game_mode") != "classic":
            self.draw_game_dice_board()
            return
        right = pygame.Rect(535, 20, 720, 682)
        self.draw_card(right, PANEL, DARK, 2, 18)
        x, y = right.x + 20, right.y + 14
        content_w = right.w - 40
        self.draw_text(f"Sala {self.room_code}", (x, y), self.font_big, DARK)
        self.add_button(pygame.Rect(right.right - 170, y, 64, 32), "Menu", lambda: asyncio.create_task(self.back_to_menu()))
        self.add_button(pygame.Rect(right.right - 98, y, 76, 32), "Regras", lambda: asyncio.create_task(self.open_rules_from_game()))
        y += 38
        y = self.draw_players_compact_panel(x, y, max_width=content_w)
        if not self.state:
            return
        q = self.state.get("current_question")
        cp = self.current_player()
        my_turn = self.is_my_turn()
        phase = self.state.get("turn_phase")
        y = self.draw_turn_banner(x, y, content_w, cp, my_turn, compact=False)

        if phase in {"turn_result", "luck_result"}:
            self.draw_consequence(x, y, content_w, right.bottom - 10, cp, my_turn, compact=False)
            return

        if q:
            remaining = self.remaining_seconds()
            qid = str(q.get("id"))
            if my_turn and remaining <= 0 and self.timeout_sent_for_question != qid:
                self.timeout_sent_for_question = qid
                self.fire_and_forget({"type": "timeout"})
            elif remaining > 0:
                self.timeout_sent_for_question = None
            diff = q.get("difficulty", "")
            diff_label = {"easy": "Fácil / Verde", "medium": "Médio / Amarelo", "hard": "Difícil / Vermelho"}.get(diff, diff)
            self.draw_text(f"Tempo: {remaining}s", (x, y), self.font_big, RED if remaining <= 10 else DARK)
            self.draw_text(f"Pergunta: {diff_label}", (x + 210, y + 8), self.font_small, DARK)
            y += 38

            question_rect = pygame.Rect(x, y, content_w, 58)
            self.draw_card(question_rect, ANSWER_FILL, SOFT_BORDER, 2, 10)
            self.draw_wrapped(q.get("prompt", ""), x + 12, y + 7, 86, self.font_tiny, TEXT, 17)
            y += 64
            eliminated = set(q.get("eliminated_options") or [])
            letters = ["A", "B", "C", "D"]
            options = list(q.get("options") or [])
            option_h = 27
            for idx, option in enumerate(options):
                self.add_button(
                    pygame.Rect(x, y + idx * 31, content_w, option_h),
                    f"{letters[idx]}) {option}"[:96],
                    lambda i=idx: self.fire_and_forget({"type": "answer", "answer_index": i}),
                    enabled=my_turn and idx not in eliminated,
                    fill_color=ANSWER_FILL, hover_color=(234, 244, 226),
                    border_color=SOFT_BORDER, font=self.font_tiny,
                )
            y += len(options) * 31 + 2
            y = self.draw_balance_card(x, y, content_w, cp, compact=True)
            y = self.draw_help_section(x, y, content_w, cp, my_turn, compact=True)
            y = self.draw_mini_event_log(x, y, content_w, compact=True)
            self.draw_stop_section(x, y, content_w, my_turn, compact=True)
            return

        pending = self.state.get("pending_question_difficulty")
        diff_label = {"easy": "Fácil / Verde", "medium": "Médio / Amarelo", "hard": "Difícil / Vermelho"}.get(pending, pending or "")
        box = pygame.Rect(x, y, content_w, right.bottom - y - 72)
        self.draw_card(box, (239, 245, 218), SOFT_BORDER, 1, 13)
        bx, by = box.x + 16, box.y + 14
        if phase == "awaiting_roll" and cp:
            self.draw_centered("JOGAR DADO", pygame.Rect(bx, by, box.w - 32, 36), self.font_big, DARK)
            by += 43
            by = self.draw_wrapped(f"{cp.get('name')} está em {track_label(int(cp.get('position', 0)), self.state.get('game_mode', 'dice_board'))}. Jogue o dado para avançar.", bx, by, 70, self.font_small, TEXT, 22)
            dice_rect = pygame.Rect(bx, by + 8, 110, 86)
            self.draw_card(dice_rect, WHITE, DARK, 3, 17)
            self.draw_centered(str(self.dice_value if self.dice_animating else "?"), dice_rect, self.font_title, DARK)
            status = "Resultado exibido" if self.dice_revealing else ("Rolando..." if self.dice_animating else "Jogar dado")
            self.add_button(pygame.Rect(bx + 132, by + 25, 270, 48), status, self.start_dice_animation, enabled=my_turn and not self.dice_animating, font=self.font)
        elif phase == "awaiting_question" and cp:
            self.draw_centered("PRONTO PARA A PERGUNTA", pygame.Rect(bx, by, box.w - 32, 40), self.font_big, DARK)
            by += 50
            roll = f" Dado: {self.state.get('last_roll')}." if self.state.get("last_roll") else ""
            by = self.draw_wrapped(f"{cp.get('name')} está na casa {track_label(int(cp.get('position', 0)), self.state.get('game_mode', 'dice_board'))}.{roll} Nível: {diff_label}.", bx, by, 68, self.font, TEXT, 25)
            by += 8
            self.draw_text("O cronômetro começa somente ao iniciar a pergunta.", (bx, by), self.font_small, TEXT)
            by += 37
            self.add_button(pygame.Rect(bx, by, 280, 52), "Iniciar pergunta", lambda: self.fire_and_forget({"type": "begin_question"}), enabled=my_turn, font=self.font)
        else:
            self.draw_wrapped("Aguardando o servidor preparar a próxima rodada...", bx, by, 70, self.font_small, TEXT)
        self.draw_mini_event_log(x, right.bottom - 60, content_w)

    def draw_game_dice_board(self) -> None:
        """HUD do tabuleiro horizontal, com seções visuais compactas."""
        right = pygame.Rect(760, 20, 500, 682)
        self.draw_card(right, PANEL, DARK, 2, 18)
        x, y = right.x + 16, right.y + 12
        content_w = right.w - 32
        self.draw_text(f"Sala {self.room_code}", (x, y), self.font, DARK)
        self.add_button(pygame.Rect(right.right - 154, y, 58, 30), "Menu", lambda: asyncio.create_task(self.back_to_menu()), font=self.font_tiny)
        self.add_button(pygame.Rect(right.right - 90, y, 74, 30), "Regras", lambda: asyncio.create_task(self.open_rules_from_game()), font=self.font_tiny)
        y += 33
        y = self.draw_players_compact_panel(x, y, max_width=content_w)
        if not self.state:
            return
        q = self.state.get("current_question")
        cp = self.current_player()
        my_turn = self.is_my_turn()
        phase = self.state.get("turn_phase")
        y = self.draw_turn_banner(x, y, content_w, cp, my_turn, compact=True)

        if phase in {"turn_result", "luck_result"}:
            self.draw_consequence(x, y, content_w, right.bottom - 8, cp, my_turn, compact=True)
            return

        if q:
            remaining = self.remaining_seconds()
            qid = str(q.get("id"))
            if my_turn and remaining <= 0 and self.timeout_sent_for_question != qid:
                self.timeout_sent_for_question = qid
                self.fire_and_forget({"type": "timeout"})
            elif remaining > 0:
                self.timeout_sent_for_question = None
            diff = q.get("difficulty", "")
            diff_label = {"easy": "Fácil/Verde", "medium": "Médio/Amarelo", "hard": "Difícil/Vermelho"}.get(diff, diff)
            self.draw_text(f"Tempo: {remaining}s", (x, y), self.font, RED if remaining <= 10 else DARK)
            self.draw_text(diff_label, (x + 170, y + 3), self.font_tiny, DARK)
            y += 29
            question_rect = pygame.Rect(x, y, content_w, 58)
            self.draw_card(question_rect, ANSWER_FILL, SOFT_BORDER, 2, 10)
            self.draw_wrapped(q.get("prompt", ""), x + 10, y + 7, 53, self.font_tiny, TEXT, 17)
            y += 64
            eliminated = set(q.get("eliminated_options") or [])
            letters = ["A", "B", "C", "D"]
            options = list(q.get("options") or [])
            for idx, option in enumerate(options):
                self.add_button(
                    pygame.Rect(x, y + idx * 31, content_w, 27),
                    f"{letters[idx]}) {option}"[:70],
                    lambda i=idx: self.fire_and_forget({"type": "answer", "answer_index": i}),
                    enabled=my_turn and idx not in eliminated,
                    fill_color=ANSWER_FILL, hover_color=(234, 244, 226),
                    border_color=SOFT_BORDER, font=self.font_tiny,
                )
            y += len(options) * 31 + 2
            y = self.draw_balance_card(x, y, content_w, cp, compact=True)
            y = self.draw_help_section(x, y, content_w, cp, my_turn, compact=True)
            y = self.draw_mini_event_log(x, y, content_w, compact=True)
            self.draw_stop_section(x, y, content_w, my_turn, compact=True)
            return

        pending = self.state.get("pending_question_difficulty")
        diff_label = {"easy": "Fácil / Verde", "medium": "Médio / Amarelo", "hard": "Difícil / Vermelho"}.get(pending, pending or "")
        box = pygame.Rect(x, y, content_w, right.bottom - y - 60)
        self.draw_card(box, (239, 245, 218), SOFT_BORDER, 1, 12)
        bx, by = box.x + 13, box.y + 12
        if phase == "awaiting_roll" and cp:
            self.draw_centered("JOGAR DADO", pygame.Rect(bx, by, box.w - 26, 32), self.font, DARK)
            by += 37
            by = self.draw_wrapped(f"{cp.get('name')} está em {track_label(int(cp.get('position', 0)), self.state.get('game_mode', 'dice_board'))}. Role o dado para avançar.", bx, by, 48, self.font_tiny, TEXT, 18)
            dice_rect = pygame.Rect(bx, by + 7, 92, 76)
            self.draw_card(dice_rect, WHITE, DARK, 3, 15)
            self.draw_centered(str(self.dice_value if self.dice_animating else "?"), dice_rect, self.font_big, DARK)
            status = "Resultado exibido" if self.dice_revealing else ("Rolando..." if self.dice_animating else "Jogar dado")
            self.add_button(pygame.Rect(bx + 108, by + 20, 225, 43), status, self.start_dice_animation, enabled=my_turn and not self.dice_animating, font=self.font_button_small)
        elif phase == "awaiting_question" and cp:
            self.draw_centered("PRONTO PARA A PERGUNTA", pygame.Rect(bx, by, box.w - 26, 36), self.font, DARK)
            by += 43
            roll = f" Dado: {self.state.get('last_roll')}." if self.state.get("last_roll") else ""
            by = self.draw_wrapped(f"{cp.get('name')} está na casa {track_label(int(cp.get('position', 0)), self.state.get('game_mode', 'dice_board'))}.{roll} Nível: {diff_label}.", bx, by, 48, self.font_small, TEXT, 21)
            self.draw_text("O cronômetro começa ao iniciar.", (bx, by + 5), self.font_tiny, TEXT)
            self.add_button(pygame.Rect(bx, by + 34, 245, 46), "Iniciar pergunta", lambda: self.fire_and_forget({"type": "begin_question"}), enabled=my_turn, font=self.font_button_small)
        else:
            self.draw_wrapped("Aguardando o servidor preparar a próxima rodada...", bx, by, 48, self.font_tiny, TEXT)
        self.draw_mini_event_log(x, right.bottom - 55, content_w, compact=True)

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
        right = pygame.Rect(535, 20, 720, 682)
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

        self.add_button(
            pygame.Rect(x, min(y + 20, right.bottom - 150), 220, 46),
            "Voltar ao menu",
            lambda: asyncio.create_task(self.back_to_menu()),
            enabled=True,
        )
        self.draw_event_log(535, 20, 720, 682)

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
            if self.ui_mode == "home":
                self.draw_home_menu()
            elif self.ui_mode == "how_to_play":
                self.draw_how_to_play()
            elif self.ui_mode == "local_setup":
                self.draw_local_setup()
            else:
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
                        if event.key == pygame.K_ESCAPE and self.ui_mode == "how_to_play":
                            self.close_rules()
                        elif event.key == pygame.K_ESCAPE and self.ui_mode == "connection" and self.show_server_settings:
                            self.toggle_server_settings()
                        elif event.key == pygame.K_ESCAPE and self.ui_mode != "home":
                            self.ui_mode = "home"
                        elif self.ui_mode == "connection":
                            for key in self.menu_input_keys():
                                self.menu_inputs[key].handle_key(event)
                        elif self.ui_mode == "local_setup":
                            self.ensure_local_name_inputs()
                            for box in self.local_name_inputs[:self.local_count]:
                                box.handle_key(event)
                        elif self.ui_mode == "home":
                            self.home_name_input.handle_key(event)
                    elif event.key == pygame.K_ESCAPE:
                        self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.in_menu:
                        clicked_input = False
                        if self.ui_mode == "connection":
                            active_keys = set(self.menu_input_keys())
                            for key, box in self.menu_inputs.items():
                                box.active = key in active_keys and box.rect.collidepoint(event.pos)
                                clicked_input = clicked_input or box.active
                            self.home_name_input.active = False
                        elif self.ui_mode == "local_setup":
                            self.ensure_local_name_inputs()
                            clicked_input = False
                            self.home_name_input.active = False
                            for box in self.menu_inputs.values():
                                box.active = False
                            for box in self.local_name_inputs[:self.local_count]:
                                box.active = box.rect.collidepoint(event.pos)
                                clicked_input = clicked_input or box.active
                        elif self.ui_mode == "home":
                            self.home_name_input.active = self.home_name_input.rect.collidepoint(event.pos)
                            clicked_input = self.home_name_input.active
                            for box in self.menu_inputs.values():
                                box.active = False
                        else:
                            self.home_name_input.active = False
                            for box in self.menu_inputs.values():
                                box.active = False
                        if clicked_input:
                            continue
                    for btn in reversed(self.buttons):
                        if btn.rect.collidepoint(event.pos):
                            btn.click()
                            break

            # Atualiza a animação do dado antes de redesenhar.
            # A versão anterior iniciava a animação, mas não chamava esta
            # rotina no loop principal, então o botão ficava preso em "Rolando...".
            self.update_dice_animation()
            self.draw()
            self.clock.tick(60)
            await asyncio.sleep(0)

        if self.ws:
            await self.ws.close()
        pygame.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cliente do Green Impact")
    parser.add_argument("--server", default=f"ws://{DEFAULT_SERVER_HOST}:{DEFAULT_SERVER_PORT}", help="URL do servidor WebSocket")
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
