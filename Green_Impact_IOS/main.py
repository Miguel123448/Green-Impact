from __future__ import annotations

import asyncio
import json
import math
import queue
import random
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable

import websockets
from green_impact.rules import track_label
from green_impact.mobile_home import MobileHomeHUD

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import ListProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

from green_impact.common import COLOR_LABELS, PLAYER_RGB

APP_DIR = Path(__file__).resolve().parent
ASSET_DIR = APP_DIR / "assets"

BG = (0.94, 0.92, 0.84, 1)
PANEL = (0.985, 0.965, 0.90, 1)
CARD = (1.0, 0.985, 0.94, 1)
DARK = (0.035, 0.25, 0.12, 1)
TEXT = (0.12, 0.16, 0.13, 1)
RED = (0.78, 0.14, 0.14, 1)
GREEN_FILL = (0.84, 0.91, 0.72, 1)
GREEN_PRIMARY = (0.055, 0.32, 0.16, 1)
GREEN_PRESSED = (0.035, 0.24, 0.11, 1)
CREAM = (0.99, 0.97, 0.90, 1)
GOLD = (0.67, 0.51, 0.20, 1)
GOLD_SOFT = (0.84, 0.74, 0.48, 1)
WHITE = (1, 1, 1, 1)
DISABLED = (0.68, 0.68, 0.62, 1)

COLOR_ORDER = ["green", "yellow", "red", "blue"]
COLOR_NAMES = {"green": "Verde", "yellow": "Amarelo", "red": "Vermelho", "blue": "Azul"}
DIFF_LABELS = {"easy": "Fácil / Verde", "medium": "Médio / Amarelo", "hard": "Difícil / Vermelho"}

DEFAULT_SERVER_HOST = "147.15.100.214"
DEFAULT_SERVER_PORT = "8765"
LOCALHOST = "127.0.0.1"

# Coordenadas aproximadas na imagem board.jpg original (1414x2000), medidas a partir do topo.
BOARD_ORIGINAL_W = 1414
BOARD_ORIGINAL_H = 2000
PATH_X = {"green": 255, "yellow": 555, "red": 850, "blue": 1148}
PATH_Y_TOP = {
    0: 1785,
    1: 1625,
    2: 1490,
    3: 1355,
    4: 1220,
    5: 1085,
    6: 950,
    7: 815,
    8: 680,
    9: 530,
    10: 392,
}

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


def rgba255(rgb: tuple[int, int, int], alpha: float = 1.0) -> tuple[float, float, float, float]:
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, alpha)


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return LOCALHOST


def build_server_url(host: str, port: str) -> str:
    host = (host or DEFAULT_SERVER_HOST).strip()
    port = (port or DEFAULT_SERVER_PORT).strip()
    if host.startswith("ws://") or host.startswith("wss://"):
        return host
    return f"ws://{host}:{port}"


class RoundedBox(BoxLayout):
    def __init__(self, bg_color: tuple = CARD, border_color: tuple = GOLD_SOFT, radius: int = 18, **kwargs: Any):
        super().__init__(**kwargs)
        self._bg_color = bg_color
        self._border_color = border_color
        self._radius = dp(radius)
        with self.canvas.before:
            self._canvas_bg_color = Color(*self._bg_color)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            self._canvas_border_color = Color(*self._border_color)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self._radius), width=1.15)
        self.bind(pos=self._update_canvas, size=self._update_canvas)

    def _update_canvas(self, *_args: Any) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)


class RoundedFloatLayout(FloatLayout):
    def __init__(self, bg_color: tuple = DARK, border_color: tuple = GOLD_SOFT, radius: int = 22, **kwargs: Any):
        super().__init__(**kwargs)
        self._radius = dp(radius)
        with self.canvas.before:
            Color(*bg_color)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            Color(*border_color)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self._radius), width=1.25)
        self.bind(pos=self._update_canvas, size=self._update_canvas)

    def _update_canvas(self, *_args: Any) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)


class RoundedButton(Button):
    def __init__(
        self,
        bg_color: tuple = GREEN_FILL,
        down_color: tuple = GREEN_PRIMARY,
        border_color: tuple = GREEN_PRIMARY,
        text_color: tuple = DARK,
        radius: int = 14,
        **kwargs: Any,
    ):
        super().__init__(background_normal="", background_down="", background_color=(0, 0, 0, 0), color=text_color, **kwargs)
        self._normal_color = bg_color
        self._down_color = down_color
        self._border_color = border_color
        self._radius = dp(radius)
        with self.canvas.before:
            self._fill_color = Color(*self._normal_color)
            self._fill = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            self._stroke_color = Color(*self._border_color)
            self._stroke = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self._radius), width=1.25)
        self.bind(pos=self._update_canvas, size=self._update_canvas, state=self._update_state, disabled=self._update_state)

    def _update_canvas(self, *_args: Any) -> None:
        self._fill.pos = self.pos
        self._fill.size = self.size
        self._stroke.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)

    def _update_state(self, *_args: Any) -> None:
        if self.disabled:
            color = DISABLED
            self.color = (0.42, 0.43, 0.39, 1)
        elif self.state == "down":
            color = self._down_color
        else:
            color = self._normal_color
        self._fill_color.rgba = color


class GearButton(Button):
    """Ícone vetorial para evitar dependência de emoji/fonte no Android."""

    def __init__(self, callback: Callable[[], None], **kwargs: Any):
        super().__init__(
            text="", size_hint=(None, None), width=dp(48), height=dp(48),
            background_normal="", background_down="", background_color=(0, 0, 0, 0), **kwargs
        )
        with self.canvas.before:
            Color(*GREEN_FILL)
            self._gear_bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
            Color(*GOLD_SOFT)
            self._gear_border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(12)), width=1.1)
        with self.canvas.after:
            Color(*DARK)
            self._gear_teeth = [Line(points=[0, 0, 0, 0], width=dp(2.7)) for _ in range(8)]
            self._gear_outer = Line(circle=(0, 0, 0), width=dp(2.5))
            self._gear_inner = Line(circle=(0, 0, 0), width=dp(2.1))
        self.bind(pos=self._update_gear, size=self._update_gear)
        self.bind(on_release=lambda *_: callback())
        Clock.schedule_once(lambda *_: self._update_gear(), 0)

    def _update_gear(self, *_args: Any) -> None:
        self._gear_bg.pos = self.pos
        self._gear_bg.size = self.size
        self._gear_border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(12))
        cx, cy = self.center
        unit = min(self.width, self.height)
        for line, angle in zip(self._gear_teeth, range(0, 360, 45)):
            rad = math.radians(angle)
            inner = unit * 0.21
            outer = unit * 0.34
            line.points = [cx + math.cos(rad) * inner, cy + math.sin(rad) * inner, cx + math.cos(rad) * outer, cy + math.sin(rad) * outer]
        self._gear_outer.circle = (cx, cy, unit * 0.205)
        self._gear_inner.circle = (cx, cy, unit * 0.07)


class WrappedLabel(Label):
    def __init__(self, text: str = "", font_size: int = 16, bold: bool = False, color: tuple = TEXT, min_height: int = 28, **kwargs: Any):
        super().__init__(
            text=text,
            markup=True,
            color=color,
            font_size=dp(font_size),
            bold=bold,
            halign=kwargs.pop("halign", "left"),
            valign=kwargs.pop("valign", "top"),
            size_hint_y=None,
            **kwargs,
        )
        self.min_height = dp(min_height)
        self.bind(width=self._sync_text_size, texture_size=self._sync_height)
        Clock.schedule_once(lambda *_: self._sync_text_size(), 0)

    def _sync_text_size(self, *_args: Any) -> None:
        self.text_size = (max(self.width, dp(20)), None)
        self._sync_height()

    def _sync_height(self, *_args: Any) -> None:
        self.height = max(self.min_height, self.texture_size[1] + dp(10))


class BoardWidget(Widget):
    players = ListProperty([])

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.texture = None
        self.new_texture = None
        self.game_mode = "classic"
        board_path = ASSET_DIR / "board_mobile.jpg"
        if not board_path.exists():
            board_path = ASSET_DIR / "board.jpg"
        new_board_path = ASSET_DIR / "board_new_mobile.jpg"
        if not new_board_path.exists():
            new_board_path = ASSET_DIR / "board_new.jpg"
        if board_path.exists():
            self.texture = CoreImage(str(board_path)).texture
        if new_board_path.exists():
            self.new_texture = CoreImage(str(new_board_path)).texture
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw(), players=lambda *_: self.redraw())
        Clock.schedule_once(lambda *_: self.redraw(), 0)

    def _board_rect(self) -> tuple[float, float, float, float]:
        widget_ratio = self.width / max(self.height, 1)
        if self.game_mode != "classic":
            board_ratio = NEW_BOARD_ORIGINAL_W / NEW_BOARD_ORIGINAL_H
        else:
            board_ratio = BOARD_ORIGINAL_W / BOARD_ORIGINAL_H
        if widget_ratio > board_ratio:
            h = self.height
            w = h * board_ratio
        else:
            w = self.width
            h = w / board_ratio
        x = self.x + (self.width - w) / 2
        y = self.y + (self.height - h) / 2
        return x, y, w, h

    def board_to_screen(self, color: str, position: int) -> tuple[float, float]:
        bx, by, bw, bh = self._board_rect()
        if self.game_mode != "classic":
            ox, oy = NEW_PATH.get(max(0, min(17, int(position))), NEW_PATH[0])
            x = bx + (ox / NEW_BOARD_ORIGINAL_W) * bw
            y = by + bh - (oy / NEW_BOARD_ORIGINAL_H) * bh
            return x, y
        ox = PATH_X.get(color, 255)
        oy_top = PATH_Y_TOP.get(position, PATH_Y_TOP[0])
        x = bx + (ox / BOARD_ORIGINAL_W) * bw
        y = by + bh - (oy_top / BOARD_ORIGINAL_H) * bh
        return x, y

    def redraw(self) -> None:
        self.canvas.clear()
        with self.canvas:
            Color(*BG)
            Rectangle(pos=self.pos, size=self.size)
            bx, by, bw, bh = self._board_rect()
            texture = self.new_texture if self.game_mode != "classic" and self.new_texture else self.texture
            if texture:
                Color(1, 1, 1, 1)
                Rectangle(texture=texture, pos=(bx, by), size=(bw, bh))
            else:
                Color(0.75, 0.88, 0.65, 1)
                RoundedRectangle(pos=(bx, by), size=(bw, bh), radius=[dp(14)])

            grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
            for p in self.players or []:
                color = p.get("color") or "green"
                pos = int(p.get("position") or 0)
                grouped.setdefault((color, pos), []).append(p)

            for (color, pos), players in grouped.items():
                base_x, base_y = self.board_to_screen(color, pos)
                count = len(players)
                for idx, p in enumerate(players):
                    angle = (2 * math.pi * idx / max(count, 1)) if count > 1 else 0
                    off = dp(15) if count > 1 else 0
                    x = base_x + math.cos(angle) * off
                    y = base_y + math.sin(angle) * off
                    rgb = PLAYER_RGB.get(color, (80, 80, 80))
                    if p.get("eliminated") or p.get("stopped"):
                        rgb = (120, 120, 120)
                    radius = max(dp(10), min(dp(17), bw * 0.028))
                    Color(1, 1, 1, 1)
                    Ellipse(pos=(x - radius - dp(3), y - radius - dp(3)), size=((radius + dp(3)) * 2, (radius + dp(3)) * 2))
                    Color(*rgba255(rgb))
                    Ellipse(pos=(x - radius, y - radius), size=(radius * 2, radius * 2))
                    Color(0, 0, 0, 0.65)
                    Line(circle=(x, y, radius), width=1.2)


class NetworkClient:
    def __init__(self, on_message: Callable[[dict[str, Any]], None], on_log: Callable[[str], None]):
        self.on_message = on_message
        self.on_log = on_log
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.ws: Any = None
        self.connected = False

    def _ensure_loop(self) -> None:
        if self.loop and not self.loop.is_closed():
            return
        loop = asyncio.new_event_loop()
        self.loop = loop

        def runner() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self.thread = threading.Thread(target=runner, daemon=True)
        self.thread.start()

    def connect(self, url: str, name: str, room: str | None, game_mode: str = "dice_board", local_count: int | None = None, local_names: list[str] | None = None) -> None:
        self._ensure_loop()
        assert self.loop is not None
        asyncio.run_coroutine_threadsafe(self._connect(url, name, room, game_mode, local_count, local_names or []), self.loop)

    async def _connect(self, url: str, name: str, room: str | None, game_mode: str = "dice_board", local_count: int | None = None, local_names: list[str] | None = None) -> None:
        try:
            self.on_log("Conectando ao servidor selecionado...")
            self.ws = await asyncio.wait_for(websockets.connect(url), timeout=8.0)
            self.connected = True
            if room:
                await self.send({"type": "join", "room": room.upper(), "name": name})
            elif local_count:
                await self.send({"type": "create_local", "name": name, "count": local_count, "names": local_names or []})
            else:
                await self.send({"type": "create", "name": name, "game_mode": game_mode})
            await self._listen()
        except Exception as exc:
            self.connected = False
            self.on_message({"type": "error", "message": f"Não foi possível conectar: {exc}"})

    async def _listen(self) -> None:
        async for raw in self.ws:
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            self.on_message(payload)

    async def send(self, payload: dict[str, Any]) -> None:
        if self.ws:
            await self.ws.send(json.dumps(payload, ensure_ascii=False))

    def send_nowait(self, payload: dict[str, Any]) -> None:
        if not self.loop:
            return
        asyncio.run_coroutine_threadsafe(self.send(payload), self.loop)

    def close(self) -> None:
        if self.loop and self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)


def pos_label(state, pos):
    """Retorna o nome correto da posição no tabuleiro atual.

    No tabuleiro novo existem casas intermediárias de Sorte/Revés; por isso
    não podemos exibir somente o número inteiro da posição interna.
    """
    mode = (state or {}).get("game_mode", "dice_board")
    try:
        return track_label(int(pos or 0), mode)
    except Exception:
        return str(pos)

class GreenImpactAndroidApp(App):
    title = "Green Impact"
    icon = str(ASSET_DIR / "app_icon.png")

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.state: dict[str, Any] | None = None
        self.you: str | None = None
        self.room_code: str | None = None
        self.server_delta = 0.0
        self.messages: list[str] = []
        self.connection_error = ""
        self.local_server_thread: threading.Thread | None = None
        self.local_server_error: str | None = None
        self.lan_ip = LOCALHOST
        self.msg_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.network = NetworkClient(self.queue_message, self.log)
        self.root_layout: BoxLayout | None = None
        self.game_layout: BoxLayout | None = None
        self.home_screen: MobileHomeHUD | None = None
        self.board_shell: RoundedFloatLayout | None = None
        self.board: BoardWidget | None = None
        self.panel: RoundedBox | None = None
        self.panel_scroll: ScrollView | None = None
        self.content: BoxLayout | None = None
        self.current_screen = "home"
        self.rules_previous_screen: str | None = None
        self.last_render_signature: tuple[Any, ...] | None = None
        self.home_name_input: TextInput | None = None
        self.name_input: TextInput | None = None
        self.host_input: TextInput | None = None
        self.port_input: TextInput | None = None
        self.server_host = DEFAULT_SERVER_HOST
        self.server_port = DEFAULT_SERVER_PORT
        self.manual_server_mode = False
        self.server_popup: Popup | None = None
        self.server_host_input: TextInput | None = None
        self.server_port_input: TextInput | None = None
        self.room_input: TextInput | None = None
        self.local_name_inputs: list[TextInput] = []
        self.local_name_values: list[str] = [f"Jogador {i + 1}" for i in range(4)]
        self.timeout_sent_for_question: str | None = None
        self.timer_label: WrappedLabel | None = None
        self.local_count = 2
        self.dice_animating = False
        self.dice_revealing = False
        self.dice_roll_sent = False
        self.dice_value = 1
        self.dice_final_value = 1
        self._dice_clock_event = None
        self.dice_label: WrappedLabel | None = None
        self.dice_status_label: WrappedLabel | None = None
        self.private_tip_message: str | None = None
        self.private_tip_question_id: str | None = None
        self.scroll_to_question_on_render = False

    def detect_lan_ip(self) -> None:
        detected = get_lan_ip()
        Clock.schedule_once(lambda *_: setattr(self, "lan_ip", detected), 0)

    def build(self) -> BoxLayout:
        Window.softinput_mode = "resize"
        Window.clearcolor = (0.10, 0.18, 0.07, 1)
        if platform not in {"android", "ios"}:
            # A prévia desktop/macOS usa o mesmo formato retrato do mobile.
            Window.size = (540, 960)

        # Contêiner raiz. A tela inicial e a tela de jogo são árvores distintas;
        # isso elimina qualquer reaproveitamento da HUD antiga no menu.
        self.root_layout = BoxLayout(orientation="vertical")

        self.game_layout = BoxLayout(
            orientation="vertical",
            padding=[dp(10), dp(10), dp(10), dp(10)],
            spacing=dp(10),
        )
        self.board_shell = RoundedFloatLayout(
            size_hint=(1, 0.54),
            bg_color=DARK,
            border_color=GOLD_SOFT,
        )
        self.board = BoardWidget(size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self.board_shell.add_widget(self.board)

        self.panel = RoundedBox(
            orientation="vertical",
            bg_color=PANEL,
            border_color=GOLD_SOFT,
            size_hint=(1, 0.46),
            padding=dp(0),
            spacing=dp(0),
            radius=22,
        )
        self.game_layout.add_widget(self.board_shell)
        self.game_layout.add_widget(self.panel)

        self.home_screen = MobileHomeHUD(
            asset_dir=ASSET_DIR,
            on_create=self.create_room_on_ip,
            on_join=self.join_room_on_ip,
            on_solo=self.start_one_player,
            on_local=self.render_local_multiplayer_menu,
            on_online=self.render_connection_menu,
            on_settings=self.open_server_settings,
            on_help=self.open_how_to_play,
            on_credits=self.open_credits,
        )

        threading.Thread(target=self.detect_lan_ip, daemon=True).start()
        Clock.schedule_interval(self.process_messages, 0.08)
        Clock.schedule_interval(self.tick_timer, 0.20)
        self.render_main_menu()
        return self.root_layout

    def show_home_screen(self, name: str | None = None, room: str | None = None) -> None:
        if not self.root_layout or not self.home_screen:
            return

        current_name = name
        if current_name is None:
            for field in (self.name_input, self.home_name_input):
                if field is not None and field.text.strip():
                    current_name = field.text.strip()
                    break
        current_name = current_name or "Jogador Verde"

        current_room = room
        if current_room is None and self.room_input is not None:
            current_room = self.room_input.text.strip().upper()
        current_room = current_room or ""

        self.home_screen.set_values(
            current_name,
            current_room,
            self.server_host,
            self.server_port,
            self.connection_error,
        )
        self.name_input = self.home_screen.name_input
        self.home_name_input = self.home_screen.name_input
        self.room_input = self.home_screen.room_input

        if self.home_screen.parent is not self.root_layout:
            self.root_layout.clear_widgets()
            self.root_layout.add_widget(self.home_screen)

    def show_game_screen(self) -> None:
        if not self.root_layout or not self.game_layout:
            return
        if self.game_layout.parent is not self.root_layout:
            self.root_layout.clear_widgets()
            self.root_layout.add_widget(self.game_layout)

    def apply_layout_for_current_mode(self) -> None:
        if not self.root_layout or not self.game_layout or not self.board_shell or not self.panel:
            return

        if self.current_screen in {"home", "connection"}:
            self.show_home_screen()
            return

        self.show_game_screen()
        # Android e iOS usam uma HUD retrato: tabuleiro acima, comandos abaixo.
        self.game_layout.orientation = "vertical"
        self.game_layout.padding = [dp(10), dp(10), dp(10), dp(10)]
        self.game_layout.spacing = dp(10)
        if self.state and self.state.get("game_mode") == "classic":
            self.board_shell.size_hint = (1, 0.48)
            self.panel.size_hint = (1, 0.52)
        else:
            self.board_shell.size_hint = (1, 0.54)
            self.panel.size_hint = (1, 0.46)
        if self.board:
            self.board.redraw()

    # ---------- helpers de UI ----------
    def queue_message(self, payload: dict[str, Any]) -> None:
        self.msg_queue.put(payload)

    def log(self, message: str) -> None:
        self.messages.append(message)
        self.messages = self.messages[-6:]
        Clock.schedule_once(lambda *_: self.render(), 0)

    def clear_panel(self, preserve_scroll: bool = False) -> None:
        if not self.panel:
            return

        previous_scroll_y = 1.0
        if preserve_scroll and self.panel_scroll is not None:
            previous_scroll_y = self.panel_scroll.scroll_y

        self.panel.clear_widgets()
        scroll = ScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=dp(6),
            scroll_type=["content", "bars"],
        )
        self.panel_scroll = scroll
        self.content = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(18), spacing=dp(10))
        self.content.bind(minimum_height=self.content.setter("height"))
        scroll.add_widget(self.content)
        self.panel.add_widget(scroll)

        if preserve_scroll:
            # O jogo redesenha a tela para atualizar o cronômetro. Sem restaurar
            # a posição, o ScrollView voltava para o topo a cada atualização.
            Clock.schedule_once(lambda *_: setattr(scroll, "scroll_y", previous_scroll_y), 0)

    def add(self, widget: Widget) -> Widget:
        if self.content is not None:
            self.content.add_widget(widget)
        return widget

    def label(self, text: str, font_size: int = 16, bold: bool = False, color: tuple = TEXT, min_height: int = 28, **kwargs: Any) -> WrappedLabel:
        return WrappedLabel(text=text, font_size=font_size, bold=bold, color=color, min_height=min_height, **kwargs)

    def title_label(self, text: str, size: int = 28) -> WrappedLabel:
        return self.label(text, size, True, DARK, min_height=40)

    def make_button(
        self, text: str, callback: Callable[[], None], disabled: bool = False, height: int = 50,
        primary: bool = False, outline: bool = False, selected: bool = False,
    ) -> Button:
        if primary:
            bg, down, border, fg = GREEN_PRIMARY, GREEN_PRESSED, GREEN_PRIMARY, WHITE
        elif outline:
            bg, down, border, fg = CREAM, GREEN_FILL, GREEN_PRIMARY, DARK
        elif selected:
            bg, down, border, fg = GREEN_FILL, GREEN_PRIMARY, GREEN_PRIMARY, DARK
        else:
            bg, down, border, fg = GREEN_FILL, GREEN_PRIMARY, GOLD_SOFT, DARK
        btn = RoundedButton(
            text=text, size_hint_y=None, height=dp(height), disabled=disabled,
            bg_color=bg, down_color=down, border_color=border, text_color=fg,
            font_size=dp(15), bold=True, halign="center", valign="middle",
        )
        btn.bind(width=lambda b, *_: setattr(b, "text_size", (max(b.width - dp(18), dp(40)), None)))
        btn.bind(on_release=lambda *_: callback())
        return btn

    def make_input(self, text: str = "", multiline: bool = False, input_filter: str | None = None) -> TextInput:
        return TextInput(
            text=text, multiline=multiline, input_filter=input_filter, size_hint_y=None, height=dp(48),
            font_size=dp(16), background_normal="", background_active="",
            background_color=(1.0, 0.985, 0.94, 1), foreground_color=TEXT, cursor_color=DARK,
            padding=[dp(12), dp(10), dp(12), dp(10)],
        )

    def card(self, padding: int = 10, spacing: int = 6) -> RoundedBox:
        return RoundedBox(orientation="vertical", bg_color=CARD, size_hint_y=None, padding=dp(padding), spacing=dp(spacing))

    def finalize_card(self, card: RoundedBox) -> RoundedBox:
        card.bind(minimum_height=card.setter("height"))
        return card

    def button_grid(self, cols: int = 2, height: int = 112) -> GridLayout:
        return GridLayout(cols=cols, spacing=dp(8), size_hint_y=None, height=dp(height))

    # ---------- mensagens ----------
    def process_messages(self, _dt: float) -> None:
        changed = False
        while True:
            try:
                data = self.msg_queue.get_nowait()
            except queue.Empty:
                break
            changed = True
            t = data.get("type")
            if t in {"created", "joined"}:
                self.you = data.get("player_id") or self.you
                self.room_code = data.get("room_code") or self.room_code
                self.log(f"Conectado à sala {self.room_code}.")
            elif t == "state":
                self.you = data.get("you") or self.you
                if data.get("server_ts"):
                    self.server_delta = float(data["server_ts"]) - time.time()
                previous_had_question = bool((self.state or {}).get("current_question"))
                self.state = data.get("room")
                if self.state:
                    self.current_screen = "game"
                    self.room_code = self.state.get("code") or self.room_code
                    current_q = self.state.get("current_question") or {}
                    if current_q and not previous_had_question:
                        self.scroll_to_question_on_render = True
                    current_qid = str(current_q.get("id") or "") if current_q else None
                    if not current_qid:
                        self.private_tip_message = None
                        self.private_tip_question_id = None
                    elif self.private_tip_question_id and self.private_tip_question_id != current_qid:
                        self.private_tip_message = None
                        self.private_tip_question_id = None
            elif t == "error":
                self.connection_error = str(data.get("message") or "Erro desconhecido")
                self.log("Erro: " + self.connection_error)
            elif t == "private_tip":
                tip = str(data.get("message") or "")
                self.log(tip)
                current_q = (self.state or {}).get("current_question") or {}
                current_qid = str(current_q.get("id") or "") if current_q else None
                self.private_tip_message = tip or None
                self.private_tip_question_id = current_qid or None
        if changed:
            self.render()

    def remaining_seconds(self) -> int:
        if not self.state or not self.state.get("current_question"):
            return 0
        deadline = float(self.state.get("deadline_ts") or 0)
        return max(0, int(math.ceil(deadline - (time.time() + self.server_delta))))

    def tick_timer(self, _dt: float) -> None:
        # Atualiza apenas o texto do cronômetro. Não redesenha toda a tela,
        # porque recriar o ScrollView durante o toque fazia a rolagem voltar
        # para o começo no Android.
        if not self.state or self.state.get("status") != "playing":
            return
        q = self.state.get("current_question")
        if not q:
            self.timer_label = None
            return

        remaining = self.remaining_seconds()
        if self.timer_label is not None:
            self.timer_label.text = f"Tempo: [b]{remaining}s[/b]"
            self.timer_label.color = RED if remaining <= 10 else DARK
            self.timer_label.texture_update()
            self.timer_label.canvas.ask_update()

        qid = str(q.get("id"))
        if self.is_my_turn() and remaining == 0 and self.timeout_sent_for_question != qid:
            self.timeout_sent_for_question = qid
            self.send({"type": "timeout"})
        elif remaining > 0:
            self.timeout_sent_for_question = None

    def render(self) -> None:
        if self.board:
            self.board.players = self.state.get("players", []) if self.state else []
            self.board.game_mode = self.state.get("game_mode", "classic") if self.state else "classic"
            self.board.redraw()
        if not self.panel:
            return
        if not self.state:
            return
        status = self.state.get("status")
        if status == "waiting":
            self.render_lobby()
        elif status == "playing":
            self.render_game()
        elif status == "ended":
            self.render_ended()

    # ---------- telas ----------
    def return_to_menu(self) -> None:
        """Sai da sala atual e volta ao menu principal após o fim da partida."""
        self.network.close()
        self.state = None
        self.you = None
        self.room_code = None
        self.connection_error = ""
        self.timeout_sent_for_question = None
        self.last_render_signature = None
        self.render_main_menu()

    def render_main_menu(self) -> None:
        previous_name = "Jogador Verde"
        previous_room = ""
        for field in (self.name_input, self.home_name_input):
            if field is not None and field.text.strip():
                previous_name = field.text.strip()
                break
        if self.room_input is not None:
            previous_room = self.room_input.text.strip().upper()

        self.timer_label = None
        self.dice_label = None
        self.dice_status_label = None
        self.current_screen = "home"
        self.rules_previous_screen = None
        self.last_render_signature = None
        self.state = None
        self.you = None
        self.room_code = None
        if self.board:
            self.board.game_mode = "dice_board"
            self.board.players = []
            self.board.redraw()

        self.show_home_screen(previous_name, previous_room)

    def render_connection_menu(self) -> None:
        # O novo menu reúne criação, entrada e configuração de servidor na mesma HUD.
        self.render_main_menu()

    def open_server_settings(self) -> None:
        if self.server_popup is not None:
            self.server_popup.dismiss()

        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        content.add_widget(self.label("Selecionar servidor", 24, True, DARK, min_height=42, halign="center"))
        selected_text = "Servidor manual selecionado" if self.manual_server_mode else "Servidor padrão selecionado"
        content.add_widget(self.label(selected_text, 14, True, DARK, min_height=34, halign="center"))
        content.add_widget(self.label("Para usar outro servidor, informe um IP ou domínio e uma porta. O endereço padrão não é exibido na interface.", 13, False, TEXT, min_height=52))
        content.add_widget(self.label("IP ou domínio manual", 13, True, DARK, min_height=22))
        visible_host = self.server_host if self.manual_server_mode else ""
        visible_port = self.server_port if self.manual_server_mode else ""
        self.server_host_input = self.make_input(visible_host)
        self.server_host_input.hint_text = "IP, domínio, ws:// ou wss://"
        content.add_widget(self.server_host_input)
        content.add_widget(self.label("Porta manual", 13, True, DARK, min_height=22))
        self.server_port_input = self.make_input(visible_port, input_filter="int")
        self.server_port_input.hint_text = "Porta"
        content.add_widget(self.server_port_input)
        actions = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(54))
        actions.add_widget(self.make_button("Salvar manual", self.save_server_settings, height=52, primary=True))
        actions.add_widget(self.make_button("Usar padrão", self.reset_server_settings, height=52, outline=True))
        actions.add_widget(self.make_button("Fechar", self.close_server_settings, height=52, outline=True))
        content.add_widget(actions)
        self.server_popup = Popup(
            title="Selecionar servidor", content=content, auto_dismiss=False,
            size_hint=(0.86, 0.84), separator_color=GOLD_SOFT,
        )
        self.server_popup.bind(on_dismiss=lambda *_: setattr(self, "server_popup", None))
        self.server_popup.open()

    def save_server_settings(self) -> None:
        host = (self.server_host_input.text if self.server_host_input else "").strip()
        port_text = (self.server_port_input.text if self.server_port_input else "").strip()
        if not host:
            self.connection_error = "Informe o IP ou domínio do servidor manual."
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
        self.server_host = host
        self.server_port = port_text or DEFAULT_SERVER_PORT
        self.manual_server_mode = True
        self.connection_error = ""
        self.close_server_settings()
        self.render_main_menu()

    def reset_server_settings(self) -> None:
        self.server_host = DEFAULT_SERVER_HOST
        self.server_port = DEFAULT_SERVER_PORT
        self.manual_server_mode = False
        self.connection_error = ""
        self.close_server_settings()
        self.render_main_menu()

    def close_server_settings(self) -> None:
        if self.server_popup is not None:
            self.server_popup.dismiss()

    def open_how_to_play(self) -> None:
        """Abre a tela de regras preservando a tela/sala atual."""
        if self.current_screen != "how_to_play":
            self.rules_previous_screen = self.current_screen
        self.render_how_to_play()

    def close_how_to_play(self) -> None:
        """Volta para a tela de onde as regras foram abertas."""
        previous = self.rules_previous_screen or "home"
        self.rules_previous_screen = None
        if previous == "home":
            self.render_main_menu()
        elif previous == "connection":
            self.render_connection_menu()
        elif previous == "local_setup":
            self.render_local_multiplayer_menu()
        elif previous == "lobby":
            self.render_lobby()
        elif previous == "game":
            self.render_game()
        elif previous == "ended":
            self.render_ended()
        else:
            self.render_main_menu()

    def render_how_to_play(self) -> None:
        self.current_screen = "how_to_play"
        self.apply_layout_for_current_mode()
        self.clear_panel()
        self.add(self.title_label("Como jogar", 30))
        sections = [
            ("Objetivo", "Green Impact é um jogo educativo sobre os Objetivos de Desenvolvimento Sustentável (ODS), criado para estimular criatividade e pensamento crítico sobre desafios ambientais, econômicos e sociais."),
            ("Preparação digital", "Tabuleiro, perguntas, dado, cronômetro e créditos são controlados pelo sistema. Cada jogador começa no Início com 3 Créditos de Carbono."),
            ("Turno", "Na sua vez, jogue o dado e avance o número de casas sorteado. Ao cair em uma casa de pergunta, toque em Iniciar pergunta quando estiver pronto."),
            ("Dificuldade", "Verde = Fácil; Amarelo/Laranja = Médio; Vermelho = Difícil."),
            ("Acerto", "Ao acertar, receba créditos conforme a dificuldade: Fácil = 1; Médio = 2; Difícil = 3."),
            ("Erro ou não responder", "Retorne à casa de onde partiu no turno, pague em créditos o número de casas retornadas e fique uma rodada sem jogar. O saldo nunca fica abaixo de 0."),
            ("Ajudas", "Cada ajuda custa 3 créditos. Só é possível usar uma ajuda por rodada e cada tipo de carta pode ser usado apenas uma vez por partida."),
            ("Ajuda do especialista", "Exibe uma dica personalizada relacionada à pergunta atual."),
            ("Eliminar duas alternativas", "Remove duas das quatro alternativas incorretas."),
            ("Pesquisa rápida", "Acrescenta 20 segundos ao cronômetro para uma pesquisa rápida na internet."),
            ("Pular pergunta", "Encerra a pergunta atual sem selecionar uma alternativa e conclui o turno."),
            ("Tempo", "Cada pergunta possui 40 segundos para resposta ou para decidir pelo uso de uma ajuda."),
            ("Sorte / Revés", "Casas especiais aplicam automaticamente bônus ou perdas de Créditos de Carbono; o saldo nunca fica negativo."),
            ("Parar", "Volta para o Início, perde metade do saldo e deixa de participar das rodadas seguintes."),
            ("Chegada", "As condições de chegada e encerramento da partida são aplicadas automaticamente pelo sistema digital."),
        ]
        for title, body in sections:
            c = self.card()
            c.add_widget(self.label(f"[b]{title}[/b]\n{body}", 15, False, TEXT, min_height=64))
            self.finalize_card(c)
            self.add(c)
        self.add(self.make_button("Voltar", self.close_how_to_play, height=54))

    def open_credits(self) -> None:
        self.current_screen = "credits"
        self.apply_layout_for_current_mode()
        self.clear_panel()
        self.add(self.title_label("Créditos", 30))
        self.add(self.label("[b]Green Impact: A Jornada Sustentável[/b]", 18, False, DARK, min_height=42, halign="center"))

        c = self.card()
        c.add_widget(self.label("[b]Elaborando por:[/b]\nPaulo Silva Barroso e Prof.ª Marcele Elisa Fontana.", 15, False, TEXT, min_height=78))
        self.finalize_card(c)
        self.add(c)

        c = self.card()
        c.add_widget(self.label("[b]Digitalizado por:[/b]\nMiguel Pereira de Lemos", 15, False, TEXT, min_height=68))
        self.finalize_card(c)
        self.add(c)

        logos = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(330), spacing=dp(10))
        logos.add_widget(Image(source=str(ASSET_DIR / "ufpe_banner.jpg"), fit_mode="contain", size_hint_y=None, height=dp(120)))
        logos.add_widget(Image(source=str(ASSET_DIR / "gamification_banner.jpg"), fit_mode="contain", size_hint_y=None, height=dp(200)))
        self.add(logos)
        self.add(self.make_button("Voltar", self.render_main_menu, height=54))

    def start_dice_animation(self) -> None:
        """Anima o widget permanente do dado sem reconstruir a tela."""
        if self.dice_animating:
            return
        self.dice_animating = True
        self.dice_revealing = False
        self.dice_roll_sent = False
        self.dice_final_value = random.randint(1, 6)
        self.dice_value = random.randint(1, 6)
        if self.dice_status_label is not None:
            self.dice_status_label.text = "Rolando o dado..."

        def paint(value: int) -> None:
            self.dice_value = value
            if self.dice_label is not None:
                self.dice_label.text = f"[b]{value}[/b]"
                self.dice_label.texture_update()
                self.dice_label.canvas.ask_update()

        def update_visual(_dt: float) -> bool:
            if not self.dice_animating or self.dice_revealing:
                return False
            paint(random.randint(1, 6))
            return True

        def reveal_roll(_dt: float) -> None:
            if not self.dice_animating:
                return
            if self._dice_clock_event is not None:
                self._dice_clock_event.cancel()
                self._dice_clock_event = None
            self.dice_revealing = True
            paint(self.dice_final_value)
            if self.dice_status_label is not None:
                self.dice_status_label.text = f"Resultado: {self.dice_final_value}"
                self.dice_status_label.texture_update()

        def send_roll(_dt: float) -> None:
            if self.dice_roll_sent:
                return
            self.dice_roll_sent = True
            self.dice_animating = False
            self.dice_revealing = False
            if self.state and self.state.get("turn_phase") == "awaiting_roll":
                self.send({"type": "roll", "roll": self.dice_final_value})

        paint(self.dice_value)
        self._dice_clock_event = Clock.schedule_interval(update_visual, 0.075)
        Clock.schedule_once(reveal_roll, 1.0)
        Clock.schedule_once(send_roll, 2.0)

    def remember_local_name_inputs(self) -> None:
        """Salva o texto digitado antes de redesenhar a tela.

        No Android/Kivy, não é seguro reutilizar o mesmo TextInput depois de
        recriar a tela, porque o widget antigo pode continuar preso ao parent
        anterior dentro do ScrollView. Ao trocar a quantidade de jogadores, isso
        causava crash com mensagem de widget já possuir parent.
        """
        for i, field in enumerate(self.local_name_inputs[:4]):
            if field is not None:
                self.local_name_values[i] = field.text

    def set_local_name_value(self, index: int, value: str) -> None:
        if 0 <= index < len(self.local_name_values):
            self.local_name_values[index] = value

    def rebuild_local_name_inputs(self) -> None:
        self.remember_local_name_inputs()
        self.local_name_inputs = []
        for i in range(4):
            text = self.local_name_values[i] if i < len(self.local_name_values) else f"Jogador {i + 1}"
            field = self.make_input(text or f"Jogador {i + 1}")
            field.bind(text=lambda instance, value, idx=i: self.set_local_name_value(idx, value))
            self.local_name_inputs.append(field)

    def ensure_local_name_inputs(self) -> None:
        if len(self.local_name_inputs) < 4:
            self.rebuild_local_name_inputs()

    def local_player_names(self) -> list[str]:
        self.remember_local_name_inputs()
        names = []
        for i in range(self.local_count):
            value = (self.local_name_values[i] or "").strip() or f"Jogador {i + 1}"
            names.append(value[:20])
        return names

    def render_local_multiplayer_menu(self) -> None:
        if self.board:
            self.board.game_mode = "dice_board"
            self.board.redraw()
        self.current_screen = "local_setup"
        self.apply_layout_for_current_mode()
        self.clear_panel()
        self.rebuild_local_name_inputs()
        self.add(self.title_label("Multijogador local", 30))

        info = self.card(padding=10, spacing=4)
        info.add_widget(self.label("Vários jogadores no mesmo dispositivo. Escolha a quantidade e informe o nome de cada jogador.", 15, False, TEXT, min_height=56))
        self.finalize_card(info)
        self.add(info)

        count_card = self.card(padding=10, spacing=8)
        count_card.add_widget(self.label(f"Quantidade de jogadores: [b]{self.local_count}[/b]", 20, False, DARK, min_height=40))
        grid = self.button_grid(cols=3, height=62)
        for count in (2, 3, 4):
            grid.add_widget(self.make_button(f"{count}" + (" [X]" if self.local_count == count else ""), lambda c=count: self.set_local_count(c), height=54))
        count_card.add_widget(grid)
        self.finalize_card(count_card)
        self.add(count_card)

        names_card = self.card(padding=10, spacing=6)
        names_card.add_widget(self.label("Nomes dos jogadores", 18, True, DARK, min_height=32))
        for i in range(self.local_count):
            names_card.add_widget(self.label(f"Jogador {i + 1}", 13, False, DARK, min_height=20))
            names_card.add_widget(self.local_name_inputs[i])
        self.finalize_card(names_card)
        self.add(names_card)

        grid2 = self.button_grid(cols=2, height=122)
        grid2.add_widget(self.make_button("Iniciar local", self.start_local_multiplayer, height=56))
        grid2.add_widget(self.make_button("Como jogar", self.open_how_to_play, height=56))
        grid2.add_widget(self.make_button("Voltar", self.render_main_menu, height=56))
        grid2.add_widget(self.label("", 1, False, TEXT, min_height=56))
        self.add(grid2)
        if self.connection_error:
            self.add(self.label("Erro: " + self.connection_error, 14, False, RED, min_height=36))

    def set_local_count(self, count: int) -> None:
        self.remember_local_name_inputs()
        self.local_count = count
        self.render_local_multiplayer_menu()

    def render_connecting(self, message: str) -> None:
        self.current_screen = "connecting"
        self.apply_layout_for_current_mode()
        self.clear_panel()
        box = AnchorLayout(anchor_x="center", anchor_y="center", size_hint_y=None, height=dp(360))
        box.add_widget(self.label(message, 22, True, DARK, halign="center", min_height=120, size_hint=(1, None)))
        self.add(box)
        if self.messages:
            self.add(self.message_box())

    def center_message(self, text: str) -> AnchorLayout:
        box = AnchorLayout(anchor_x="center", anchor_y="center")
        box.add_widget(self.label(text, 22, True, DARK, min_height=120, halign="center", size_hint=(1, None)))
        return box

    # ---------- conexão / servidor local ----------
    def input_values(self) -> tuple[str, str, str, str]:
        name = (self.name_input.text if self.name_input else (self.home_name_input.text if self.home_name_input else "Jogador")).strip() or "Jogador"
        host = (self.server_host or DEFAULT_SERVER_HOST).strip() or DEFAULT_SERVER_HOST
        port = (self.server_port or DEFAULT_SERVER_PORT).strip() or DEFAULT_SERVER_PORT
        room = (self.room_input.text if self.room_input else "").strip().upper()
        return name, host, port, room

    def create_room_on_ip(self) -> None:
        name, host, port, _room = self.input_values()
        self.connection_error = ""
        self.render_connecting("Criando sala...")
        self.network.connect(build_server_url(host, port), name, None, game_mode="dice_board")

    def join_room_on_ip(self) -> None:
        name, host, port, room = self.input_values()
        if not room:
            self.connection_error = "Digite o código da sala."
            self.render_connection_menu()
            return
        self.connection_error = ""
        self.render_connecting("Entrando na sala...")
        self.network.connect(build_server_url(host, port), name, room)

    def start_one_player(self) -> None:
        name = (self.home_name_input.text if self.home_name_input else "Jogador").strip() or "Jogador"
        self.connection_error = ""
        port = 8765
        self.start_local_server(port)
        self.render_connecting("Abrindo modo Um jogador...")

        def delayed_connect(_dt: float) -> None:
            if self.local_server_error:
                self.connection_error = "Erro ao abrir servidor local: " + self.local_server_error
                self.render_main_menu()
                return
            self.network.connect(f"ws://{LOCALHOST}:{port}", name, None, game_mode="classic")

        Clock.schedule_once(delayed_connect, 0.8)


    def start_local_multiplayer(self) -> None:
        name = (self.home_name_input.text if self.home_name_input else "Jogador").strip() or "Jogador"
        self.connection_error = ""
        port = 8765
        self.start_local_server(port)
        self.render_connecting("Abrindo multijogador local...")

        def delayed_connect(_dt: float) -> None:
            if self.local_server_error:
                self.connection_error = "Erro ao abrir servidor local: " + self.local_server_error
                self.render_local_multiplayer_menu()
                return
            self.network.connect(f"ws://{LOCALHOST}:{port}", name, None, game_mode="dice_board", local_count=self.local_count, local_names=self.local_player_names())

        Clock.schedule_once(delayed_connect, 0.8)

    def start_local_server(self, port: int) -> None:
        if self.local_server_thread and self.local_server_thread.is_alive():
            self.log(f"Servidor local já está aberto na porta {port}.")
            return
        self.local_server_error = None

        def server_thread() -> None:
            try:
                from green_impact import server as local_server

                async def runner() -> None:
                    local_server.QUESTIONS = local_server.load_questions()
                    async with websockets.serve(local_server.handler, "0.0.0.0", port):
                        await asyncio.Future()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(runner())
            except Exception as exc:
                self.local_server_error = str(exc)

        self.local_server_thread = threading.Thread(target=server_thread, daemon=True)
        self.local_server_thread.start()
        self.log(f"Servidor local aberto na porta {port}.")

    def local_server_and_create(self) -> None:
        name, _host, port_text, _room = self.input_values()
        try:
            port = int(port_text or DEFAULT_SERVER_PORT)
        except ValueError:
            self.connection_error = "A porta precisa ser um número."
            self.render_connection_menu()
            return
        self.connection_error = ""
        self.start_local_server(port)
        self.render_connecting("Abrindo servidor local...")

        def delayed_connect(_dt: float) -> None:
            if self.local_server_error:
                self.connection_error = "Erro ao abrir servidor local: " + self.local_server_error
                self.render_connection_menu()
                return
            self.network.connect(f"ws://{LOCALHOST}:{port}", name, None, game_mode="dice_board")

        Clock.schedule_once(delayed_connect, 0.8)

    # ---------- estado da partida ----------
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

    def send(self, payload: dict[str, Any]) -> None:
        self.network.send_nowait(payload)

    # ---------- lobby ----------
    def render_lobby(self) -> None:
        self.timer_label = None
        self.current_screen = "lobby"
        self.clear_panel()
        self.add(self.title_label(f"Sala {self.room_code or '---'}", 30))
        self.add(self.label("Escolha sua cor. Depois o criador da sala inicia a partida.", 15, False, TEXT))

        players = self.state.get("players", []) if self.state else []
        chosen = {p.get("color") for p in players if p.get("color")}
        me = self.me()
        grid = self.button_grid(cols=2, height=112)
        for color in COLOR_ORDER:
            taken_by_me = bool(me and me.get("color") == color)
            enabled = color not in chosen or taken_by_me
            grid.add_widget(self.make_button(
                COLOR_NAMES[color] + (" [X]" if taken_by_me else ""),
                lambda c=color: self.send({"type": "choose_color", "color": c}),
                disabled=not enabled,
                height=52,
            ))
        self.add(grid)
        self.add(self.players_box(compact=False))

        is_host = bool(me and me.get("is_host"))
        can_start = bool(is_host and me and me.get("color") and all(p.get("color") for p in players))
        grid_nav = self.button_grid(cols=3, height=62)
        grid_nav.add_widget(self.make_button("Iniciar partida", lambda: self.send({"type": "start"}), disabled=not can_start, height=54))
        grid_nav.add_widget(self.make_button("Menu", self.return_to_menu, height=54))
        grid_nav.add_widget(self.make_button("Como jogar", self.open_how_to_play, height=54))
        self.add(grid_nav)
        if not is_host:
            self.add(self.label("Apenas o criador da sala pode iniciar.", 13, False, TEXT, min_height=28))
        self.add(self.label("Criar sala = abrir uma partida nova. Entrar = usar o código de uma sala já criada.", 13, False, TEXT, min_height=42))
        if self.messages:
            self.add(self.message_box())

    def players_box(self, compact: bool = True) -> RoundedBox:
        players = self.state.get("players", []) if self.state else []
        current_id = self.state.get("current_player_id") if self.state else None
        box = self.card(padding=10, spacing=4)
        box.add_widget(self.label("Jogadores", 19 if compact else 21, True, DARK, min_height=30))
        for p in players[:4]:
            status = ""
            if p.get("eliminated"):
                status = " | eliminado"
            elif p.get("stopped"):
                status = " | parou"
            elif int(p.get("skip_turns") or 0) > 0:
                status = " | perde próxima rodada"
            elif not p.get("connected", True):
                status = " | offline"
            prefix = "▶ " if p.get("id") == current_id else "• "
            color = COLOR_LABELS.get(p.get("color"), "Sem cor")
            txt = f"{prefix}[b]{p.get('name')}[/b] | {color} | casa {pos_label(self.state, p.get('position'))} | {p.get('credits')} créditos{status}"
            fs = 16 if p.get('id') == current_id else (13 if compact else 15)
            box.add_widget(self.label(txt, fs, False, DARK if p.get('id') == current_id else TEXT, min_height=30 if p.get('id') == current_id else 25))
        self.finalize_card(box)
        return box

    # ---------- partida ----------
    def render_game(self) -> None:
        self.current_screen = "game"
        self.apply_layout_for_current_mode()
        force_question_focus = bool(self.scroll_to_question_on_render and self.state and self.state.get("current_question"))
        self.clear_panel(preserve_scroll=not force_question_focus)
        if self.state and self.state.get("game_mode") != "classic":
            self.add(self.title_label(f"Sala {self.room_code} - Tabuleiro com dado", 24))
        else:
            self.add(self.title_label(f"Sala {self.room_code}", 28))
        nav = self.button_grid(cols=2, height=54)
        nav.add_widget(self.make_button("Menu", self.return_to_menu, height=48))
        nav.add_widget(self.make_button("Como jogar", self.open_how_to_play, height=48))
        self.add(nav)
        self.add(self.players_box(compact=True))

        if not self.state:
            return

        q = self.state.get("current_question")
        cp = self.current_player()
        my_turn = self.is_my_turn()
        if cp:
            turn = self.card(padding=8, spacing=2)
            turn.add_widget(self.label(f"Vez: [b]{cp.get('name')}[/b]", 16, False, DARK, min_height=26))
            turn.add_widget(self.label(f"Casa atual: {pos_label(self.state, cp.get('position'))}   |   Sua vez: {'Sim' if my_turn else 'Não'}", 13, False, TEXT, min_height=24))
            self.finalize_card(turn)
            self.add(turn)

        if q:
            self.render_question_area(q, my_turn)
        else:
            self.render_pause_area(cp, my_turn)

        self.add(self.event_log_box())
        if force_question_focus:
            Clock.schedule_once(lambda *_: self._focus_question_area(), 0.05)

    def begin_question(self) -> None:
        self.scroll_to_question_on_render = True
        self.send({"type": "begin_question"})

    def _focus_question_area(self) -> None:
        scroll = self.panel_scroll
        target = getattr(self, "question_focus_widget", None)
        if scroll is not None and target is not None:
            try:
                scroll.scroll_to(target, padding=dp(8), animate=False)
            except Exception:
                scroll.scroll_y = 1
        elif scroll is not None:
            scroll.scroll_y = 1
        self.scroll_to_question_on_render = False

    def render_question_area(self, q: dict[str, Any], my_turn: bool) -> None:
        remaining = self.remaining_seconds()
        qid = str(q.get("id"))
        if my_turn and remaining == 0 and self.timeout_sent_for_question != qid:
            self.timeout_sent_for_question = qid
            self.send({"type": "timeout"})
        if remaining > 0:
            self.timeout_sent_for_question = None

        timer = self.card(padding=8, spacing=2)
        self.question_focus_widget = timer
        self.timer_label = self.label(f"Tempo: [b]{remaining}s[/b]", 24, False, RED if remaining <= 10 else DARK, min_height=34)
        timer.add_widget(self.timer_label)
        timer.add_widget(self.label(f"Pergunta: {DIFF_LABELS.get(q.get('difficulty'), q.get('difficulty'))}", 15, False, DARK, min_height=26))
        if my_turn:
            timer.add_widget(self.label("Responda abaixo ou use uma ajuda antes de escolher a alternativa.", 12, False, TEXT, min_height=24))
        self.finalize_card(timer)
        self.add(timer)

        question_box = self.card(padding=10, spacing=2)
        question_box.add_widget(self.label(q.get("prompt", ""), 17, False, TEXT, min_height=68))
        self.finalize_card(question_box)
        self.add(question_box)

        qid = str(q.get("id") or "")
        if self.private_tip_message and self.private_tip_question_id == qid:
            tip_box = self.card(padding=10, spacing=2)
            tip_box.add_widget(self.label("Especialista", 16, True, DARK, min_height=24))
            tip_box.add_widget(self.label(self.private_tip_message, 14, False, TEXT, min_height=50))
            self.finalize_card(tip_box)
            self.add(tip_box)

        eliminated = set(q.get("eliminated_options") or [])
        letters = ["A", "B", "C", "D"]
        for idx, opt in enumerate(q.get("options") or []):
            disabled = (idx in eliminated) or not my_turn
            txt = f"{letters[idx]}) {opt}"
            if idx in eliminated:
                txt += "  (eliminada)"
            self.add(self.make_button(txt, lambda i=idx: self.send({"type": "answer", "answer_index": i}), disabled=disabled, height=58))

        cp = self.current_player()
        saldo = cp.get("credits") if cp else "-"
        self.add(self.label(f"[b]Créditos do jogador da vez:[/b] {saldo}. Cada ajuda custa 3 créditos.", 15, False, DARK, min_height=40))

        helps = self.card(padding=8, spacing=6)
        helps.add_widget(self.label("Ajudas", 18, True, DARK, min_height=30))
        helps.add_widget(self.label("Cada carta pode ser utilizada apenas uma vez por partida.", 12, False, TEXT, min_height=28))
        used_helps = set((cp or {}).get("used_helps") or [])
        help_used_this_turn = bool(self.state.get("help_used_this_turn"))
        no_credit = isinstance(saldo, int) and saldo < 3
        grid = self.button_grid(cols=2, height=174)

        def add_help_button(label: str, help_type: str) -> None:
            already_used = help_type in used_helps
            shown = f"{label} (usada)" if already_used else label
            disabled = (not my_turn) or help_used_this_turn or no_credit or already_used
            grid.add_widget(self.make_button(
                shown,
                lambda h=help_type: self.send({"type": "help", "help": h}),
                disabled=disabled,
                height=52,
            ))

        add_help_button("Eliminar 2 alternativas", "eliminate2")
        add_help_button("Pesquisa (+20s)", "research")
        add_help_button("Especialista", "expert")
        add_help_button("Pular pergunta", "skip")
        helps.add_widget(grid)
        self.finalize_card(helps)
        self.add(helps)

        stop_card = self.card(padding=8, spacing=4)
        stop_card.add_widget(self.label("Desistir da partida", 16, True, DARK, min_height=28))
        stop_card.add_widget(self.label("Volta para o início e perde metade do saldo.", 13, False, TEXT, min_height=50))
        stop_card.add_widget(self.make_button("Parar", lambda: self.send({"type": "stop"}), disabled=not my_turn, height=54))
        self.finalize_card(stop_card)
        self.add(stop_card)

    def render_pause_area(self, cp: dict[str, Any] | None, my_turn: bool) -> None:
        self.timer_label = None
        self.dice_label = None
        self.dice_status_label = None
        phase = self.state.get("turn_phase") if self.state else None
        pending = self.state.get("pending_question_difficulty") if self.state else None
        pause = self.card(padding=12, spacing=8)
        if phase == "awaiting_roll" and cp:
            pause.add_widget(self.label("Jogar dado", 23, True, DARK, min_height=38))
            pause.add_widget(self.label(
                f"{cp.get('name')} está em {pos_label(self.state, cp.get('position'))}. Toque para lançar o dado e avançar no novo tabuleiro.",
                15, False, TEXT, min_height=64,
            ))
            dice_card = self.card(padding=8, spacing=4)
            self.dice_label = self.label(f"[b]{self.dice_value if self.dice_animating else '?'}[/b]", 46, True, DARK, min_height=76, halign="center")
            dice_card.add_widget(self.dice_label)
            if self.dice_revealing:
                dice_status = "Resultado sorteado. O peão anda em 1 segundo..."
                btn_text = "Resultado exibido"
            elif self.dice_animating:
                dice_status = "Rolando o dado..."
                btn_text = "Rolando..."
            else:
                dice_status = "Pronto para lançar"
                btn_text = "Jogar dado"
            self.dice_status_label = self.label(dice_status, 13, False, TEXT, min_height=34, halign="center")
            dice_card.add_widget(self.dice_status_label)
            self.finalize_card(dice_card)
            pause.add_widget(dice_card)
            pause.add_widget(self.make_button(btn_text, self.start_dice_animation, disabled=(not my_turn or self.dice_animating), height=60))
        elif phase == "turn_result" and cp:
            pause.add_widget(self.label("Resultado da rodada", 23, True, DARK, min_height=38))
            pause.add_widget(self.label(self.state.get("special_event") or "Rodada concluída.", 16, False, TEXT, min_height=90))
            pause.add_widget(self.make_button("Próximo jogador", lambda: self.send({"type": "continue"}), disabled=not my_turn, height=60))
        elif phase == "luck_result" and cp:
            pause.add_widget(self.label("Casa de sorte/revés", 23, True, DARK, min_height=38))
            pause.add_widget(self.label(self.state.get("special_event") or "Evento especial aplicado.", 15, False, TEXT, min_height=72))
            pause.add_widget(self.make_button("Continuar", lambda: self.send({"type": "continue"}), disabled=not my_turn, height=60))
        elif phase == "awaiting_question" and cp:
            timer_preview = self.card(padding=8, spacing=2)
            timer_preview.add_widget(self.label("Tempo: [b]40s[/b]", 24, False, DARK, min_height=34))
            timer_preview.add_widget(self.label(f"Pergunta: {DIFF_LABELS.get(pending, pending or '')}", 15, False, DARK, min_height=26))
            timer_preview.add_widget(self.label(f"Vez de {cp.get('name')} — o cronômetro começa quando a pergunta for iniciada.", 12, False, TEXT, min_height=24))
            self.finalize_card(timer_preview)
            pause.add_widget(timer_preview)

            roll_txt = f" Dado: {self.state.get('last_roll')}." if self.state.get("last_roll") else ""
            prompt_preview = self.card(padding=10, spacing=2)
            prompt_preview.add_widget(self.label(
                f"{cp.get('name')} está em {pos_label(self.state, cp.get('position'))}.{roll_txt} Toque em [b]Iniciar pergunta[/b] para revelar a pergunta nesta área e começar a contagem.",
                15,
                False,
                TEXT,
                min_height=86,
            ))
            self.finalize_card(prompt_preview)
            pause.add_widget(prompt_preview)
            pause.add_widget(self.make_button("Iniciar pergunta", self.begin_question, disabled=not my_turn, height=60))
            if not my_turn:
                pause.add_widget(self.label("Aguardando o jogador da vez iniciar.", 13, False, TEXT, min_height=28))
        else:
            pause.add_widget(self.label("Aguardando o servidor preparar a próxima rodada...", 17, False, TEXT, min_height=70))
        self.finalize_card(pause)
        self.add(pause)

    def event_log_box(self) -> RoundedBox:
        events = list(self.state.get("event_log") or [])[-5:] if self.state else []
        box = self.card(padding=10, spacing=3)
        box.add_widget(self.label("Histórico", 17, True, DARK, min_height=28))
        if not events:
            box.add_widget(self.label("Sem eventos ainda.", 13, False, TEXT, min_height=24))
        for ev in events:
            box.add_widget(self.label("• " + ev, 12, False, TEXT, min_height=24))
        self.finalize_card(box)
        return box

    def message_box(self) -> RoundedBox:
        box = self.card(padding=10, spacing=2)
        box.add_widget(self.label("Mensagens", 15, True, DARK, min_height=26))
        for msg in self.messages[-4:]:
            box.add_widget(self.label("• " + msg, 12, False, TEXT, min_height=22))
        self.finalize_card(box)
        return box

    def render_ended(self) -> None:
        self.current_screen = "ended"
        self.apply_layout_for_current_mode()
        self.clear_panel()
        self.add(self.title_label("Fim de jogo", 30))
        rows = self.state.get("ranking", []) if self.state else []
        if not rows:
            self.add(self.label("Sem ranking disponível.", 15, False, TEXT))
        for idx, row in enumerate(rows, start=1):
            status = ""
            if row.get("eliminated"):
                status = " | eliminado"
            elif row.get("stopped"):
                status = " | parou"
            c = self.card(padding=8, spacing=2)
            c.add_widget(self.label(f"[b]{idx}º {row.get('name')}[/b]", 18, False, DARK, min_height=28))
            c.add_widget(self.label(f"Casa {row.get('display_position', row.get('position'))} | {row.get('credits')} créditos{status}", 14, False, TEXT, min_height=24))
            self.finalize_card(c)
            self.add(c)
        self.add(self.event_log_box())
        grid_end = self.button_grid(cols=2, height=62)
        grid_end.add_widget(self.make_button("Voltar ao menu", self.return_to_menu, height=56))
        grid_end.add_widget(self.make_button("Como jogar", self.open_how_to_play, height=56))
        self.add(grid_end)

    def on_stop(self) -> None:
        self.network.close()


if __name__ == "__main__":
    GreenImpactAndroidApp().run()
