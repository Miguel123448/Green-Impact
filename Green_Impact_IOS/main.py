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
from green_impact.rules import HELP_COST, RESEARCH_BONUS_SECONDS, track_label

from kivy.app import App
from kivy.clock import Clock
from kivy.loader import Loader
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Rotate, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import ListProperty, NumericProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import AsyncImage, Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

from green_impact.common import COLOR_LABELS, PLAYER_RGB

APP_DIR = Path(__file__).resolve().parent
ASSET_DIR = APP_DIR / "assets"

BG = (0.92, 0.93, 0.84, 1)
PANEL = (0.96, 0.965, 0.88, 1)
CARD = (0.98, 0.985, 0.93, 1)
DARK = (0.05, 0.28, 0.17, 1)
TEXT = (0.12, 0.16, 0.13, 1)
RED = (0.78, 0.14, 0.14, 1)
GREEN_FILL = (0.88, 0.94, 0.78, 1)
WHITE = (1, 1, 1, 1)
DISABLED = (0.65, 0.66, 0.60, 1)
ANSWER_FILL = (0.97, 0.98, 0.96, 1)
HELP_FILL = (0.97, 0.90, 0.63, 1)
HELP_CARD = (1.00, 0.97, 0.82, 1)
WARNING_FILL = (1.00, 0.90, 0.82, 1)
SUCCESS_FILL = (0.84, 0.95, 0.82, 1)
ERROR_FILL = (1.00, 0.84, 0.82, 1)
INFO_FILL = (0.86, 0.93, 0.98, 1)

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


def get_lan_ip(timeout: float = 0.35) -> str:
    """Descobre o IP local sem permitir bloqueio prolongado.

    Esta função é executada em uma thread auxiliar. O timeout também protege
    aparelhos sem rota de rede ou com o Wi-Fi ainda inicializando.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.connect(("1.1.1.1", 80))
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
    def __init__(self, bg_color: tuple = CARD, border_color: tuple = DARK, radius: int = 12, **kwargs: Any):
        super().__init__(**kwargs)
        self._bg_color = bg_color
        self._border_color = border_color
        self._radius = dp(radius)
        with self.canvas.before:
            Color(*self._bg_color)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            Color(*self._border_color)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self._radius), width=1.0)
        self.bind(pos=self._update_canvas, size=self._update_canvas)

    def _update_canvas(self, *_args: Any) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)


class GearButton(Button):
    """Botão de engrenagem desenhado no canvas, sem depender de fonte/emoji.

    No Android, o caractere Unicode de engrenagem pode não existir na fonte
    padrão do Kivy. Desenhar o ícone garante que ele fique visível em todos
    os aparelhos e densidades de tela.
    """

    def __init__(self, callback: Callable[[], None], **kwargs: Any):
        super().__init__(
            text="",
            size_hint=(None, None),
            width=dp(52),
            height=dp(52),
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            **kwargs,
        )
        self._callback = callback
        with self.canvas.before:
            self._gear_bg_color = Color(*GREEN_FILL)
            self._gear_bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
            self._gear_border_color = Color(*DARK)
            self._gear_border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(12)), width=1.4)
        with self.canvas.after:
            self._gear_color = Color(*DARK)
            self._gear_teeth = [Line(points=[0, 0, 0, 0], width=dp(3.2)) for _ in range(8)]
            self._gear_outer = Line(circle=(0, 0, 0), width=dp(3.0))
            self._gear_inner = Line(circle=(0, 0, 0), width=dp(2.6))
        self.bind(pos=self._update_gear, size=self._update_gear)
        self.bind(on_release=lambda *_: self._callback())
        Clock.schedule_once(lambda *_: self._update_gear(), 0)

    def _update_gear(self, *_args: Any) -> None:
        self._gear_bg.pos = self.pos
        self._gear_bg.size = self.size
        self._gear_border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(12))
        cx, cy = self.center
        unit = min(self.width, self.height)
        inner_r = unit * 0.21
        outer_r = unit * 0.34
        for line, angle in zip(self._gear_teeth, range(0, 360, 45)):
            rad = math.radians(angle)
            line.points = [
                cx + math.cos(rad) * inner_r,
                cy + math.sin(rad) * inner_r,
                cx + math.cos(rad) * outer_r,
                cy + math.sin(rad) * outer_r,
            ]
        self._gear_outer.circle = (cx, cy, unit * 0.205)
        self._gear_inner.circle = (cx, cy, unit * 0.072)


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


class DiceFace(Widget):
    """Dado desenhado no canvas para uma animação visível em Android e iOS."""

    value = NumericProperty(1)
    scale = NumericProperty(1.0)
    jitter_x = NumericProperty(0.0)
    jitter_y = NumericProperty(0.0)
    angle = NumericProperty(0.0)

    def __init__(self, **kwargs: Any):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(104), dp(104)))
        super().__init__(**kwargs)
        self.bind(
            pos=lambda *_: self.redraw(),
            size=lambda *_: self.redraw(),
            value=lambda *_: self.redraw(),
            scale=lambda *_: self.redraw(),
            jitter_x=lambda *_: self.redraw(),
            jitter_y=lambda *_: self.redraw(),
            angle=lambda *_: self.redraw(),
        )
        Clock.schedule_once(lambda *_: self.redraw(), 0)

    def redraw(self) -> None:
        self.canvas.clear()
        side = max(dp(52), min(self.width, self.height) * 0.86 * max(0.78, float(self.scale)))
        cx = self.center_x + float(self.jitter_x)
        cy = self.center_y + float(self.jitter_y)
        x = cx - side / 2
        y = cy - side / 2
        radius = side * 0.15
        pip_radius = max(dp(4), side * 0.065)
        offsets = {
            "tl": (-0.24, 0.24), "tc": (0.0, 0.24), "tr": (0.24, 0.24),
            "ml": (-0.24, 0.0), "c": (0.0, 0.0), "mr": (0.24, 0.0),
            "bl": (-0.24, -0.24), "bc": (0.0, -0.24), "br": (0.24, -0.24),
        }
        pips = {
            1: ("c",),
            2: ("tl", "br"),
            3: ("tl", "c", "br"),
            4: ("tl", "tr", "bl", "br"),
            5: ("tl", "tr", "c", "bl", "br"),
            6: ("tl", "ml", "bl", "tr", "mr", "br"),
        }.get(max(1, min(6, int(self.value))), ("c",))

        with self.canvas:
            PushMatrix()
            Rotate(angle=float(self.angle), origin=(cx, cy))
            Color(0, 0, 0, 0.20)
            RoundedRectangle(pos=(x + dp(4), y - dp(4)), size=(side, side), radius=[radius])
            Color(1, 1, 0.97, 1)
            RoundedRectangle(pos=(x, y), size=(side, side), radius=[radius])
            Color(*DARK)
            Line(rounded_rectangle=(x, y, side, side, radius), width=dp(1.5))
            for key in pips:
                ox, oy = offsets[key]
                px = cx + ox * side - pip_radius
                py = cy + oy * side - pip_radius
                Ellipse(pos=(px, py), size=(pip_radius * 2, pip_radius * 2))
            PopMatrix()


class BoardWidget(Widget):
    players = ListProperty([])
    # left, bottom, right, top; used by the mobile HUD to reserve real map space.
    content_insets = ListProperty([0.0, 0.0, 0.0, 0.0])

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.texture = None
        self.new_texture = None
        self.game_mode = "classic"
        self._requested_textures: set[str] = set()
        self._loader_proxies: list[Any] = []
        self.bind(
            pos=lambda *_: self.redraw(),
            size=lambda *_: self.redraw(),
            players=lambda *_: self.redraw(),
            content_insets=lambda *_: self.redraw(),
        )

        # A versão anterior decodificava os dois tabuleiros grandes dentro do
        # construtor, antes do primeiro frame do Android. Em alguns aparelhos
        # isso prendia a thread gráfica e fazia o app parecer congelado. Agora
        # a imagem necessária é carregada pelo Loader em segundo plano.
        Clock.schedule_once(lambda *_: self._ensure_texture_for_mode(), 0.20)
        Clock.schedule_once(lambda *_: self.redraw(), 0)

    def _texture_info(self) -> tuple[str, Path, str]:
        if self.game_mode != "classic":
            return "dice_board", ASSET_DIR / "board_new.jpg", "new_texture"
        return "classic", ASSET_DIR / "board.jpg", "texture"

    def _ensure_texture_for_mode(self) -> None:
        key, image_path, attribute = self._texture_info()
        if getattr(self, attribute) is not None or key in self._requested_textures:
            return
        if not image_path.exists():
            return

        self._requested_textures.add(key)
        try:
            proxy = Loader.image(str(image_path), nocache=False)
            self._loader_proxies.append(proxy)

            def loaded(instance: Any, *_args: Any) -> None:
                texture = getattr(instance, "texture", None)
                if texture is not None:
                    setattr(self, attribute, texture)
                self._requested_textures.discard(key)
                try:
                    self._loader_proxies.remove(instance)
                except ValueError:
                    pass
                self.redraw()

            proxy.bind(on_load=loaded)
            # Quando a imagem já está em cache, o evento pode já ter ocorrido.
            if getattr(proxy, "loaded", False) and getattr(proxy, "texture", None) is not None:
                Clock.schedule_once(lambda *_: loaded(proxy), 0)
        except Exception as exc:
            self._requested_textures.discard(key)
            print(f"Não foi possível carregar {image_path.name}: {exc}")

    def _board_rect(self) -> tuple[float, float, float, float]:
        left, bottom, right, top = [max(0.0, float(value)) for value in self.content_insets]
        available_x = self.x + left
        available_y = self.y + bottom
        available_w = max(dp(120), self.width - left - right)
        available_h = max(dp(120), self.height - bottom - top)
        widget_ratio = available_w / max(available_h, 1)
        if self.game_mode != "classic":
            board_ratio = NEW_BOARD_ORIGINAL_W / NEW_BOARD_ORIGINAL_H
        else:
            board_ratio = BOARD_ORIGINAL_W / BOARD_ORIGINAL_H
        if widget_ratio > board_ratio:
            h = available_h
            w = h * board_ratio
        else:
            w = available_w
            h = w / board_ratio
        x = available_x + (available_w - w) / 2
        y = available_y + (available_h - h) / 2
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
        self._ensure_texture_for_mode()
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
                # Placeholder leve enquanto a textura é carregada.
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
        self._loop_lock = threading.Lock()
        self._loop_ready = threading.Event()
        self._loop_error: Exception | None = None

    def _ensure_loop(self, timeout: float = 3.0) -> asyncio.AbstractEventLoop:
        if self.loop and self.loop.is_running():
            return self.loop

        with self._loop_lock:
            if not (self.thread and self.thread.is_alive()):
                self._loop_ready.clear()
                self._loop_error = None

                def runner() -> None:
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        self.loop = loop
                        self._loop_ready.set()
                        loop.run_forever()
                    except Exception as exc:
                        self._loop_error = exc
                        self._loop_ready.set()

                self.thread = threading.Thread(target=runner, daemon=True, name="greenimpact-network")
                self.thread.start()

        # Nunca há mais uma espera infinita. Esta função roda em uma thread
        # auxiliar criada por connect(), portanto a interface permanece livre.
        if not self._loop_ready.wait(timeout):
            raise RuntimeError("A thread de rede não iniciou dentro do prazo.")
        if self._loop_error is not None:
            raise RuntimeError(f"Falha ao iniciar a rede: {self._loop_error}")
        if self.loop is None or not self.loop.is_running():
            raise RuntimeError("O loop de rede não está disponível.")
        return self.loop

    def connect(self, url: str, name: str, room: str | None, game_mode: str = "dice_board", local_count: int | None = None, local_names: list[str] | None = None) -> None:
        # A criação do loop e a conexão não bloqueiam mais a thread do Kivy.
        def submit_connection() -> None:
            try:
                loop = self._ensure_loop()
                asyncio.run_coroutine_threadsafe(
                    self._connect(url, name, room, game_mode, local_count, local_names or []),
                    loop,
                )
            except Exception as exc:
                self.on_message({"type": "error", "message": f"Não foi possível iniciar a conexão: {exc}"})

        threading.Thread(target=submit_connection, daemon=True, name="greenimpact-connect").start()

    async def _connect(self, url: str, name: str, room: str | None, game_mode: str = "dice_board", local_count: int | None = None, local_names: list[str] | None = None) -> None:
        try:
            self.on_log(f"Conectando em {url}...")
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
        try:
            async for raw in self.ws:
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                self.on_message(payload)
        except Exception as exc:
            if self.connected:
                self.on_message({"type": "error", "message": f"Conexão encerrada: {exc}"})
        finally:
            self.connected = False

    async def send(self, payload: dict[str, Any]) -> None:
        if self.ws:
            await self.ws.send(json.dumps(payload, ensure_ascii=False))

    def send_nowait(self, payload: dict[str, Any]) -> None:
        if not self.loop or not self.loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self.send(payload), self.loop)

    def close(self) -> None:
        self.connected = False
        if self.loop and self.loop.is_running() and self.ws:
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
        self.lan_ip = "detectando..."
        self.lan_ip_label: WrappedLabel | None = None
        self._lan_ip_thread: threading.Thread | None = None
        self.msg_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.network = NetworkClient(self.queue_message, self.log)
        self.app_root: FloatLayout | None = None
        self.root_layout: BoxLayout | None = None
        self.board: BoardWidget | None = None
        self.panel: RoundedBox | None = None
        self.game_safe_layer: FloatLayout | None = None
        # Dynamic gameplay actions no longer use Kivy Popup. A permanent
        # in-screen action sheet is attached to game_safe_layer instead.
        self.game_action_panel: RoundedBox | None = None
        self.game_action_title_label: Label | None = None
        self.game_action_kind: str | None = None
        self.game_action_signature: tuple[Any, ...] | None = None
        self.game_action_suppressed_signature: tuple[Any, ...] | None = None
        self.roll_value_label: WrappedLabel | None = None
        self.roll_dice_widget: DiceFace | None = None
        self.roll_status_label: WrappedLabel | None = None
        self.roll_button: Button | None = None
        self.panel_scroll: ScrollView | None = None
        self.content: BoxLayout | None = None
        self.current_screen = "home"
        self.rules_previous_screen: str | None = None
        self.last_render_signature: tuple[Any, ...] | None = None
        self.home_name_input: TextInput | None = None
        self.name_input: TextInput | None = None
        self.host_input: TextInput | None = None
        self.port_input: TextInput | None = None
        self.room_input: TextInput | None = None
        self.server_host = DEFAULT_SERVER_HOST
        self.server_port = DEFAULT_SERVER_PORT
        self.server_popup: Popup | None = None
        self.server_preview_label: WrappedLabel | None = None
        self.server_error_label: WrappedLabel | None = None
        self.local_name_inputs: list[TextInput] = []
        self.local_name_values: list[str] = [f"Jogador {i + 1}" for i in range(4)]
        self.timeout_sent_for_question: str | None = None
        self.force_game_scroll_top = True
        self.timer_label: WrappedLabel | None = None
        self._timer_question_id: str | None = None
        self._timer_deadline_server: float | None = None
        self._timer_deadline_monotonic: float | None = None
        self.local_count = 2
        self.dice_animating = False
        self.dice_revealing = False
        self.dice_roll_sent = False
        self.dice_value = 1
        self.dice_final_value = 1
        self._dice_clock_event = None
        # Insets das barras/recortes em coordenadas Kivy: esquerda, topo,
        # direita e base. No iOS usamos um fallback conservador até que os
        # safeAreaInsets nativos estejam disponíveis.
        self.safe_insets_px: tuple[int, int, int, int] = (
            (int(dp(44)), int(dp(8)), int(dp(44)), int(dp(21)))
            if platform == "ios"
            else (0, 0, 0, 0)
        )
        self._safe_area_request_pending = False

    def build(self) -> FloatLayout:
        Window.clearcolor = BG
        if platform not in {"android", "ios"}:
            Window.size = (1280, 720)

        # A raiz flutuante permite que o tabuleiro ocupe toda a tela durante a
        # partida, enquanto a HUD mobile é desenhada por cima. Menus e lobby
        # continuam usando o painel lateral para manter a navegação existente.
        self.app_root = FloatLayout()
        safe_left, safe_top, safe_right, safe_bottom = self.safe_insets_px
        self.root_layout = BoxLayout(
            orientation="horizontal",
            padding=[
                dp(6) + safe_left,
                dp(6) + safe_top,
                dp(6) + safe_right,
                dp(6) + safe_bottom,
            ],
            spacing=dp(8),
            size_hint=(1, 1),
        )
        self.board = BoardWidget(size_hint=(0.40, 1))
        self.panel = RoundedBox(
            orientation="vertical",
            bg_color=PANEL,
            size_hint=(0.60, 1),
            padding=dp(0),
            spacing=dp(0),
        )
        self.root_layout.add_widget(self.board)
        self.root_layout.add_widget(self.panel)

        # Camada separada para a HUD em tela cheia. Ela é posicionada dentro da
        # área segura do aparelho e só fica ativa durante jogo/fim de jogo.
        # Não use ``disabled=True`` nesta camada invisível. No Kivy, um widget
        # desabilitado ainda consome o toque quando collide_point() é verdadeiro.
        # Como esta camada fica acima do menu, isso bloqueava todos os botões no
        # Android. Fora da partida ela é movida para fora da tela e fica com
        # tamanho zero; durante a partida volta a ocupar somente a área segura.
        self.game_safe_layer = FloatLayout(size_hint=(None, None), opacity=0)
        self.app_root.add_widget(self.root_layout)
        self.app_root.add_widget(self.game_safe_layer)

        Clock.schedule_interval(self.process_messages, 0.08)
        Clock.schedule_interval(self.tick_timer, 0.20)
        Window.bind(size=self.update_game_safe_geometry)
        Clock.schedule_once(self.update_game_safe_geometry, 0)

        # A leitura da área segura pode retornar vazia nos primeiros frames.
        # Repetimos em momentos curtos e também quando a janela muda de tamanho.
        if platform in {"android", "ios"}:
            Window.bind(size=self.schedule_safe_area_refresh)
            refresh = self.refresh_android_safe_area if platform == "android" else self.refresh_ios_safe_area
            for delay in (0.25, 0.75, 1.50, 3.00):
                Clock.schedule_once(refresh, delay)

        self.render_main_menu()
        Clock.schedule_once(self.start_lan_ip_detection, 0.20)
        return self.app_root

    def start_lan_ip_detection(self, *_args: Any) -> None:
        """Detecta o IP fora da thread gráfica e atualiza somente o rótulo."""
        if self._lan_ip_thread and self._lan_ip_thread.is_alive():
            return

        def worker() -> None:
            value = get_lan_ip()
            Clock.schedule_once(lambda _dt, ip=value: self.apply_detected_lan_ip(ip), 0)

        self._lan_ip_thread = threading.Thread(target=worker, daemon=True, name="greenimpact-lan-ip")
        self._lan_ip_thread.start()

    def apply_detected_lan_ip(self, value: str) -> None:
        self.lan_ip = value or LOCALHOST
        if self.lan_ip_label is not None:
            self.lan_ip_label.text = self.lan_ip_info_text()

    def lan_ip_info_text(self) -> str:
        return (
            "No modo Um jogador o app abre um servidor local automaticamente. "
            "Para multiplayer na mesma rede, outros aparelhos podem usar o IP do servidor. "
            f"IP local detectado: [b]{self.lan_ip}[/b]."
        )

    def on_resume(self) -> None:
        """Recalcula a área útil quando o app volta do segundo plano."""
        if platform == "android":
            Clock.schedule_once(self.refresh_android_safe_area, 0.10)
            Clock.schedule_once(self.refresh_android_safe_area, 0.60)
        elif platform == "ios":
            Clock.schedule_once(self.refresh_ios_safe_area, 0.10)
            Clock.schedule_once(self.refresh_ios_safe_area, 0.60)

    def schedule_safe_area_refresh(self, *_args: Any) -> None:
        if platform == "android":
            Clock.schedule_once(self.refresh_android_safe_area, 0.05)
        elif platform == "ios":
            Clock.schedule_once(self.refresh_ios_safe_area, 0.05)

    def refresh_ios_safe_area(self, *_args: Any) -> None:
        """Lê os safeAreaInsets nativos do iOS quando o Pyobjus está disponível.

        A chamada é defensiva porque diferentes versões do kivy-ios podem
        expor a estrutura UIEdgeInsets como objeto, sequência ou tupla.
        """
        if platform != "ios":
            return
        try:
            from pyobjus import autoclass

            UIApplication = autoclass("UIApplication")
            app = UIApplication.sharedApplication()
            window = app.keyWindow()
            if window is None:
                windows = app.windows()
                if windows is not None and int(windows.count()) > 0:
                    window = windows.objectAtIndex_(0)
            if window is None or not window.respondsToSelector_("safeAreaInsets"):
                return

            insets = window.safeAreaInsets()

            def read_value(name: str, index: int) -> float:
                value = getattr(insets, name, None)
                if callable(value):
                    value = value()
                if value is None:
                    try:
                        value = insets[index]
                    except Exception:
                        value = 0
                return float(value or 0)

            top = int(dp(read_value("top", 0)))
            left = int(dp(read_value("left", 1)))
            bottom = int(dp(read_value("bottom", 2)))
            right = int(dp(read_value("right", 3)))
            self.apply_ios_safe_area((left, top, right, bottom))
        except Exception as exc:
            print(f"Não foi possível ler a área segura do iOS: {exc}")

    def update_root_padding_for_mode(self) -> None:
        """Reserva espaço real para a HUD mobile, evitando mapa sob os botões."""
        if not self.root_layout:
            return
        left, top, right, bottom = self.safe_insets_px
        base = dp(6)
        full_board = self.current_screen in {"game", "ended"} and bool(self.state)
        if full_board:
            # As barras continuam sobre a camada segura, mas o tabuleiro fica
            # numa janela central própria e nunca é coberto pelos comandos.
            self.root_layout.padding = [
                base + left + dp(8),
                base + top + dp(76),
                base + right + dp(8),
                base + bottom + dp(66),
            ]
        else:
            self.root_layout.padding = [base + left, base + top, base + right, base + bottom]
        self.root_layout.do_layout()

    def apply_ios_safe_area(self, values: tuple[int, int, int, int]) -> None:
        """Aplica a área segura do iPhone/iPad usando o mesmo layout mobile."""
        left, top, right, bottom = (max(0, int(value)) for value in values)
        new_values = (left, top, right, bottom)
        if any(self.safe_insets_px) and not any(new_values):
            return
        self.safe_insets_px = new_values
        if self.root_layout:
            self.update_root_padding_for_mode()
        self.update_game_safe_geometry()
        if self.board:
            self.board.redraw()

    def refresh_android_safe_area(self, *_args: Any) -> None:
        """Obtém os insets das barras do sistema e aplica padding ao HUD.

        Em aparelhos com navegação por três botões, a barra costuma ficar na
        lateral direita em modo paisagem. Em navegação por gestos ela pode ficar
        na parte inferior. O código não presume a posição: usa os quatro insets
        informados pelo Android, incluindo recorte/notch.
        """
        if platform != "android" or self._safe_area_request_pending:
            return
        self._safe_area_request_pending = True

        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass
        except Exception:
            self._safe_area_request_pending = False
            return

        @run_on_ui_thread
        def read_insets_on_android_ui() -> None:
            values = (0, 0, 0, 0)
            try:
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                BuildVersion = autoclass("android.os.Build$VERSION")
                Rect = autoclass("android.graphics.Rect")

                activity = PythonActivity.mActivity
                decor = activity.getWindow().getDecorView()
                root_insets = decor.getRootWindowInsets()

                if root_insets is not None and int(BuildVersion.SDK_INT) >= 30:
                    InsetsType = autoclass("android.view.WindowInsets$Type")
                    mask = int(InsetsType.systemBars()) | int(InsetsType.displayCutout())
                    inset = root_insets.getInsets(mask)
                    values = (
                        max(0, int(inset.left)),
                        max(0, int(inset.top)),
                        max(0, int(inset.right)),
                        max(0, int(inset.bottom)),
                    )
                elif root_insets is not None:
                    left = max(0, int(root_insets.getSystemWindowInsetLeft()))
                    top = max(0, int(root_insets.getSystemWindowInsetTop()))
                    right = max(0, int(root_insets.getSystemWindowInsetRight()))
                    bottom = max(0, int(root_insets.getSystemWindowInsetBottom()))

                    # O minAPI é 26; display cutout existe a partir do API 28.
                    if int(BuildVersion.SDK_INT) >= 28:
                        cutout = root_insets.getDisplayCutout()
                        if cutout is not None:
                            left = max(left, int(cutout.getSafeInsetLeft()))
                            top = max(top, int(cutout.getSafeInsetTop()))
                            right = max(right, int(cutout.getSafeInsetRight()))
                            bottom = max(bottom, int(cutout.getSafeInsetBottom()))
                    values = (left, top, right, bottom)
                else:
                    # Fallback para o raro caso de os WindowInsets ainda não
                    # estarem disponíveis: compara o frame visível com o decor.
                    frame = Rect()
                    decor.getWindowVisibleDisplayFrame(frame)
                    decor_width = max(0, int(decor.getWidth()))
                    decor_height = max(0, int(decor.getHeight()))
                    if decor_width and decor_height:
                        values = (
                            max(0, int(frame.left)),
                            max(0, int(frame.top)),
                            max(0, decor_width - int(frame.right)),
                            max(0, decor_height - int(frame.bottom)),
                        )
            except Exception as exc:
                print(f"Não foi possível ler a área segura do Android: {exc}")

            Clock.schedule_once(
                lambda _dt, safe_values=values: self.apply_android_safe_area(safe_values),
                0,
            )

        try:
            read_insets_on_android_ui()
        except Exception:
            self._safe_area_request_pending = False

    def apply_android_safe_area(self, values: tuple[int, int, int, int]) -> None:
        """Reduz a HUD para a área que não está coberta pelo sistema."""
        self._safe_area_request_pending = False
        left, top, right, bottom = (max(0, int(value)) for value in values)
        new_values = (left, top, right, bottom)

        # Alguns aparelhos entregam um frame transitório sem inset durante a
        # inicialização. Não substituímos uma medida válida por zeros até que
        # haja uma mudança real de tamanho/orientação.
        if any(self.safe_insets_px) and not any(new_values):
            return

        self.safe_insets_px = new_values
        if not self.root_layout:
            return

        # Ordem do padding do BoxLayout: esquerda, topo, direita, base.
        self.update_root_padding_for_mode()
        self.update_game_safe_geometry()
        if self.board:
            self.board.redraw()

    def safe_window_size(self) -> tuple[float, float]:
        """Dimensões úteis da janela, descontando barras e notch."""
        left, top, right, bottom = self.safe_insets_px
        return (
            max(dp(240), Window.width - left - right),
            max(dp(180), Window.height - top - bottom),
        )

    def update_game_safe_geometry(self, *_args: Any) -> None:
        """Posiciona a HUD sem permitir que uma camada invisível capture toques.

        ``Widget.disabled`` não funciona como ``pointer-events: none``: no
        Kivy, um widget desabilitado que colide com o toque pode devolvê-lo como
        tratado. Por isso a camada de jogo é retirada fisicamente da área da
        janela quando menus e lobby estão visíveis.
        """
        if not self.game_safe_layer:
            return

        full_board = self.current_screen in {"game", "ended"} and bool(self.state)
        if not full_board:
            self.game_safe_layer.opacity = 0
            self.game_safe_layer.pos = (-dp(10000), -dp(10000))
            self.game_safe_layer.size = (0, 0)
            return

        left, top, right, bottom = self.safe_insets_px
        margin = dp(7)
        self.game_safe_layer.opacity = 1
        self.game_safe_layer.pos = (left + margin, bottom + margin)
        self.game_safe_layer.size = (
            max(dp(220), Window.width - left - right - margin * 2),
            max(dp(160), Window.height - top - bottom - margin * 2),
        )
        self.layout_mobile_action_panel()
        self.update_board_viewport()

    def apply_layout_for_current_mode(self) -> None:
        """Alterna entre painel tradicional e tabuleiro mobile em tela cheia."""
        if not self.root_layout or not self.board or not self.panel:
            return

        full_board = self.current_screen in {"game", "ended"} and bool(self.state)
        self.root_layout.orientation = "horizontal"
        if full_board:
            self.board.size_hint = (1, 1)
            self.panel.size_hint = (None, 1)
            self.panel.width = 0
            self.panel.opacity = 0
            self.panel.disabled = True
            if self.game_safe_layer:
                self.update_game_safe_geometry()
        else:
            self.board.size_hint = (0.40, 1)
            self.panel.size_hint = (0.60, 1)
            self.panel.opacity = 1
            self.panel.disabled = False
            if self.game_safe_layer:
                self.game_safe_layer.clear_widgets()
                # Tamanho zero + posição externa garantem que a camada superior
                # não intercepte cliques/toques destinados ao painel do menu.
                self.update_game_safe_geometry()
            self.dismiss_game_popup(programmatic=True)

        self.update_root_padding_for_mode()
        self.root_layout.do_layout()
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
        self.apply_layout_for_current_mode()

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
        self.content = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(14), spacing=dp(9))
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
        self,
        text: str,
        callback: Callable[[], None],
        disabled: bool = False,
        height: int = 50,
        background_color: tuple | None = None,
        text_color: tuple = DARK,
        font_size: int = 15,
    ) -> Button:
        enabled_color = background_color if background_color is not None else GREEN_FILL
        btn = Button(
            text=text,
            size_hint_y=None,
            height=dp(height),
            disabled=disabled,
            background_normal="",
            background_down="",
            background_color=DISABLED if disabled else enabled_color,
            color=text_color,
            font_size=dp(font_size),
            halign="center",
            valign="middle",
        )
        btn.bind(width=lambda b, *_: setattr(b, "text_size", (max(b.width - dp(14), dp(40)), None)))
        btn.bind(on_release=lambda *_: callback())
        return btn

    def make_input(self, text: str = "", multiline: bool = False, input_filter: str | None = None) -> TextInput:
        return TextInput(
            text=text,
            multiline=multiline,
            input_filter=input_filter,
            size_hint_y=None,
            height=dp(48),
            font_size=dp(17),
            background_color=WHITE,
            foreground_color=TEXT,
            cursor_color=DARK,
            padding=[dp(10), dp(9), dp(10), dp(9)],
        )

    def card(
        self,
        padding: int = 10,
        spacing: int = 6,
        bg_color: tuple = CARD,
        border_color: tuple = DARK,
    ) -> RoundedBox:
        return RoundedBox(
            orientation="vertical",
            bg_color=bg_color,
            border_color=border_color,
            size_hint_y=None,
            padding=dp(padding),
            spacing=dp(spacing),
        )

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
                server_ts = float(data.get("server_ts") or time.time())
                self.server_delta = server_ts - time.time()

                old_state = self.state or {}
                new_state = data.get("room") or {}
                old_question = old_state.get("current_question") or {}
                new_question = new_state.get("current_question") or {}
                phase_changed = old_state.get("turn_phase") != new_state.get("turn_phase")
                player_changed = old_state.get("current_player_id") != new_state.get("current_player_id")
                question_changed = old_question.get("id") != new_question.get("id")
                new_qid = str(new_question.get("id")) if new_question else None
                try:
                    new_deadline = float(new_state.get("deadline_ts") or 0)
                except (TypeError, ValueError):
                    new_deadline = 0.0
                if new_qid and new_deadline > 0:
                    if new_qid != self._timer_question_id or new_deadline != self._timer_deadline_server:
                        # O cronômetro passa a usar o relógio monotônico local.
                        # Isso evita ficar fixo quando o relógio civil do aparelho
                        # ou a diferença cliente/servidor sofre ajuste no Android.
                        self._timer_question_id = new_qid
                        self._timer_deadline_server = new_deadline
                        self._timer_deadline_monotonic = time.monotonic() + max(0.0, new_deadline - server_ts)
                else:
                    self._timer_question_id = None
                    self._timer_deadline_server = None
                    self._timer_deadline_monotonic = None

                if phase_changed or player_changed or question_changed:
                    # Mostra imediatamente o novo jogador ou a consequência.
                    self.force_game_scroll_top = True
                    if new_state.get("turn_phase") != "awaiting_roll" or player_changed:
                        if self._dice_clock_event is not None:
                            self._dice_clock_event.cancel()
                            self._dice_clock_event = None
                        self.dice_animating = False
                        self.dice_revealing = False
                        self.dice_roll_sent = False

                self.state = new_state
                if self.state:
                    self.current_screen = "game"
                    self.room_code = self.state.get("code") or self.room_code
            elif t == "error":
                self.connection_error = str(data.get("message") or "Erro desconhecido")
                self.log("Erro: " + self.connection_error)
            elif t == "private_tip":
                self.log(str(data.get("message")))
        if changed:
            self.render()

    def remaining_seconds(self) -> int:
        if not self.state or not self.state.get("current_question"):
            return 0
        qid = str((self.state.get("current_question") or {}).get("id"))
        if qid == self._timer_question_id and self._timer_deadline_monotonic is not None:
            return max(0, math.ceil(self._timer_deadline_monotonic - time.monotonic()))
        deadline = float(self.state.get("deadline_ts") or 0)
        # Fallback para estados antigos que não tenham sido sincronizados ainda.
        return max(0, math.ceil(deadline - (time.time() + self.server_delta)))

    def tick_timer(self, _dt: float) -> None:
        # Atualiza apenas o texto do cronômetro para não recriar o ScrollView.
        if not self.state or self.state.get("status") != "playing":
            return
        q = self.state.get("current_question")
        if not q:
            self.timer_label = None
            self.timeout_sent_for_question = None
            return

        remaining = self.remaining_seconds()
        if self.timer_label is not None:
            self.timer_label.text = f"Tempo: [b]{remaining}s[/b]"
            self.timer_label.color = RED if remaining <= 10 else DARK
            # The label lives directly in the game widget tree; force texture
            # refresh to make the countdown visible on SDL2/Android immediately.
            self.timer_label.texture_update()
            self.timer_label.canvas.ask_update()

        qid = str(q.get("id"))
        if self.is_my_turn() and remaining <= 0 and self.timeout_sent_for_question != qid:
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
        self.dismiss_game_popup(programmatic=True)
        self.network.close()
        self.state = None
        self.you = None
        self.room_code = None
        self.connection_error = ""
        self.timeout_sent_for_question = None
        self.force_game_scroll_top = True
        self.last_render_signature = None
        self.render_main_menu()

    def render_main_menu(self) -> None:
        if self.board:
            self.board.game_mode = "classic"
            self.board.redraw()
        self.timer_label = None
        self.current_screen = "home"
        self.rules_previous_screen: str | None = None
        self.last_render_signature = None
        self.state = None
        self.you = None
        self.room_code = None
        self.connection_error = ""
        self.name_input = self.host_input = self.port_input = self.room_input = None
        self.clear_panel()

        logo_path = ASSET_DIR / "logo.png"
        if logo_path.exists():
            # AsyncImage evita decodificar o logotipo grande antes do primeiro frame.
            self.add(AsyncImage(source=str(logo_path), size_hint_y=None, height=dp(100), allow_stretch=True, keep_ratio=True))
        else:
            self.add(self.title_label("GREEN IMPACT", 32))

        self.add(self.title_label("Menu principal", 30))
        self.add(self.label("Escolha uma modalidade para começar.", 16, False, TEXT))

        box = self.card()
        box.add_widget(self.label("Seu nome", 14, False, DARK, min_height=22))
        self.home_name_input = self.make_input("Jogador")
        box.add_widget(self.home_name_input)
        self.finalize_card(box)
        self.add(box)

        self.add(self.make_button("Um jogador", self.start_one_player, height=54))
        self.add(self.make_button("Multijogador online", self.render_connection_menu, height=54))
        self.add(self.make_button("Multijogador local", self.render_local_multiplayer_menu, height=54))
        self.add(self.make_button("Como jogar", self.open_how_to_play, height=54))

        info = self.card()
        self.lan_ip_label = self.label(
            self.lan_ip_info_text(),
            14,
            False,
            TEXT,
            min_height=50,
        )
        info.add_widget(self.lan_ip_label)
        self.finalize_card(info)
        self.add(info)
        if self.messages:
            self.add(self.message_box())

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
        self.clear_panel()
        self.add(self.title_label("Como jogar", 30))
        sections = [
            ("Objetivo", "Chegue primeiro à casa 10/FIM respondendo perguntas sobre sustentabilidade e ODS."),
            ("Turno", "No modo Um jogador, o peão avança 1 casa. No multijogador online/local, o jogador lança um dado e anda a quantidade sorteada."),
            ("Perguntas", "No novo tabuleiro multiplayer: casas 1 a 5 usam perguntas fáceis, 6 a 9 usam médias e 10 a 12 usam difíceis. O cronômetro começa somente depois que a pergunta é iniciada."),
            ("Sorte/Revés", "Casas com símbolo de planta ativam bônus ou perda de créditos de carbono em vez de pergunta."),
            ("Créditos", "Você começa com 3 créditos de carbono. Ao acertar, ganha créditos conforme a dificuldade. Cada ajuda custa 3 créditos."),
            ("Erro", "Ao errar, volta ao Início e perde todos os créditos. Se errar novamente depois do reinício, é eliminado."),
            ("Parar", "Volta para o início e perde metade do saldo."),
            ("Ajudas", "Eliminar 2 alternativas, Pesquisa, Especialista e Pular pergunta. Só é possível usar uma ajuda por rodada."),
            ("Vitória", "Vence quem completar o percurso primeiro. Em empate, vence quem tiver mais créditos."),
        ]
        for title, body in sections:
            c = self.card()
            c.add_widget(self.label(f"[b]{title}[/b]\n{body}", 15, False, TEXT, min_height=64))
            self.finalize_card(c)
            self.add(c)
        self.add(self.make_button("Voltar", self.close_how_to_play, height=54))


    def start_dice_animation(self) -> None:
        """Anima faces, escala e deslocamento do dado antes de enviar o resultado."""
        if self.dice_animating:
            return
        self.dice_animating = True
        self.dice_revealing = False
        self.dice_roll_sent = False
        self.dice_final_value = random.randint(1, 6)
        self.dice_value = random.randint(1, 6)
        self.update_roll_mobile_widgets()

        def update_visual(_dt: float) -> bool:
            if not self.dice_animating or self.dice_revealing:
                return False
            self.dice_value = random.randint(1, 6)
            if self.roll_dice_widget is not None:
                self.roll_dice_widget.scale = random.choice((0.86, 0.94, 1.03, 1.10))
                self.roll_dice_widget.jitter_x = random.choice((-dp(6), -dp(3), 0, dp(3), dp(6)))
                self.roll_dice_widget.jitter_y = random.choice((-dp(5), -dp(2), 0, dp(2), dp(5)))
                self.roll_dice_widget.angle = (float(self.roll_dice_widget.angle) + random.choice((35, 50, 70, 90))) % 360
                self.roll_dice_widget.redraw()
                self.roll_dice_widget.canvas.ask_update()
            self.update_roll_mobile_widgets()
            return True

        def reveal_roll(_dt: float) -> None:
            if not self.dice_animating:
                return
            if self._dice_clock_event is not None:
                self._dice_clock_event.cancel()
                self._dice_clock_event = None
            self.dice_revealing = True
            self.dice_value = self.dice_final_value
            if self.roll_dice_widget is not None:
                self.roll_dice_widget.scale = 1.14
                self.roll_dice_widget.jitter_x = 0
                self.roll_dice_widget.jitter_y = 0
                self.roll_dice_widget.angle = 0
                self.roll_dice_widget.redraw()
                self.roll_dice_widget.canvas.ask_update()
            self.update_roll_mobile_widgets()
            Clock.schedule_once(self.settle_dice_visual, 0.18)

        def send_roll(_dt: float) -> None:
            if self.dice_roll_sent:
                return
            self.dice_roll_sent = True
            # Mantém a face final visível até o servidor mudar a fase.
            if self.state and self.state.get("turn_phase") == "awaiting_roll":
                self.update_roll_mobile_widgets()
                self.send({"type": "roll", "roll": self.dice_final_value})

        self._dice_clock_event = Clock.schedule_interval(update_visual, 0.075)
        Clock.schedule_once(reveal_roll, 1.05)
        Clock.schedule_once(send_roll, 2.05)

    def settle_dice_visual(self, _dt: float = 0) -> None:
        if self.roll_dice_widget is not None:
            self.roll_dice_widget.scale = 1.0
            self.roll_dice_widget.jitter_x = 0
            self.roll_dice_widget.jitter_y = 0
            self.roll_dice_widget.angle = 0
            self.roll_dice_widget.redraw()
            self.roll_dice_widget.canvas.ask_update()

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

    def render_connection_menu(self) -> None:
        if self.board:
            self.board.game_mode = "dice_board"
            self.board.redraw()
        self.current_screen = "connection"
        self.clear_panel()

        # Cabeçalho real do HUD Android: título à esquerda e configuração do
        # servidor à direita. O ícone é desenhado no canvas, não como emoji.
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(58), spacing=dp(8))
        title = self.title_label("Multijogador online", 28)
        title.size_hint_x = 1
        header.add_widget(title)

        server_tools = BoxLayout(orientation="horizontal", size_hint=(None, 1), width=dp(148), spacing=dp(8))
        server_label = Label(
            text="Servidor",
            color=DARK,
            bold=True,
            font_size=dp(14),
            halign="right",
            valign="middle",
            size_hint_x=1,
        )
        server_label.bind(size=lambda widget, *_: setattr(widget, "text_size", widget.size))
        server_tools.add_widget(server_label)
        server_tools.add_widget(GearButton(self.open_server_settings))
        header.add_widget(server_tools)
        self.add(header)

        self.add(self.label(
            "Crie uma sala ou entre usando o código recebido. Para trocar o IP do servidor, toque na engrenagem ao lado de Servidor.",
            15, False, TEXT, min_height=64,
        ))

        previous_name = self.name_input.text if self.name_input else (self.home_name_input.text if self.home_name_input else "Jogador")
        previous_room = self.room_input.text if self.room_input else ""

        form = self.card()
        form.add_widget(self.label("Seu nome", 14, False, DARK, min_height=22))
        self.name_input = self.make_input(previous_name)
        form.add_widget(self.name_input)
        form.add_widget(self.label("Código da sala", 14, False, DARK, min_height=22))
        self.room_input = self.make_input(previous_room)
        form.add_widget(self.room_input)
        self.finalize_card(form)
        self.add(form)

        grid = self.button_grid(cols=2, height=112)
        grid.add_widget(self.make_button("Criar nova sala", self.create_room_on_ip, height=52))
        grid.add_widget(self.make_button("Entrar com código", self.join_room_on_ip, height=52))
        grid.add_widget(self.make_button("Como jogar", self.open_how_to_play, height=52))
        grid.add_widget(self.make_button("Voltar", self.render_main_menu, height=52))
        self.add(grid)

        server_box = self.card()
        server_box.add_widget(self.label(
            f"[b]Servidor selecionado[/b]\n{build_server_url(self.server_host, self.server_port)}",
            13, False, DARK, min_height=54,
        ))
        self.finalize_card(server_box)
        self.add(server_box)

        if self.connection_error:
            self.add(self.label("Erro: " + self.connection_error, 14, False, RED, min_height=36))
        if self.messages:
            self.add(self.message_box())

    def open_server_settings(self) -> None:
        """Abre a configuração manual do servidor no HUD Android/Kivy."""
        if self.server_popup is not None:
            try:
                self.server_popup.dismiss()
            except Exception:
                pass

        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        content.add_widget(self.label("Servidor online", 24, True, DARK, min_height=42))
        content.add_widget(self.label(
            "Informe o IP ou domínio e a porta. Também é aceita uma URL completa começando com ws:// ou wss://.",
            14, False, TEXT, min_height=54,
        ))

        fields = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(88), cols_minimum={1: dp(112)})
        host_column = BoxLayout(orientation="vertical", spacing=dp(3))
        host_column.add_widget(self.label("IP ou endereço", 13, False, DARK, min_height=24))
        self.host_input = self.make_input(self.server_host)
        host_column.add_widget(self.host_input)
        fields.add_widget(host_column)

        port_column = BoxLayout(orientation="vertical", spacing=dp(3), size_hint_x=None, width=dp(118))
        port_column.add_widget(self.label("Porta", 13, False, DARK, min_height=24))
        self.port_input = self.make_input(self.server_port, input_filter="int")
        port_column.add_widget(self.port_input)
        fields.add_widget(port_column)
        content.add_widget(fields)

        self.server_preview_label = self.label("", 13, False, DARK, min_height=42)
        content.add_widget(self.server_preview_label)
        self.server_error_label = self.label("", 13, False, RED, min_height=32)
        content.add_widget(self.server_error_label)

        actions = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(52))
        actions.add_widget(self.make_button("Salvar", self.save_server_settings, height=50))
        actions.add_widget(self.make_button("Usar padrão", self.reset_server_settings_fields, height=50))
        actions.add_widget(self.make_button("Fechar", self.close_server_settings, height=50))
        content.add_widget(actions)

        safe_width, safe_height = self.safe_window_size()
        popup_width = min(dp(650), safe_width * 0.92)
        popup_height = min(dp(420), safe_height * 0.90)
        self.server_popup = Popup(
            title="Configurar servidor",
            content=content,
            size_hint=(None, None),
            size=(popup_width, popup_height),
            auto_dismiss=False,
            separator_color=DARK,
        )
        self.host_input.bind(text=lambda *_: self.update_server_preview())
        self.port_input.bind(text=lambda *_: self.update_server_preview())
        self.server_popup.bind(on_dismiss=self._server_popup_dismissed)
        self.update_server_preview()
        self.server_popup.open()

    def update_server_preview(self) -> None:
        if self.server_preview_label is None:
            return
        host = self.host_input.text.strip() if self.host_input else self.server_host
        port = self.port_input.text.strip() if self.port_input else self.server_port
        self.server_preview_label.text = f"[b]Conexão:[/b] {build_server_url(host, port)}"

    def reset_server_settings_fields(self) -> None:
        if self.host_input is not None:
            self.host_input.text = DEFAULT_SERVER_HOST
        if self.port_input is not None:
            self.port_input.text = DEFAULT_SERVER_PORT
        if self.server_error_label is not None:
            self.server_error_label.text = ""
        self.update_server_preview()

    def save_server_settings(self) -> None:
        host = (self.host_input.text if self.host_input else "").strip()
        port_text = (self.port_input.text if self.port_input else DEFAULT_SERVER_PORT).strip() or DEFAULT_SERVER_PORT
        error = ""
        if not host:
            error = "Informe o IP ou endereço do servidor."
        elif not host.startswith(("ws://", "wss://")):
            try:
                port = int(port_text)
            except ValueError:
                error = "A porta precisa ser um número."
            else:
                if not 1 <= port <= 65535:
                    error = "A porta deve estar entre 1 e 65535."
                else:
                    port_text = str(port)

        if error:
            if self.server_error_label is not None:
                self.server_error_label.text = "Erro: " + error
            return

        self.server_host = host
        self.server_port = port_text
        self.connection_error = ""
        self.close_server_settings()
        self.render_connection_menu()

    def close_server_settings(self) -> None:
        if self.server_popup is not None:
            self.server_popup.dismiss()

    def _server_popup_dismissed(self, *_args: Any) -> None:
        self.server_popup = None
        self.server_preview_label = None
        self.server_error_label = None
        self.host_input = None
        self.port_input = None

    def render_connecting(self, message: str) -> None:
        self.current_screen = "connecting"
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
        name = (self.name_input.text if self.name_input else "Jogador").strip() or "Jogador"
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
        box = self.card(padding=10, spacing=5)
        box.add_widget(self.label("Jogadores", 18 if compact else 21, True, DARK, min_height=30))
        for p in players[:4]:
            status = ""
            if p.get("eliminated"):
                status = " | eliminado"
            elif p.get("stopped"):
                status = " | parou"
            elif not p.get("connected", True):
                status = " | offline"
            active = p.get("id") == current_id
            color = COLOR_LABELS.get(p.get("color"), "Sem cor")
            if active:
                row = self.card(padding=7, spacing=1, bg_color=GREEN_FILL, border_color=DARK)
                row.add_widget(self.label(f"[b]JOGANDO AGORA: {p.get('name')}[/b]", 18, False, DARK, min_height=32))
                row.add_widget(self.label(
                    f"{color} | casa {pos_label(self.state, p.get('position'))} | {p.get('credits')} créditos{status}",
                    14, False, TEXT, min_height=26,
                ))
                self.finalize_card(row)
                box.add_widget(row)
            else:
                txt = f"{p.get('name')} | {color} | casa {pos_label(self.state, p.get('position'))} | {p.get('credits')} créditos{status}"
                box.add_widget(self.label(txt, 13 if compact else 15, False, TEXT, min_height=26))
        self.finalize_card(box)
        return box

    def current_turn_banner(self, cp: dict[str, Any], my_turn: bool) -> RoundedBox:
        phase = self.state.get("turn_phase") if self.state else ""
        if phase in {"turn_result", "luck_result"}:
            heading = f"RESULTADO DE {cp.get('name')}"
        elif my_turn and not (self.state and self.state.get("local_multiplayer")):
            heading = f"SUA VEZ: {cp.get('name')}"
        else:
            heading = f"VEZ DE {cp.get('name')}"

        color_name = COLOR_LABELS.get(cp.get("color"), "Sem cor")
        banner = self.card(padding=12, spacing=3, bg_color=GREEN_FILL, border_color=DARK)
        banner.add_widget(self.label(heading, 29, True, DARK, min_height=44, halign="center"))
        banner.add_widget(self.label(
            f"{cp.get('name')} | {color_name} | casa {pos_label(self.state, cp.get('position'))} | saldo: {cp.get('credits')} créditos",
            15, False, TEXT, min_height=30, halign="center",
        ))
        self.finalize_card(banner)
        return banner

    def render_stop_area(self, my_turn: bool) -> None:
        stop_card = self.card(padding=10, spacing=6, bg_color=WARNING_FILL, border_color=RED)
        stop_card.add_widget(self.label("PARAR", 18, True, RED, min_height=30))
        stop_card.add_widget(self.label(
            "Volta para o início e perde metade do saldo.",
            14, False, TEXT, min_height=58,
        ))
        stop_card.add_widget(self.make_button(
            "Parar",
            lambda: self.send({"type": "stop"}),
            disabled=not my_turn,
            height=58,
            background_color=ERROR_FILL,
            text_color=RED,
            font_size=16,
        ))
        self.finalize_card(stop_card)
        self.add(stop_card)

    def render_consequence_area(self, cp: dict[str, Any] | None, my_turn: bool) -> None:
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
        bg_color, accent, fallback_title = styles.get(kind, (INFO_FILL, DARK, "CONSEQUÊNCIA"))
        title = str(result.get("title") or fallback_title)
        message = str(result.get("message") or (self.state or {}).get("special_event") or "Rodada concluída.")

        card = self.card(padding=14, spacing=8, bg_color=bg_color, border_color=accent)
        card.add_widget(self.label("CONSEQUÊNCIA", 15, True, accent, min_height=28, halign="center"))
        card.add_widget(self.label(title, 27, True, accent, min_height=48, halign="center"))
        card.add_widget(self.label(message, 16, False, TEXT, min_height=72, halign="center"))

        old_credits = result.get("old_credits")
        new_credits = result.get("new_credits")
        if old_credits is not None and new_credits is not None:
            delta = int(result.get("credit_delta") or 0)
            delta_text = f"+{delta}" if delta > 0 else str(delta)
            card.add_widget(self.label(
                f"[b]Saldo de carbono:[/b] {old_credits} → {new_credits} créditos ({delta_text})",
                18, False, DARK, min_height=36, halign="center",
            ))

        old_position = result.get("old_position_label")
        new_position = result.get("new_position_label")
        if old_position and new_position and old_position != new_position:
            card.add_widget(self.label(
                f"[b]Posição:[/b] {old_position} → {new_position}",
                17, False, DARK, min_height=34, halign="center",
            ))
        elif result.get("position_label"):
            card.add_widget(self.label(
                f"[b]Posição atual:[/b] {result.get('position_label')}",
                15, False, DARK, min_height=30, halign="center",
            ))

        correct_answer = str(result.get("correct_answer") or "").strip()
        if correct_answer:
            card.add_widget(self.label(
                f"[b]Resposta correta:[/b] {correct_answer}",
                15, False, DARK, min_height=52,
            ))
        if result.get("eliminated"):
            card.add_widget(self.label(
                "O jogador foi eliminado e não participará das próximas rodadas.",
                16, True, RED, min_height=42, halign="center",
            ))
        elif result.get("stopped"):
            card.add_widget(self.label(
                "O jogador voltou para o início e perdeu metade do saldo.",
                16, True, RED, min_height=42, halign="center",
            ))

        button_text = "Continuar" if (self.state or {}).get("turn_phase") == "luck_result" else "Próximo jogador"
        card.add_widget(self.make_button(
            button_text,
            lambda: self.send({"type": "continue"}),
            disabled=not my_turn,
            height=62,
            background_color=GREEN_FILL,
            font_size=17,
        ))
        if not my_turn:
            player_name = (cp or {}).get("name") or "jogador da vez"
            card.add_widget(self.label(
                f"Aguardando {player_name} continuar.",
                14, False, TEXT, min_height=30, halign="center",
            ))
        self.finalize_card(card)
        self.add(card)

    # ---------- frontend mobile em tela cheia ----------
    def _clear_live_action_references(self) -> None:
        self.timer_label = None
        self.roll_dice_widget = None
        self.roll_value_label = None
        self.roll_status_label = None
        self.roll_button = None

    def _detach_game_action_panel(self) -> None:
        panel = self.game_action_panel
        if panel is not None and panel.parent is not None:
            panel.parent.remove_widget(panel)
        self.game_action_panel = None
        self.game_action_title_label = None
        self.game_action_kind = None
        self.game_action_signature = None
        self._clear_live_action_references()
        self.update_board_viewport()

    def dismiss_game_popup(self, programmatic: bool = False) -> None:
        """Compatibility name: dismisses the in-screen action sheet, not a Popup."""
        signature = self.game_action_signature
        if not programmatic and signature is not None:
            self.game_action_suppressed_signature = signature
        elif programmatic:
            self.game_action_suppressed_signature = None
        self._detach_game_action_panel()

    def minimize_game_popup(self) -> None:
        """Hides the action sheet while keeping the map and current turn active."""
        self.dismiss_game_popup(programmatic=False)

    def _game_popup_dismissed(self, *_args: Any) -> None:
        """Legacy no-op kept for compatibility with older tests/build artifacts."""
        return

    def mobile_popup_size(self) -> tuple[float, float]:
        # Still used by static informational/configuration popups. Gameplay
        # questions and dice no longer use Popup.
        width, height = self.safe_window_size()
        target_w = min(width * (0.78 if width > height else 0.94), dp(780))
        target_h = min(height * 0.90, dp(820))
        return max(dp(300), target_w), max(dp(260), target_h)

    def mobile_dialog_body(self) -> tuple[ScrollView, BoxLayout]:
        scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=dp(5),
            scroll_type=["content", "bars"],
        )
        body = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=[dp(12), dp(10), dp(12), dp(14)],
            spacing=dp(9),
        )
        body.bind(minimum_height=body.setter("height"))
        scroll.add_widget(body)
        return scroll, body

    def layout_mobile_action_panel(self, *_args: Any) -> None:
        """Positions the permanent action sheet between the top and bottom HUD."""
        panel = self.game_action_panel
        layer = self.game_safe_layer
        if panel is None or layer is None or panel.parent is None:
            self.update_board_viewport()
            return

        gap = dp(9)
        top_reserved = dp(75)
        bottom_reserved = dp(63)
        available_h = max(dp(250), layer.height - top_reserved - bottom_reserved - gap * 2)
        landscape = layer.width > layer.height

        if landscape:
            width = min(dp(760), max(dp(370), layer.width * 0.48))
            height = available_h
            x = layer.right - width - gap
            y = layer.y + bottom_reserved + gap
        else:
            width = max(dp(300), layer.width - gap * 2)
            height = min(available_h, max(dp(330), layer.height * 0.70))
            x = layer.x + gap
            y = layer.y + bottom_reserved + gap

        panel.pos = (x, y)
        panel.size = (width, height)
        panel.canvas.ask_update()
        self.update_board_viewport()

    def update_board_viewport(self) -> None:
        """Reserves actual board space for HUD and the side action sheet."""
        if self.board is None:
            return
        full_board = self.current_screen in {"game", "ended"} and bool(self.state)
        if not full_board:
            self.board.content_insets = [0.0, 0.0, 0.0, 0.0]
            return

        base = dp(5)
        left = bottom = right = top = base
        panel = self.game_action_panel
        layer = self.game_safe_layer
        if panel is not None and panel.parent is not None and layer is not None and layer.width > layer.height:
            overlap = max(0.0, self.board.right - panel.x + dp(7))
            right = min(max(base, overlap), max(base, self.board.width - dp(190)))
        self.board.content_insets = [left, bottom, right, top]
        self.board.redraw()

    def open_game_popup(
        self,
        kind: str,
        signature: tuple[Any, ...],
        title: str,
        content: Widget,
        force: bool = False,
    ) -> None:
        """Shows gameplay content in a fixed sheet inside game_safe_layer.

        The method name is retained to minimize changes in the state renderer,
        but no Kivy Popup is created. The timer label and dice canvas stay in
        the main widget tree, so Clock callbacks repaint them continuously.
        """
        if not self.game_safe_layer:
            return
        if not force and self.game_action_suppressed_signature == signature:
            return

        # Remove only the old panel widget. The new content was already built,
        # so do not clear its live timer/dice references here.
        old_panel = self.game_action_panel
        if old_panel is not None and old_panel.parent is not None:
            old_panel.parent.remove_widget(old_panel)

        panel = RoundedBox(
            orientation="vertical",
            size_hint=(None, None),
            padding=[dp(8), dp(7), dp(8), dp(8)],
            spacing=dp(6),
            bg_color=(0.98, 0.985, 0.93, 0.94),
            border_color=DARK,
            radius=18,
        )
        titlebar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(6))
        title_label = self.hud_text(f"[b]{title}[/b]", 15, halign="left")
        title_label.size_hint_x = 0.73
        hide_button = self.make_button(
            "Ocultar",
            self.minimize_game_popup,
            height=40,
            font_size=12,
            background_color=(WARNING_FILL[0], WARNING_FILL[1], WARNING_FILL[2], 0.88),
        )
        hide_button.size_hint_x = 0.27
        titlebar.add_widget(title_label)
        titlebar.add_widget(hide_button)
        panel.add_widget(titlebar)
        panel.add_widget(content)

        self.game_action_panel = panel
        self.game_action_title_label = title_label
        self.game_action_kind = kind
        self.game_action_signature = signature
        self.game_action_suppressed_signature = None
        self.game_safe_layer.add_widget(panel)
        self.layout_mobile_action_panel()

        # First paint is immediate and subsequent frames are driven by the
        # global Clock schedules already installed in build().
        if kind == "question":
            self.tick_timer(0)
        elif kind == "roll":
            self.update_roll_mobile_widgets()
        Clock.schedule_once(lambda *_: self.layout_mobile_action_panel(), 0)

    def hud_text(self, text: str, size: int = 14, halign: str = "center") -> Label:
        label = Label(
            text=text,
            markup=True,
            color=DARK,
            font_size=dp(size),
            halign=halign,
            valign="middle",
        )
        label.bind(size=lambda w, *_: setattr(w, "text_size", (w.width - dp(8), w.height)))
        return label

    def rebuild_mobile_hud(self, ended: bool = False) -> None:
        if not self.game_safe_layer:
            return
        # Server state changes rebuild the static HUD. The dynamic action sheet
        # is recreated afterward, but explicit user minimization is preserved.
        self._detach_game_action_panel()
        self.game_safe_layer.clear_widgets()

        cp = self.current_player()
        me = self.me()
        phase = str((self.state or {}).get("turn_phase") or "")
        room = self.room_code or (self.state or {}).get("code") or "---"

        top = RoundedBox(
            orientation="horizontal",
            size_hint=(0.97, None),
            height=dp(66),
            pos_hint={"center_x": 0.5, "top": 0.992},
            padding=[dp(10), dp(5), dp(10), dp(5)],
            spacing=dp(7),
            bg_color=(0.96, 0.98, 0.91, 0.88),
            border_color=DARK,
            radius=14,
        )
        top.add_widget(self.hud_text(f"[b]Sala[/b]\n{room}", 13))
        if ended:
            turn_text = "[b]FIM DE JOGO[/b]\nConfira o resultado"
        elif cp:
            prefix = "SUA VEZ" if self.is_my_turn() and not (self.state or {}).get("local_multiplayer") else "JOGADOR DA VEZ"
            turn_text = f"[b]{prefix}[/b]\n{cp.get('name')}"
        else:
            turn_text = "[b]PARTIDA[/b]\nAguardando jogador"
        top.add_widget(self.hud_text(turn_text, 15))

        balance_player = cp or me
        balance = int((balance_player or {}).get("credits", 0))
        position = pos_label(self.state, (balance_player or {}).get("position")) if balance_player else "-"
        top.add_widget(self.hud_text(f"[b]Carbono: {balance}[/b]\nCasa {position}", 13))
        self.game_safe_layer.add_widget(top)

        toolbar = RoundedBox(
            orientation="horizontal",
            size_hint=(0.97, None),
            height=dp(54),
            pos_hint={"center_x": 0.5, "y": 0.008},
            padding=dp(4),
            spacing=dp(5),
            bg_color=(0.96, 0.98, 0.91, 0.84),
            border_color=DARK,
            radius=14,
        )
        action_label = "Resultado" if ended else ("Pergunta" if (self.state or {}).get("current_question") else "Ação")
        transparent_action = (GREEN_FILL[0], GREEN_FILL[1], GREEN_FILL[2], 0.82)
        transparent_warning = (WARNING_FILL[0], WARNING_FILL[1], WARNING_FILL[2], 0.82)
        toolbar.add_widget(self.make_button(action_label, self.show_current_mobile_action, height=44, font_size=12, background_color=transparent_action))
        toolbar.add_widget(self.make_button("Jogadores", self.open_players_popup, height=44, font_size=12, background_color=transparent_action))
        toolbar.add_widget(self.make_button("Histórico", self.open_history_popup, height=44, font_size=12, background_color=transparent_action))
        toolbar.add_widget(self.make_button("Regras", self.open_rules_popup, height=44, font_size=12, background_color=transparent_action))
        toolbar.add_widget(self.make_button("Menu", self.return_to_menu, height=44, font_size=12, background_color=transparent_warning))
        self.game_safe_layer.add_widget(toolbar)
        self.update_board_viewport()

        # Pequena legenda de fase, sem competir com o tabuleiro.
        phase_names = {
            "awaiting_roll": "Lançamento do dado",
            "awaiting_question": "Preparar pergunta",
            "question": "Pergunta em andamento",
            "turn_result": "Consequência",
            "luck_result": "Sorte ou revés",
        }
        if not ended and phase:
            chip = RoundedBox(
                orientation="horizontal",
                size_hint=(None, None),
                size=(dp(190), dp(34)),
                pos_hint={"right": 0.985, "top": 0.875},
                padding=[dp(8), dp(2), dp(8), dp(2)],
                bg_color=(0.98, 0.985, 0.93, 0.92),
                border_color=DARK,
                radius=10,
            )
            chip.add_widget(self.hud_text(phase_names.get(phase, "Partida em andamento"), 11))
            self.game_safe_layer.add_widget(chip)

    def open_mobile_info_popup(self, title: str, body: BoxLayout) -> None:
        body.bind(minimum_height=body.setter("height"))
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True, bar_width=dp(5))
        scroll.add_widget(body)
        popup = Popup(
            title=title,
            content=scroll,
            size_hint=(None, None),
            size=self.mobile_popup_size(),
            auto_dismiss=True,
            title_size=dp(20),
            title_color=DARK,
            separator_color=DARK,
            overlay_color=(0, 0, 0, 0.42),
        )
        popup.open()

    def open_players_popup(self) -> None:
        body = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(12), spacing=dp(8))
        players = list((self.state or {}).get("players") or [])
        current_id = (self.state or {}).get("current_player_id")
        for player in players:
            active = player.get("id") == current_id
            status = ""
            if player.get("eliminated"):
                status = " • eliminado"
            elif player.get("stopped"):
                status = " • parou"
            elif not player.get("connected", True):
                status = " • offline"
            card = self.card(
                padding=9,
                spacing=2,
                bg_color=GREEN_FILL if active else CARD,
                border_color=DARK,
            )
            heading = "JOGANDO AGORA: " if active else ""
            card.add_widget(self.label(f"[b]{heading}{player.get('name')}[/b]", 17, False, DARK, min_height=30))
            color = COLOR_LABELS.get(player.get("color"), "Sem cor")
            card.add_widget(self.label(
                f"{color} • casa {pos_label(self.state, player.get('position'))} • {player.get('credits', 0)} créditos{status}",
                14, False, TEXT, min_height=28,
            ))
            self.finalize_card(card)
            body.add_widget(card)
        self.open_mobile_info_popup("Jogadores", body)

    def open_history_popup(self) -> None:
        body = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(12), spacing=dp(7))
        events = list((self.state or {}).get("event_log") or [])
        if not events:
            body.add_widget(self.label("Ainda não há eventos na partida.", 15, False, TEXT, min_height=48))
        for event in reversed(events[-20:]):
            card = self.card(padding=8, spacing=1, bg_color=CARD, border_color=DARK)
            card.add_widget(self.label("• " + str(event), 14, False, TEXT, min_height=40))
            self.finalize_card(card)
            body.add_widget(card)
        self.open_mobile_info_popup("Histórico da partida", body)

    def open_rules_popup(self) -> None:
        body = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(12), spacing=dp(8))
        sections = [
            ("Objetivo", "Chegue ao FIM respondendo perguntas sobre sustentabilidade e ODS."),
            ("Turno", "Lance o dado, avance e inicie a pergunta quando o tabuleiro solicitar."),
            ("Créditos", f"As ajudas custam {HELP_COST} créditos de carbono e só uma pode ser usada por rodada."),
            ("Erro", "Ao errar, você pode voltar ao início e perder os créditos conforme as regras da partida."),
            ("Parar", "Volta para o início e perde metade do saldo."),
        ]
        for heading, description in sections:
            card = self.card(padding=9, spacing=2)
            card.add_widget(self.label(f"[b]{heading}[/b]\n{description}", 14, False, TEXT, min_height=58))
            self.finalize_card(card)
            body.add_widget(card)
        self.open_mobile_info_popup("Como jogar", body)

    def add_minimize_button(self, body: BoxLayout, text: str = "Ocultar e ver o mapa") -> None:
        body.add_widget(self.make_button(
            text,
            self.minimize_game_popup,
            height=48,
            background_color=INFO_FILL,
            font_size=14,
        ))

    def build_question_mobile_popup(self, q: dict[str, Any], my_turn: bool) -> tuple[ScrollView, tuple[Any, ...]]:
        # Referências vivas usadas por ``tick_timer``. Elas precisam apontar
        # para o Label que realmente será inserido no popup aberto.
        self.roll_dice_widget = None
        self.roll_status_label = None
        self.roll_button = None
        scroll, body = self.mobile_dialog_body()
        remaining = self.remaining_seconds()
        cp = self.current_player()
        saldo = int((cp or {}).get("credits", 0))
        eliminated = tuple(sorted(q.get("eliminated_options") or []))
        help_used = bool((self.state or {}).get("help_used_this_turn"))
        signature = (
            "question",
            str(q.get("id")),
            eliminated,
            help_used,
            saldo,
            my_turn,
            str(q.get("prompt") or ""),
        )

        timer = self.card(
            padding=7,
            spacing=1,
            bg_color=ERROR_FILL if remaining <= 10 else INFO_FILL,
            border_color=RED if remaining <= 10 else DARK,
        )
        self.timer_label = self.label(
            f"Tempo: [b]{remaining}s[/b]",
            25, False, RED if remaining <= 10 else DARK, min_height=40, halign="center",
        )
        timer.add_widget(self.timer_label)
        timer.add_widget(self.label(
            f"{DIFF_LABELS.get(q.get('difficulty'), q.get('difficulty'))} • saldo: [b]{saldo} créditos[/b]",
            14, False, DARK, min_height=28, halign="center",
        ))
        self.finalize_card(timer)
        body.add_widget(timer)

        question = self.card(padding=11, spacing=4, bg_color=CARD, border_color=DARK)
        question.add_widget(self.label("PERGUNTA", 14, True, DARK, min_height=26))
        question.add_widget(self.label(str(q.get("prompt") or ""), 18, False, TEXT, min_height=78))
        self.finalize_card(question)
        body.add_widget(question)

        answers = self.card(padding=9, spacing=7, bg_color=ANSWER_FILL, border_color=DARK)
        answers.add_widget(self.label("RESPOSTAS", 18, True, DARK, min_height=30))
        letters = ["A", "B", "C", "D"]
        eliminated_set = set(eliminated)
        for idx, option in enumerate(q.get("options") or []):
            removed = idx in eliminated_set
            label = f"{letters[idx]}) {option}"
            if removed:
                label += "\nALTERNATIVA ELIMINADA"
            answers.add_widget(self.make_button(
                label,
                lambda i=idx: self.send({"type": "answer", "answer_index": i}),
                disabled=removed or not my_turn,
                height=62,
                background_color=WHITE,
                font_size=15,
            ))
        self.finalize_card(answers)
        body.add_widget(answers)

        helps = self.card(padding=9, spacing=7, bg_color=HELP_CARD, border_color=(0.65, 0.47, 0.08, 1))
        helps.add_widget(self.label("AJUDAS", 18, True, DARK, min_height=30))
        state_message = f"Cada ajuda custa {HELP_COST} créditos. Use no máximo uma por rodada."
        if help_used:
            state_message += " Uma ajuda já foi utilizada."
        elif saldo < HELP_COST:
            state_message += " Saldo insuficiente."
        helps.add_widget(self.label(state_message, 13, False, TEXT, min_height=44))
        help_disabled = (not my_turn) or help_used or saldo < HELP_COST
        grid = self.button_grid(cols=2, height=132)
        help_specs = [
            ("Eliminar 2", "eliminate2"),
            (f"Pesquisa +{RESEARCH_BONUS_SECONDS}s", "research"),
            ("Especialista", "expert"),
            ("Pular pergunta", "skip"),
        ]
        for label, code in help_specs:
            grid.add_widget(self.make_button(
                f"{label}\nCusto: {HELP_COST}",
                lambda h=code: self.send({"type": "help", "help": h}),
                disabled=help_disabled,
                height=60,
                background_color=HELP_FILL,
                font_size=13,
            ))
        helps.add_widget(grid)
        self.finalize_card(helps)
        body.add_widget(helps)

        stop = self.card(padding=9, spacing=5, bg_color=WARNING_FILL, border_color=RED)
        stop.add_widget(self.label("PARAR", 17, True, RED, min_height=28))
        stop.add_widget(self.label(
            "Volta para o início e perde metade do saldo.",
            13, False, TEXT, min_height=44,
        ))
        stop.add_widget(self.make_button(
            "Parar",
            lambda: self.send({"type": "stop"}),
            disabled=not my_turn,
            height=54,
            background_color=ERROR_FILL,
            text_color=RED,
            font_size=14,
        ))
        self.finalize_card(stop)
        body.add_widget(stop)

        if not my_turn:
            body.add_widget(self.label("Aguardando o jogador da vez responder.", 14, True, DARK, min_height=34, halign="center"))
        self.add_minimize_button(body)
        return scroll, signature

    def build_consequence_mobile_popup(self, cp: dict[str, Any] | None, my_turn: bool) -> tuple[ScrollView, tuple[Any, ...], str]:
        scroll, body = self.mobile_dialog_body()
        result = dict((self.state or {}).get("turn_result") or {})
        kind = str(result.get("kind") or "result")
        styles = {
            "correct": (SUCCESS_FILL, DARK, "RESPOSTA CORRETA"),
            "incorrect": (ERROR_FILL, RED, "RESPOSTA INCORRETA"),
            "timeout": (ERROR_FILL, RED, "TEMPO ESGOTADO"),
            "skipped": (INFO_FILL, DARK, "PERGUNTA PULADA"),
            "stopped": (WARNING_FILL, RED, "JOGADOR PAROU"),
            "luck_gain": (SUCCESS_FILL, DARK, "SORTE"),
            "luck_loss": (WARNING_FILL, RED, "REVÉS"),
        }
        bg_color, accent, fallback = styles.get(kind, (INFO_FILL, DARK, "CONSEQUÊNCIA"))
        title = str(result.get("title") or fallback)
        message = str(result.get("message") or (self.state or {}).get("special_event") or "Rodada concluída.")
        signature = (
            "result",
            str((self.state or {}).get("turn_phase")),
            json.dumps(result, sort_keys=True, default=str),
            my_turn,
        )

        card = self.card(padding=13, spacing=8, bg_color=bg_color, border_color=accent)
        card.add_widget(self.label(title, 27, True, accent, min_height=48, halign="center"))
        card.add_widget(self.label(message, 16, False, TEXT, min_height=72, halign="center"))
        old_credits, new_credits = result.get("old_credits"), result.get("new_credits")
        if old_credits is not None and new_credits is not None:
            delta = int(result.get("credit_delta") or 0)
            delta_text = f"+{delta}" if delta > 0 else str(delta)
            card.add_widget(self.label(
                f"[b]Saldo:[/b] {old_credits} → {new_credits} créditos ({delta_text})",
                17, False, DARK, min_height=36, halign="center",
            ))
        old_position, new_position = result.get("old_position_label"), result.get("new_position_label")
        if old_position and new_position and old_position != new_position:
            card.add_widget(self.label(
                f"[b]Posição:[/b] {old_position} → {new_position}",
                16, False, DARK, min_height=34, halign="center",
            ))
        correct_answer = str(result.get("correct_answer") or "").strip()
        if correct_answer:
            card.add_widget(self.label(f"[b]Resposta correta:[/b] {correct_answer}", 15, False, DARK, min_height=52))
        self.finalize_card(card)
        body.add_widget(card)

        button_text = "Continuar" if (self.state or {}).get("turn_phase") == "luck_result" else "Próximo jogador"
        body.add_widget(self.make_button(
            button_text,
            lambda: self.send({"type": "continue"}),
            disabled=not my_turn,
            height=58,
            font_size=17,
        ))
        if not my_turn:
            body.add_widget(self.label(
                f"Aguardando {(cp or {}).get('name') or 'o jogador da vez'} continuar.",
                14, False, TEXT, min_height=34, halign="center",
            ))
        self.add_minimize_button(body, "Ocultar resultado e ver o mapa")
        return scroll, signature, title

    def build_roll_mobile_popup(self, cp: dict[str, Any], my_turn: bool) -> tuple[ScrollView, tuple[Any, ...]]:
        # A animação atualiza estas referências a cada frame. Limpar o Label
        # do cronômetro evita conservar um widget pertencente ao popup anterior.
        self.timer_label = None
        scroll, body = self.mobile_dialog_body()
        signature = ("roll", cp.get("id"), my_turn)
        intro = self.card(padding=12, spacing=6, bg_color=INFO_FILL, border_color=DARK)
        intro.add_widget(self.label("JOGAR DADO", 25, True, DARK, min_height=42, halign="center"))
        intro.add_widget(self.label(
            f"{cp.get('name')} está em {pos_label(self.state, cp.get('position'))}.",
            16, False, TEXT, min_height=44, halign="center",
        ))
        self.roll_value_label = None
        dice_anchor = AnchorLayout(size_hint_y=None, height=dp(116), anchor_x="center", anchor_y="center")
        self.roll_dice_widget = DiceFace(value=max(1, int(self.dice_value)))
        dice_anchor.add_widget(self.roll_dice_widget)
        intro.add_widget(dice_anchor)
        self.roll_status_label = self.label("Pronto para lançar", 14, False, TEXT, min_height=34, halign="center")
        intro.add_widget(self.roll_status_label)
        self.finalize_card(intro)
        body.add_widget(intro)
        self.roll_button = self.make_button("Jogar dado", self.start_dice_animation, disabled=not my_turn, height=62, font_size=18)
        body.add_widget(self.roll_button)
        if not my_turn:
            body.add_widget(self.label("Aguardando o jogador da vez lançar.", 14, False, TEXT, min_height=34, halign="center"))
        self.add_minimize_button(body)
        self.update_roll_mobile_widgets()
        return scroll, signature

    def update_roll_mobile_widgets(self) -> None:
        if self.roll_status_label is None or self.roll_button is None:
            return
        if self.roll_dice_widget is not None:
            self.roll_dice_widget.value = max(1, min(6, int(self.dice_value)))
            if not self.dice_animating and not self.dice_revealing:
                self.roll_dice_widget.scale = 1.0
                self.roll_dice_widget.jitter_x = 0
                self.roll_dice_widget.jitter_y = 0
                self.roll_dice_widget.angle = 0
            self.roll_dice_widget.redraw()
            self.roll_dice_widget.canvas.ask_update()
        if self.dice_revealing:
            self.roll_status_label.text = "Resultado sorteado. O peão avançará em instantes..."
            self.roll_button.text = "Resultado exibido"
        elif self.dice_animating:
            self.roll_status_label.text = "Rolando o dado..."
            self.roll_button.text = "Rolando..."
        else:
            self.roll_status_label.text = "Pronto para lançar"
            self.roll_button.text = "Jogar dado"
        self.roll_button.disabled = (not self.is_my_turn()) or self.dice_animating or self.dice_revealing

    def build_ready_mobile_popup(self, cp: dict[str, Any], my_turn: bool) -> tuple[ScrollView, tuple[Any, ...]]:
        scroll, body = self.mobile_dialog_body()
        pending = (self.state or {}).get("pending_question_difficulty")
        signature = ("ready", cp.get("id"), pending, my_turn, (self.state or {}).get("last_roll"))
        card = self.card(padding=13, spacing=8, bg_color=INFO_FILL, border_color=DARK)
        card.add_widget(self.label("PRONTO PARA A PERGUNTA", 23, True, DARK, min_height=42, halign="center"))
        roll_text = f" O dado mostrou {(self.state or {}).get('last_roll')}." if (self.state or {}).get("last_roll") else ""
        card.add_widget(self.label(
            f"{cp.get('name')} chegou à casa {pos_label(self.state, cp.get('position'))}.{roll_text}\n"
            f"Nível: [b]{DIFF_LABELS.get(pending, pending or '')}[/b]",
            16, False, TEXT, min_height=78, halign="center",
        ))
        card.add_widget(self.label("O cronômetro começa ao tocar no botão abaixo.", 14, False, TEXT, min_height=34, halign="center"))
        self.finalize_card(card)
        body.add_widget(card)
        body.add_widget(self.make_button(
            "Iniciar pergunta",
            lambda: self.send({"type": "begin_question"}),
            disabled=not my_turn,
            height=62,
            font_size=18,
        ))
        if not my_turn:
            body.add_widget(self.label("Aguardando o jogador da vez iniciar.", 14, False, TEXT, min_height=34, halign="center"))
        self.add_minimize_button(body)
        return scroll, signature

    def build_wait_mobile_popup(self) -> tuple[ScrollView, tuple[Any, ...]]:
        scroll, body = self.mobile_dialog_body()
        phase = str((self.state or {}).get("turn_phase") or "waiting")
        signature = ("wait", phase, (self.state or {}).get("current_player_id"))
        card = self.card(padding=14, spacing=8, bg_color=INFO_FILL, border_color=DARK)
        card.add_widget(self.label("PARTIDA EM ANDAMENTO", 23, True, DARK, min_height=42, halign="center"))
        card.add_widget(self.label("Aguardando o servidor preparar a próxima ação.", 16, False, TEXT, min_height=64, halign="center"))
        self.finalize_card(card)
        body.add_widget(card)
        self.add_minimize_button(body)
        return scroll, signature

    def show_current_mobile_action(self, force: bool = True) -> None:
        if self.current_screen == "ended":
            self.show_end_mobile_popup(force=force)
            return
        self.sync_mobile_game_popup(force=force)

    def sync_mobile_game_popup(self, force: bool = False) -> None:
        """Synchronizes the fixed in-screen action sheet with server state."""
        if not self.state or self.state.get("status") != "playing":
            return
        q = self.state.get("current_question")
        cp = self.current_player()
        my_turn = self.is_my_turn()
        phase = str(self.state.get("turn_phase") or "")

        if q:
            saldo = int((cp or {}).get("credits", 0))
            signature = (
                "question",
                str(q.get("id")),
                tuple(sorted(q.get("eliminated_options") or [])),
                bool(self.state.get("help_used_this_turn")),
                saldo,
                my_turn,
                str(q.get("prompt") or ""),
            )
            if not force and (
                (self.game_action_panel is not None and self.game_action_signature == signature)
                or self.game_action_suppressed_signature == signature
            ):
                return
            self.dismiss_game_popup(programmatic=True)
            content, signature = self.build_question_mobile_popup(q, my_turn)
            title = f"Pergunta • {DIFF_LABELS.get(q.get('difficulty'), q.get('difficulty'))}"
            self.open_game_popup("question", signature, title, content, force=force)
            return

        if phase in {"turn_result", "luck_result"}:
            result = dict(self.state.get("turn_result") or {})
            signature = (
                "result",
                phase,
                json.dumps(result, sort_keys=True, default=str),
                my_turn,
            )
            if not force and (
                (self.game_action_panel is not None and self.game_action_signature == signature)
                or self.game_action_suppressed_signature == signature
            ):
                return
            self.dismiss_game_popup(programmatic=True)
            content, signature, title = self.build_consequence_mobile_popup(cp, my_turn)
            self.open_game_popup("result", signature, title, content, force=force)
            return

        if phase == "awaiting_roll" and cp:
            signature = ("roll", cp.get("id"), my_turn)
            if self.game_action_panel is not None and self.game_action_signature == signature:
                self.update_roll_mobile_widgets()
                return
            if not force and self.game_action_suppressed_signature == signature:
                return
            self.dismiss_game_popup(programmatic=True)
            content, signature = self.build_roll_mobile_popup(cp, my_turn)
            self.open_game_popup("roll", signature, "Lançamento do dado", content, force=force)
            return

        if phase == "awaiting_question" and cp:
            signature = ("ready", cp.get("id"), self.state.get("pending_question_difficulty"), my_turn, self.state.get("last_roll"))
            if not force and (
                (self.game_action_panel is not None and self.game_action_signature == signature)
                or self.game_action_suppressed_signature == signature
            ):
                return
            self.dismiss_game_popup(programmatic=True)
            content, signature = self.build_ready_mobile_popup(cp, my_turn)
            self.open_game_popup("ready", signature, "Preparar pergunta", content, force=force)
            return

        signature = ("wait", phase or "waiting", self.state.get("current_player_id"))
        if not force and (
            (self.game_action_panel is not None and self.game_action_signature == signature)
            or self.game_action_suppressed_signature == signature
        ):
            return
        self.dismiss_game_popup(programmatic=True)
        content, signature = self.build_wait_mobile_popup()
        self.open_game_popup("wait", signature, "Partida", content, force=force)

    def render_game(self) -> None:
        """HUD mobile: mapa em tela cheia e ações em painel fixo sobreposto."""
        self.current_screen = "game"
        self.apply_layout_for_current_mode()
        self.force_game_scroll_top = False
        if not self.state:
            return
        self.rebuild_mobile_hud(ended=False)
        self.sync_mobile_game_popup(force=False)

    def render_question_area(self, q: dict[str, Any], my_turn: bool) -> None:
        remaining = self.remaining_seconds()
        qid = str(q.get("id"))
        if my_turn and remaining <= 0 and self.timeout_sent_for_question != qid:
            self.timeout_sent_for_question = qid
            self.send({"type": "timeout"})
        if remaining > 0:
            self.timeout_sent_for_question = None

        timer_bg = ERROR_FILL if remaining <= 10 else INFO_FILL
        timer_border = RED if remaining <= 10 else DARK
        timer = self.card(padding=9, spacing=2, bg_color=timer_bg, border_color=timer_border)
        self.timer_label = self.label(
            f"Tempo: [b]{remaining}s[/b]",
            26, False, RED if remaining <= 10 else DARK, min_height=38, halign="center",
        )
        timer.add_widget(self.timer_label)
        timer.add_widget(self.label(
            f"Nível: {DIFF_LABELS.get(q.get('difficulty'), q.get('difficulty'))}",
            15, False, DARK, min_height=27, halign="center",
        ))
        self.finalize_card(timer)
        self.add(timer)

        question_box = self.card(padding=12, spacing=4, bg_color=CARD, border_color=DARK)
        question_box.add_widget(self.label("PERGUNTA", 15, True, DARK, min_height=28))
        question_box.add_widget(self.label(q.get("prompt", ""), 18, False, TEXT, min_height=76))
        self.finalize_card(question_box)
        self.add(question_box)

        answers = self.card(padding=10, spacing=7, bg_color=ANSWER_FILL, border_color=DARK)
        answers.add_widget(self.label("RESPOSTAS", 18, True, DARK, min_height=30))
        eliminated = set(q.get("eliminated_options") or [])
        letters = ["A", "B", "C", "D"]
        for idx, opt in enumerate(q.get("options") or []):
            disabled = (idx in eliminated) or not my_turn
            txt = f"{letters[idx]}) {opt}"
            if idx in eliminated:
                txt += "\nALTERNATIVA ELIMINADA"
            answers.add_widget(self.make_button(
                txt,
                lambda i=idx: self.send({"type": "answer", "answer_index": i}),
                disabled=disabled,
                height=64,
                background_color=WHITE,
                font_size=16,
            ))
        self.finalize_card(answers)
        self.add(answers)

        cp = self.current_player()
        saldo = int(cp.get("credits", 0)) if cp else 0
        balance = self.card(
            padding=11,
            spacing=3,
            bg_color=SUCCESS_FILL if saldo >= HELP_COST else WARNING_FILL,
            border_color=DARK,
        )
        balance.add_widget(self.label("SALDO DE CARBONO", 16, True, DARK, min_height=28, halign="center"))
        balance.add_widget(self.label(f"[b]{saldo} créditos[/b]", 29, False, DARK, min_height=46, halign="center"))
        balance.add_widget(self.label(
            f"Cada ajuda custa [b]{HELP_COST} créditos[/b]. "
            + ("Você pode comprar uma ajuda." if saldo >= HELP_COST else "Saldo insuficiente para comprar ajuda."),
            15, False, DARK, min_height=42, halign="center",
        ))
        self.finalize_card(balance)
        self.add(balance)

        help_used = bool((self.state or {}).get("help_used_this_turn"))
        help_disabled = (not my_turn) or help_used or saldo < HELP_COST
        helps = self.card(
            padding=10,
            spacing=7,
            bg_color=HELP_CARD,
            border_color=(0.65, 0.47, 0.08, 1),
        )
        helps.add_widget(self.label("AJUDAS", 20, True, DARK, min_height=32))
        helps.add_widget(self.label(
            f"São recursos opcionais, não respostas. Use no máximo uma por rodada. Custo unitário: {HELP_COST} créditos.",
            14, False, TEXT, min_height=48,
        ))
        if help_used:
            helps.add_widget(self.label("Ajuda já utilizada nesta rodada.", 14, True, RED, min_height=28))
        elif saldo < HELP_COST:
            helps.add_widget(self.label("Você não possui créditos suficientes.", 14, True, RED, min_height=28))

        grid = self.button_grid(cols=2, height=126)
        grid.add_widget(self.make_button(
            f"Eliminar 2 respostas\nCusto: {HELP_COST}",
            lambda: self.send({"type": "help", "help": "eliminate2"}),
            disabled=help_disabled,
            height=58,
            background_color=HELP_FILL,
            font_size=14,
        ))
        grid.add_widget(self.make_button(
            f"Pesquisa: +{RESEARCH_BONUS_SECONDS}s\nCusto: {HELP_COST}",
            lambda: self.send({"type": "help", "help": "research"}),
            disabled=help_disabled,
            height=58,
            background_color=HELP_FILL,
            font_size=14,
        ))
        grid.add_widget(self.make_button(
            f"Dica do especialista\nCusto: {HELP_COST}",
            lambda: self.send({"type": "help", "help": "expert"}),
            disabled=help_disabled,
            height=58,
            background_color=HELP_FILL,
            font_size=14,
        ))
        grid.add_widget(self.make_button(
            f"Pular a pergunta\nCusto: {HELP_COST}",
            lambda: self.send({"type": "help", "help": "skip"}),
            disabled=help_disabled,
            height=58,
            background_color=HELP_FILL,
            font_size=14,
        ))
        helps.add_widget(grid)
        self.finalize_card(helps)
        self.add(helps)

    def render_pause_area(self, cp: dict[str, Any] | None, my_turn: bool) -> None:
        self.timer_label = None
        phase = self.state.get("turn_phase") if self.state else None
        pending = self.state.get("pending_question_difficulty") if self.state else None

        if phase in {"turn_result", "luck_result"}:
            self.render_consequence_area(cp, my_turn)
            return

        pause = self.card(padding=12, spacing=8)
        if phase == "awaiting_roll" and cp:
            pause.add_widget(self.label("Jogar dado", 24, True, DARK, min_height=40, halign="center"))
            pause.add_widget(self.label(
                f"{cp.get('name')} está em {pos_label(self.state, cp.get('position'))}. Toque para lançar o dado e avançar no tabuleiro.",
                16, False, TEXT, min_height=64, halign="center",
            ))
            dice_card = self.card(padding=8, spacing=4, bg_color=INFO_FILL)
            dice_card.add_widget(self.label(
                f"[b]{self.dice_value if self.dice_animating else '?'}[/b]",
                46, True, DARK, min_height=76, halign="center",
            ))
            if self.dice_revealing:
                dice_status = "Resultado sorteado. O peão anda em 1 segundo..."
                btn_text = "Resultado exibido"
            elif self.dice_animating:
                dice_status = "Rolando o dado..."
                btn_text = "Rolando..."
            else:
                dice_status = "Pronto para lançar"
                btn_text = "Jogar dado"
            dice_card.add_widget(self.label(dice_status, 14, False, TEXT, min_height=34, halign="center"))
            self.finalize_card(dice_card)
            pause.add_widget(dice_card)
            pause.add_widget(self.make_button(
                btn_text,
                self.start_dice_animation,
                disabled=(not my_turn or self.dice_animating),
                height=62,
                font_size=17,
            ))
        elif phase == "awaiting_question" and cp:
            pause.add_widget(self.label("PRONTO PARA A PERGUNTA", 23, True, DARK, min_height=40, halign="center"))
            roll_txt = f" Dado: {self.state.get('last_roll')}." if self.state.get("last_roll") else ""
            pause.add_widget(self.label(
                f"{cp.get('name')} está na casa {pos_label(self.state, cp.get('position'))}.{roll_txt}\n"
                f"Nível da pergunta: [b]{DIFF_LABELS.get(pending, pending or '')}[/b].",
                17, False, TEXT, min_height=78, halign="center",
            ))
            pause.add_widget(self.label(
                "O cronômetro só começa ao tocar em Iniciar pergunta.",
                14, False, TEXT, min_height=32, halign="center",
            ))
            pause.add_widget(self.make_button(
                "Iniciar pergunta",
                lambda: self.send({"type": "begin_question"}),
                disabled=not my_turn,
                height=62,
                font_size=18,
            ))
            if not my_turn:
                pause.add_widget(self.label(
                    "Aguardando o jogador da vez iniciar.",
                    14, False, TEXT, min_height=30, halign="center",
                ))
        else:
            pause.add_widget(self.label(
                "Aguardando o servidor preparar a próxima rodada...",
                17, False, TEXT, min_height=70, halign="center",
            ))
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

    def build_end_mobile_content(self) -> ScrollView:
        scroll, body = self.mobile_dialog_body()
        rows = list((self.state or {}).get("ranking") or [])
        if not rows:
            body.add_widget(self.label("Sem ranking disponível.", 15, False, TEXT, min_height=48))
        for idx, row in enumerate(rows, start=1):
            status = ""
            if row.get("eliminated"):
                status = " • eliminado"
            elif row.get("stopped"):
                status = " • parou"
            card = self.card(
                padding=10,
                spacing=3,
                bg_color=SUCCESS_FILL if idx == 1 else CARD,
                border_color=DARK,
            )
            card.add_widget(self.label(f"[b]{idx}º {row.get('name')}[/b]", 19, False, DARK, min_height=32))
            card.add_widget(self.label(
                f"Casa {row.get('display_position', row.get('position'))} • {row.get('credits')} créditos{status}",
                14, False, TEXT, min_height=28,
            ))
            self.finalize_card(card)
            body.add_widget(card)
        body.add_widget(self.make_button("Voltar ao menu", self.return_to_menu, height=58, font_size=17))
        self.add_minimize_button(body, "Ocultar resultado e ver o mapa")
        return scroll

    def show_end_mobile_popup(self, force: bool = False) -> None:
        rows = list((self.state or {}).get("ranking") or [])
        signature = ("ended", json.dumps(rows, sort_keys=True, default=str))
        if not force and (
            (self.game_action_panel is not None and self.game_action_signature == signature)
            or self.game_action_suppressed_signature == signature
        ):
            return
        self.dismiss_game_popup(programmatic=True)
        content = self.build_end_mobile_content()
        self.open_game_popup("ended", signature, "Fim de jogo", content, force=force)

    def render_ended(self) -> None:
        self.timer_label = None
        self.current_screen = "ended"
        self.apply_layout_for_current_mode()
        self.rebuild_mobile_hud(ended=True)
        self.show_end_mobile_popup(force=False)

    def on_stop(self) -> None:
        self.network.close()


if __name__ == "__main__":
    GreenImpactAndroidApp().run()
