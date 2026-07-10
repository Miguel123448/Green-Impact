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
from kivy.uix.image import Image
from kivy.uix.label import Label
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
        board_path = ASSET_DIR / "board.jpg"
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
        if self.loop and self.loop.is_running():
            return

        def runner() -> None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self.thread = threading.Thread(target=runner, daemon=True)
        self.thread.start()
        while self.loop is None:
            time.sleep(0.02)

    def connect(self, url: str, name: str, room: str | None, game_mode: str = "dice_board", local_count: int | None = None, local_names: list[str] | None = None) -> None:
        self._ensure_loop()
        assert self.loop is not None
        asyncio.run_coroutine_threadsafe(self._connect(url, name, room, game_mode, local_count, local_names or []), self.loop)

    async def _connect(self, url: str, name: str, room: str | None, game_mode: str = "dice_board", local_count: int | None = None, local_names: list[str] | None = None) -> None:
        try:
            self.on_log(f"Conectando em {url}...")
            self.ws = await websockets.connect(url)
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
        self.lan_ip = get_lan_ip()
        self.msg_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.network = NetworkClient(self.queue_message, self.log)
        self.root_layout: BoxLayout | None = None
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

    def build(self) -> BoxLayout:
        Window.clearcolor = BG
        if platform != "android":
            Window.size = (1280, 720)
        self.root_layout = BoxLayout(orientation="horizontal", padding=dp(6), spacing=dp(8))
        self.board = BoardWidget(size_hint=(0.40, 1))
        self.panel = RoundedBox(orientation="vertical", bg_color=PANEL, size_hint=(0.60, 1), padding=dp(0), spacing=dp(0))
        self.root_layout.add_widget(self.board)
        self.root_layout.add_widget(self.panel)
        Clock.schedule_interval(self.process_messages, 0.08)
        Clock.schedule_interval(self.tick_timer, 0.5)
        self.render_main_menu()
        return self.root_layout

    def apply_layout_for_current_mode(self) -> None:
        """Ajusta a proporção da tela conforme o tabuleiro usado.

        O tabuleiro novo é horizontal. Em celulares/tablets, o layout antigo
        com tabuleiro estreito à esquerda deixava o HUD apertado. Durante
        partidas com dado, o tabuleiro fica em cima e o HUD embaixo.
        """
        if not self.root_layout or not self.board or not self.panel:
            return
        new_board = bool(self.state and self.state.get("game_mode") != "classic" and self.current_screen in {"game", "ended"})
        if new_board:
            self.root_layout.orientation = "vertical"
            self.board.size_hint = (1, 0.44)
            self.panel.size_hint = (1, 0.56)
        else:
            self.root_layout.orientation = "horizontal"
            self.board.size_hint = (0.40, 1)
            self.panel.size_hint = (0.60, 1)
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

    def make_button(self, text: str, callback: Callable[[], None], disabled: bool = False, height: int = 50) -> Button:
        btn = Button(
            text=text,
            size_hint_y=None,
            height=dp(height),
            disabled=disabled,
            background_normal="",
            background_color=DISABLED if disabled else GREEN_FILL,
            color=DARK,
            font_size=dp(15),
            halign="center",
            valign="middle",
        )
        btn.bind(width=lambda b, *_: setattr(b, "text_size", (max(b.width - dp(14), dp(40)), None)))
        btn.bind(on_release=lambda *_: callback())
        return btn

    def make_input(self, text: str = "", multiline: bool = False) -> TextInput:
        return TextInput(
            text=text,
            multiline=multiline,
            size_hint_y=None,
            height=dp(48),
            font_size=dp(17),
            background_color=WHITE,
            foreground_color=TEXT,
            cursor_color=DARK,
            padding=[dp(10), dp(9), dp(10), dp(9)],
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
                self.state = data.get("room")
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
        deadline = float(self.state.get("deadline_ts") or 0)
        return max(0, int(deadline - (time.time() + self.server_delta)))

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
            self.add(Image(source=str(logo_path), size_hint_y=None, height=dp(100), allow_stretch=True, keep_ratio=True))
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
        info.add_widget(self.label(
            f"No modo Um jogador o app abre um servidor local automaticamente. Para multiplayer na mesma rede, outros aparelhos podem usar o IP do servidor. IP local detectado: [b]{self.lan_ip}[/b].",
            14,
            False,
            TEXT,
            min_height=50,
        ))
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
            ("Parar", "Você pode parar para evitar o risco de perder tudo. Nesse caso, não joga mais e fica com metade dos créditos."),
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
        """Anima o dado, revela o resultado por 1 segundo e depois move o peão."""
        if self.dice_animating:
            return
        self.dice_animating = True
        self.dice_revealing = False
        self.dice_roll_sent = False
        self.dice_final_value = random.randint(1, 6)
        self.dice_value = random.randint(1, 6)
        self.render_game()

        def update_visual(_dt: float) -> bool:
            if not self.dice_animating or self.dice_revealing:
                return False
            self.dice_value = random.randint(1, 6)
            if self.state and self.state.get("turn_phase") == "awaiting_roll":
                self.render_game()
            return True

        def reveal_roll(_dt: float) -> None:
            if not self.dice_animating:
                return
            if self._dice_clock_event is not None:
                self._dice_clock_event.cancel()
                self._dice_clock_event = None
            self.dice_revealing = True
            self.dice_value = self.dice_final_value
            self.render_game()

        def send_roll(_dt: float) -> None:
            if self.dice_roll_sent:
                return
            self.dice_roll_sent = True
            self.dice_animating = False
            self.dice_revealing = False
            if self.state and self.state.get("turn_phase") == "awaiting_roll":
                self.render_game()
                self.send({"type": "roll", "roll": self.dice_final_value})

        self._dice_clock_event = Clock.schedule_interval(update_visual, 0.08)
        Clock.schedule_once(reveal_roll, 0.90)
        Clock.schedule_once(send_roll, 1.90)

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
        self.add(self.title_label("Multijogador online", 30))
        self.add(self.label("Criar sala abre uma partida nova. Entrar na sala usa o código mostrado para quem criou a partida.", 15, False, TEXT, min_height=58))

        previous_name = self.name_input.text if self.name_input else (self.home_name_input.text if self.home_name_input else "Jogador")
        previous_room = self.room_input.text if self.room_input else ""
        previous_host = self.host_input.text if self.host_input else DEFAULT_SERVER_HOST
        previous_port = self.port_input.text if self.port_input else DEFAULT_SERVER_PORT

        form = self.card()
        form.add_widget(self.label("Seu nome", 14, False, DARK, min_height=22))
        self.name_input = self.make_input(previous_name)
        form.add_widget(self.name_input)
        form.add_widget(self.label("Código da sala", 14, False, DARK, min_height=22))
        self.room_input = self.make_input(previous_room)
        form.add_widget(self.room_input)
        self.host_input = self.make_input(previous_host)
        self.port_input = self.make_input(previous_port)
        self.finalize_card(form)
        self.add(form)

        grid = self.button_grid(cols=2, height=112)
        grid.add_widget(self.make_button("Criar nova sala", self.create_room_on_ip, height=52))
        grid.add_widget(self.make_button("Entrar com código", self.join_room_on_ip, height=52))
        grid.add_widget(self.make_button("Como jogar", self.open_how_to_play, height=52))
        grid.add_widget(self.make_button("Voltar", self.render_main_menu, height=52))
        self.add(grid)

        help_box = self.card()
        help_box.add_widget(self.label(
            "IP e porta ficam configurados internamente. Para jogar em rede local, use a opção Servidor local em uma versão de teste/PC ou mantenha o servidor online ativo.",
            13, False, TEXT, min_height=62,
        ))
        self.finalize_card(help_box)
        self.add(help_box)
        if self.connection_error:
            self.add(self.label("Erro: " + self.connection_error, 14, False, RED, min_height=36))
        if self.messages:
            self.add(self.message_box())

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
        host = (self.host_input.text if self.host_input else DEFAULT_SERVER_HOST).strip() or DEFAULT_SERVER_HOST
        port = (self.port_input.text if self.port_input else DEFAULT_SERVER_PORT).strip() or DEFAULT_SERVER_PORT
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
        self.clear_panel(preserve_scroll=True)
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

    def render_question_area(self, q: dict[str, Any], my_turn: bool) -> None:
        remaining = self.remaining_seconds()
        qid = str(q.get("id"))
        if my_turn and remaining == 0 and self.timeout_sent_for_question != qid:
            self.timeout_sent_for_question = qid
            self.send({"type": "timeout"})
        if remaining > 0:
            self.timeout_sent_for_question = None

        timer = self.card(padding=8, spacing=2)
        self.timer_label = self.label(f"Tempo: [b]{remaining}s[/b]", 24, False, RED if remaining <= 10 else DARK, min_height=34)
        timer.add_widget(self.timer_label)
        timer.add_widget(self.label(f"Pergunta: {DIFF_LABELS.get(q.get('difficulty'), q.get('difficulty'))}", 15, False, DARK, min_height=26))
        self.finalize_card(timer)
        self.add(timer)

        question_box = self.card(padding=10, spacing=2)
        question_box.add_widget(self.label(q.get("prompt", ""), 17, False, TEXT, min_height=68))
        self.finalize_card(question_box)
        self.add(question_box)

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
        grid = self.button_grid(cols=2, height=174)
        grid.add_widget(self.make_button("Eliminar 2 alternativas", lambda: self.send({"type": "help", "help": "eliminate2"}), disabled=(not my_turn or self.state.get("help_used_this_turn")), height=52))
        grid.add_widget(self.make_button("Pesquisa (+20s)", lambda: self.send({"type": "help", "help": "research"}), disabled=(not my_turn or self.state.get("help_used_this_turn")), height=52))
        grid.add_widget(self.make_button("Especialista", lambda: self.send({"type": "help", "help": "expert"}), disabled=(not my_turn or self.state.get("help_used_this_turn")), height=52))
        grid.add_widget(self.make_button("Pular pergunta", lambda: self.send({"type": "help", "help": "skip"}), disabled=(not my_turn or self.state.get("help_used_this_turn")), height=52))
        helps.add_widget(grid)
        self.finalize_card(helps)
        self.add(helps)

        stop_card = self.card(padding=8, spacing=4)
        stop_card.add_widget(self.label("Desistir da partida", 16, True, DARK, min_height=28))
        stop_card.add_widget(self.label("Use Parar apenas se não quiser arriscar perder tudo. Você fica com metade dos créditos e sai das próximas rodadas.", 13, False, TEXT, min_height=50))
        stop_card.add_widget(self.make_button("Parar", lambda: self.send({"type": "stop"}), disabled=not my_turn, height=54))
        self.finalize_card(stop_card)
        self.add(stop_card)

    def render_pause_area(self, cp: dict[str, Any] | None, my_turn: bool) -> None:
        self.timer_label = None
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
            dice_card.add_widget(self.label(f"[b]{self.dice_value if self.dice_animating else '?'}[/b]", 46, True, DARK, min_height=76, halign="center"))
            if self.dice_revealing:
                dice_status = "Resultado sorteado. O peão anda em 1 segundo..."
                btn_text = "Resultado exibido"
            elif self.dice_animating:
                dice_status = "Rolando o dado..."
                btn_text = "Rolando..."
            else:
                dice_status = "Pronto para lançar"
                btn_text = "Jogar dado"
            dice_card.add_widget(self.label(dice_status, 13, False, TEXT, min_height=34, halign="center"))
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
            pause.add_widget(self.label(f"Vez de {cp.get('name')}", 26, True, DARK, min_height=44))
            roll_txt = f" Dado: {self.state.get('last_roll')}." if self.state.get("last_roll") else ""
            pause.add_widget(self.label(
                f"{cp.get('name')} está em {pos_label(self.state, cp.get('position'))}.{roll_txt} A pergunta será: [b]{DIFF_LABELS.get(pending, pending or '')}[/b]. O cronômetro só começa depois de tocar no botão abaixo.",
                15,
                False,
                TEXT,
                min_height=86,
            ))
            pause.add_widget(self.make_button("Iniciar pergunta", lambda: self.send({"type": "begin_question"}), disabled=not my_turn, height=60))
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
