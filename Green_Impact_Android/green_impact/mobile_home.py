from __future__ import annotations

from pathlib import Path
from typing import Callable

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

DARK_GREEN = (0.035, 0.27, 0.12, 1)
MID_GREEN = (0.17, 0.42, 0.12, 1)
LIGHT_GREEN = (0.72, 0.86, 0.45, 1)
CREAM = (0.985, 0.97, 0.91, 1)
FIELD = (1.0, 0.99, 0.96, 1)
GOLD = (0.76, 0.67, 0.42, 1)
TEXT = (0.15, 0.18, 0.13, 1)
WHITE = (1, 1, 1, 1)
ERROR = (0.78, 0.13, 0.13, 1)


class RoundedPanel(FloatLayout):
    def __init__(self, background=CREAM, border=GOLD, radius=24, **kwargs):
        super().__init__(**kwargs)
        self._radius = dp(radius)
        with self.canvas.before:
            self._bg_color = Color(*background)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            self._bd_color = Color(*border)
            self._bd = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self._radius), width=1.25)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._bd.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)


class RoundedRow(BoxLayout):
    def __init__(self, background=FIELD, border=(0.84, 0.82, 0.72, 1), radius=16, **kwargs):
        super().__init__(**kwargs)
        self._radius = dp(radius)
        with self.canvas.before:
            self._bg_color = Color(*background)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            self._bd_color = Color(*border)
            self._bd = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self._radius), width=1.05)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._bd.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)


class HudButton(Button):
    def __init__(self, *, fill=DARK_GREEN, pressed=(0.02, 0.20, 0.08, 1), border=DARK_GREEN, foreground=WHITE, radius=16, **kwargs):
        super().__init__(background_normal="", background_down="", background_color=(0, 0, 0, 0), color=foreground, bold=True, **kwargs)
        self._fill_normal = fill
        self._fill_pressed = pressed
        self._radius = dp(radius)
        with self.canvas.before:
            self._fill_color = Color(*fill)
            self._fill = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            self._border_color = Color(*border)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self._radius), width=1.35)
        self.bind(pos=self._sync_canvas, size=self._sync_canvas, state=self._sync_state)
        self.bind(width=self._sync_text, height=self._sync_text)

    def _sync_canvas(self, *_):
        self._fill.pos = self.pos
        self._fill.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)

    def _sync_state(self, *_):
        self._fill_color.rgba = self._fill_pressed if self.state == "down" else self._fill_normal

    def _sync_text(self, *_):
        self.text_size = (max(dp(40), self.width - dp(16)), max(dp(24), self.height - dp(10)))
        self.halign = "center"
        self.valign = "middle"


class VectorIcon(Widget):
    def __init__(self, kind: str, color=DARK_GREEN, **kwargs):
        super().__init__(**kwargs)
        self.kind = kind
        self.icon_color = color
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *_):
        self.canvas.clear()
        cx, cy = self.center
        unit = min(self.width, self.height)
        with self.canvas:
            Color(*self.icon_color)
            if self.kind == "person":
                r = unit * 0.14
                Ellipse(pos=(cx - r, cy + unit * 0.08), size=(2 * r, 2 * r))
                RoundedRectangle(pos=(cx - unit * 0.22, cy - unit * 0.28), size=(unit * 0.44, unit * 0.26), radius=[unit * 0.08])
            elif self.kind == "hash":
                off = unit * 0.13
                length = unit * 0.58
                for xoff in (-off, off):
                    Line(points=[cx + xoff - unit * 0.04, cy - length / 2, cx + xoff + unit * 0.04, cy + length / 2], width=dp(2.4))
                for yoff in (-off, off):
                    Line(points=[cx - length / 2, cy + yoff - unit * 0.04, cx + length / 2, cy + yoff + unit * 0.04], width=dp(2.4))
            elif self.kind == "check":
                Line(points=[cx - unit * 0.24, cy, cx - unit * 0.05, cy - unit * 0.18, cx + unit * 0.28, cy + unit * 0.20], width=dp(3.0), joint="round", cap="round")
            elif self.kind == "gear":
                import math
                outer = unit * 0.22
                inner = outer * 0.38
                tooth_start = outer * 1.06
                tooth_end = outer * 1.42
                Line(circle=(cx, cy, outer), width=dp(2.2))
                Line(circle=(cx, cy, inner), width=dp(2.0))
                for index in range(8):
                    angle = math.radians(index * 45)
                    Line(points=[
                        cx + math.cos(angle) * tooth_start,
                        cy + math.sin(angle) * tooth_start,
                        cx + math.cos(angle) * tooth_end,
                        cy + math.sin(angle) * tooth_end,
                    ], width=dp(2.4), cap="round")


class GearButton(Button):
    """Botão de configuração com ícone PNG para renderização estável no Android."""

    def __init__(self, callback: Callable[[], None], **kwargs):
        super().__init__(
            text="",
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            **kwargs,
        )
        self._radius = dp(14)
        self._normal_fill = (0.96, 0.96, 0.88, 0.97)

        with self.canvas.before:
            self._fill_color = Color(*self._normal_fill)
            self._fill = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[self._radius],
            )
            self._border_color = Color(0.72, 0.75, 0.60, 1)
            self._border = Line(
                rounded_rectangle=(
                    self.x,
                    self.y,
                    self.width,
                    self.height,
                    self._radius,
                ),
                width=1.35,
            )

        icon_path = Path(__file__).resolve().parents[1] / "assets" / "gear_icon.png"
        self.icon = Image(
            source=str(icon_path),
            size_hint=(None, None),
            size=(dp(28), dp(28)),
            allow_stretch=True,
            keep_ratio=True,
        )
        self.add_widget(self.icon)

        self.bind(pos=self._sync_graphics, size=self._sync_graphics)
        self.bind(state=self._sync_state)
        self.bind(on_release=lambda *_: callback())
        self._sync_graphics()

    def _sync_state(self, *_):
        self._fill_color.rgba = LIGHT_GREEN if self.state == "down" else self._normal_fill

    def _sync_graphics(self, *_):
        self._fill.pos = self.pos
        self._fill.size = self.size
        self._border.rounded_rectangle = (
            self.x,
            self.y,
            self.width,
            self.height,
            self._radius,
        )
        self.icon.pos = (
            self.center_x - self.icon.width / 2,
            self.center_y - self.icon.height / 2,
        )


class StatusBadge(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._circle_color = Color(*MID_GREEN)
            self._circle = Ellipse(pos=self.pos, size=self.size)

        self.icon = VectorIcon(
            "check",
            color=WHITE,
            size_hint=(None, None),
            size=(dp(24), dp(24)),
        )
        self.add_widget(self.icon)

        self.bind(pos=self._sync_contents, size=self._sync_contents)
        self._sync_contents()

    def _sync_contents(self, *_):
        diameter = min(self.width, self.height)
        circle_x = self.center_x - diameter / 2
        circle_y = self.center_y - diameter / 2
        self._circle.size = (diameter, diameter)
        self._circle.pos = (circle_x, circle_y)
        self.icon.pos = (
            self.center_x - self.icon.width / 2,
            self.center_y - self.icon.height / 2,
        )
        self.icon.redraw()


class FieldCard(RoundedRow):
    def __init__(self, title: str, icon_kind: str, value: str = "", hint: str = "", **kwargs):
        super().__init__(orientation="horizontal", padding=[dp(12), dp(8)], spacing=dp(10), **kwargs)
        icon_box = BoxLayout(size_hint=(None, 1), width=dp(34), padding=[0, dp(8), 0, dp(8)])
        icon_box.add_widget(VectorIcon(icon_kind, size_hint=(None, None), size=(dp(28), dp(28))))
        self.add_widget(icon_box)

        text_col = BoxLayout(orientation="vertical", spacing=dp(2))
        title_label = Label(text=title, color=DARK_GREEN, bold=True, font_size=dp(13), size_hint_y=0.42, halign="left", valign="middle")
        title_label.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        self.input = TextInput(text=value, hint_text=hint, multiline=False, background_normal="", background_active="", background_color=(0, 0, 0, 0), foreground_color=TEXT, hint_text_color=(0.48, 0.48, 0.43, 1), cursor_color=DARK_GREEN, font_size=dp(14), padding=[0, dp(4), 0, 0], size_hint_y=0.58)
        text_col.add_widget(title_label)
        text_col.add_widget(self.input)
        self.add_widget(text_col)


class ServerCard(RoundedPanel):
    """Cartão com ícones fixados por coordenadas relativas ao próprio cartão."""

    def __init__(self, on_settings: Callable[[], None], **kwargs):
        self.on_settings = on_settings
        super().__init__(
            background=FIELD,
            border=(0.84, 0.82, 0.72, 1),
            radius=16,
            **kwargs,
        )

        self.status_badge = StatusBadge(
            size_hint=(None, None),
            size=(dp(42), dp(42)),
        )
        self.add_widget(self.status_badge)

        self.title_label = Label(
            text="Selecionar servidor",
            color=DARK_GREEN,
            bold=True,
            font_size=dp(13),
            halign="left",
            valign="middle",
            size_hint=(None, None),
        )
        self.title_label.bind(
            size=lambda widget, *_: setattr(widget, "text_size", widget.size)
        )
        self.add_widget(self.title_label)

        self.address_label = Label(
            text="Toque para configurar",
            color=TEXT,
            font_size=dp(11),
            halign="left",
            valign="middle",
            size_hint=(None, None),
        )
        self.address_label.bind(
            size=lambda widget, *_: setattr(widget, "text_size", widget.size)
        )
        self.add_widget(self.address_label)

        self.settings_button = GearButton(
            on_settings,
            size_hint=(None, None),
            size=(dp(42), dp(42)),
        )
        self.add_widget(self.settings_button)

        self.bind(pos=self._layout_contents, size=self._layout_contents)
        self._layout_contents()

    def _layout_contents(self, *_):
        side_margin = dp(14)
        icon_size = dp(42)

        # ✓ e círculo: centro vertical, lado esquerdo.
        self.status_badge.pos = (
            self.x + side_margin,
            self.center_y - icon_size / 2,
        )

        # Engrenagem: centro vertical, lado direito.
        self.settings_button.pos = (
            self.right - side_margin - icon_size,
            self.center_y - icon_size / 2,
        )

        text_left = self.status_badge.right + dp(14)
        text_right = self.settings_button.x - dp(12)
        text_width = max(dp(80), text_right - text_left)

        self.title_label.pos = (text_left, self.center_y + dp(1))
        self.title_label.size = (text_width, dp(24))

        self.address_label.pos = (text_left, self.center_y - dp(24))
        self.address_label.size = (text_width, dp(22))

    def set_address(self, host: str, port: str):
        self.address_label.text = "Toque para configurar"

    def on_touch_up(self, touch):
        # O botão da direita continua recebendo o toque normalmente.
        if self.settings_button.collide_point(*touch.pos):
            return super().on_touch_up(touch)
        # Qualquer toque no restante do cartão também abre as configurações.
        if self.collide_point(*touch.pos) and not getattr(touch, "is_mouse_scrolling", False):
            self.on_settings()
            return True
        return super().on_touch_up(touch)


class MobileHomeHUD(FloatLayout):
    def __init__(self, *, asset_dir: Path, on_create: Callable[[], None], on_join: Callable[[], None], on_solo: Callable[[], None], on_local: Callable[[], None], on_online: Callable[[], None], on_settings: Callable[[], None], on_help: Callable[[], None], **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.10, 0.22, 0.08, 1)
            self._root_background = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(28)])
        self.bind(pos=self._sync_root, size=self._sync_root)

        root = BoxLayout(orientation="vertical", padding=[dp(14), dp(20), dp(14), dp(22)], spacing=dp(10), size_hint=(1, 1))
        self.add_widget(root)

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(70), spacing=dp(12))
        self.top_bar = top
        root.add_widget(top)

        logo_path = asset_dir / "logo_mobile.png"
        if not logo_path.exists():
            logo_path = asset_dir / "logo.png"
        logo_box = BoxLayout(size_hint_x=0.24)
        logo_box.add_widget(Image(source=str(logo_path), fit_mode="contain"))
        top.add_widget(logo_box)

        title_pill = RoundedPanel(size_hint_x=0.76, background=(0.24, 0.39, 0.18, 0.96), border=(0.65, 0.76, 0.48, 1), radius=20)
        title = Label(text="Green Impact", color=WHITE, bold=True, font_size=dp(20), halign="center", valign="middle", size_hint=(0.96, 0.96), pos_hint={"center_x": 0.5, "center_y": 0.5})
        title.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        title_pill.add_widget(title)
        top.add_widget(title_pill)

        board_frame = RoundedPanel(size_hint_y=0.31, background=(0.13, 0.24, 0.10, 1), border=(0.16, 0.34, 0.13, 1), radius=18)
        self.board_frame = board_frame
        board_path = asset_dir / "board_new_mobile.jpg"
        if not board_path.exists():
            board_path = asset_dir / "board_new.jpg"
        board_frame.add_widget(Image(source=str(board_path), fit_mode="contain", size_hint=(0.97, 0.97), pos_hint={"center_x": 0.5, "center_y": 0.5}))
        root.add_widget(board_frame)

        quick_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12), padding=[dp(8), 0, dp(8), 0])
        self.quick_row = quick_row
        help_button = HudButton(text="Como jogar", fill=(0.98, 0.97, 0.92, 0.96), pressed=LIGHT_GREEN, border=GOLD, foreground=DARK_GREEN, font_size=dp(13))
        help_button.bind(on_release=lambda *_: on_help())
        quick_row.add_widget(help_button)
        root.add_widget(quick_row)

        panel_host = FloatLayout(size_hint_y=0.57)
        self.panel_host = panel_host
        root.add_widget(panel_host)
        self.action_panel = RoundedPanel(size_hint=(0.96, 1), pos_hint={"center_x": 0.5, "y": 0}, background=CREAM, border=GOLD, radius=24)
        panel_host.add_widget(self.action_panel)

        self.content_scroll = ScrollView(size_hint=(0.98, 0.98), pos_hint={"center_x": 0.5, "center_y": 0.5}, do_scroll_x=False, bar_width=dp(4), scroll_type=['bars', 'content'])
        self.action_panel.add_widget(self.content_scroll)

        content = BoxLayout(orientation="vertical", padding=[dp(14), dp(16), dp(14), dp(20)], spacing=dp(10), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        self.content_scroll.add_widget(content)
        self.content_box = content

        self.name_field = FieldCard("Seu nome", "person", value="Jogador Verde", hint="Jogador Verde", size_hint_y=None, height=dp(70))
        self.room_field = FieldCard("Código da sala", "hash", value="", hint="Ex.: ABC123", size_hint_y=None, height=dp(70))
        self.name_input = self.name_field.input
        self.room_input = self.room_field.input
        self.name_input.bind(focus=self._ensure_visible)
        self.room_input.bind(focus=self._ensure_visible)
        content.add_widget(self.name_field)
        content.add_widget(self.room_field)

        primary_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(70))
        create_button = HudButton(text="Criar nova sala", fill=(0.31, 0.58, 0.07, 1), pressed=(0.23, 0.47, 0.05, 1), border=(0.25, 0.48, 0.07, 1), foreground=WHITE, font_size=dp(15))
        join_button = HudButton(text="Entrar com código", fill=DARK_GREEN, pressed=(0.02, 0.19, 0.08, 1), border=DARK_GREEN, foreground=WHITE, font_size=dp(15))
        create_button.bind(on_release=lambda *_: on_create())
        join_button.bind(on_release=lambda *_: on_join())
        primary_row.add_widget(create_button)
        primary_row.add_widget(join_button)
        content.add_widget(primary_row)

        mode_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(58))
        local_button = HudButton(text="Multijogador local", fill=(0.97, 0.96, 0.90, 1), pressed=LIGHT_GREEN, border=(0.78, 0.80, 0.66, 1), foreground=DARK_GREEN, font_size=dp(13))
        solo_mode_button = HudButton(text="Um jogador", fill=(0.90, 0.95, 0.76, 1), pressed=LIGHT_GREEN, border=MID_GREEN, foreground=DARK_GREEN, font_size=dp(13))
        local_button.bind(on_release=lambda *_: on_local())
        solo_mode_button.bind(on_release=lambda *_: on_solo())
        mode_row.add_widget(local_button)
        mode_row.add_widget(solo_mode_button)
        content.add_widget(mode_row)

        self.server_card = ServerCard(on_settings=on_settings, size_hint_y=None, height=dp(68))
        content.add_widget(self.server_card)

        self.error_label = Label(text="", color=ERROR, bold=True, font_size=dp(11), halign="center", valign="middle", size_hint_y=None, height=dp(22))
        self.error_label.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        content.add_widget(self.error_label)

    def _sync_root(self, *_):
        self._root_background.pos = self.pos
        self._root_background.size = self.size


    def _ensure_visible(self, widget, focused):
        if focused:
            self._set_typing_layout(True)
            Clock.schedule_once(lambda *_: self._scroll_to_widget(widget), 0.18)
        else:
            Clock.schedule_once(lambda *_: self._restore_after_focus(), 0.12)

    def _restore_after_focus(self):
        if not self.name_input.focus and not self.room_input.focus:
            self._set_typing_layout(False)

    def _set_typing_layout(self, typing: bool):
        if typing:
            self.top_bar.height = 0
            self.top_bar.opacity = 0
            self.board_frame.size_hint_y = 0
            self.board_frame.opacity = 0
            self.quick_row.height = 0
            self.quick_row.opacity = 0
            self.panel_host.size_hint_y = 1
        else:
            self.top_bar.height = dp(70)
            self.top_bar.opacity = 1
            self.board_frame.size_hint_y = 0.31
            self.board_frame.opacity = 1
            self.quick_row.height = dp(52)
            self.quick_row.opacity = 1
            self.panel_host.size_hint_y = 0.57

    def _scroll_to_widget(self, widget):
        if getattr(self, 'content_scroll', None) is not None:
            try:
                self.content_scroll.scroll_to(widget, padding=dp(24), animate=False)
            except Exception:
                pass

    def set_values(self, name: str, room: str, host: str, port: str, error: str = ""):
        self.name_input.text = name or "Jogador Verde"
        self.room_input.text = (room or "").upper()
        self.server_card.set_address(host, port)
        self.error_label.text = error or ""

    def values(self) -> tuple[str, str]:
        return self.name_input.text.strip(), self.room_input.text.strip().upper()
