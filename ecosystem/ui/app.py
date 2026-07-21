"""Tkinter application shell and settings interface."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from ..constants import (
    EMPTY_COLOR,
    GRASS_COLOR,
    HERBIVORE_COLOR,
    MUTED_COLOR,
    PANEL_COLOR,
    PREDATOR_COLOR,
    RENDER_MS,
    TEXT_COLOR,
    TICK_MS,
)
from ..settings import SETTING_KEYS, SETTING_RULES, GameSettings, SettingsStore
from ..simulation import Simulation
from .renderer import CanvasRenderer

CARD_COLOR = "#1d2d24"
CARD_BORDER_COLOR = "#395842"
CARD_SUBTLE_COLOR = "#294233"
BUTTON_TEXT_COLOR = "#102117"
SLIDER_TROUGH_COLOR = "#5b9664"
SLIDER_ACCENT_COLOR = "#ddff82"
SETTINGS_FRAME_CLEANUP_DELAY_MS = 200
GRASS_METER_BACKGROUND = "#0d1510"
GRASS_METER_BORDER = "#71917a"
DEFAULT_WINDOW_WIDTH = 1120
DEFAULT_WINDOW_HEIGHT = 780
MIN_WINDOW_WIDTH = 980
MIN_WINDOW_HEIGHT = 720
GAME_CONTENT_PADDING = 12
GAME_STATS_PANEL_WIDTH = 250
GAME_STATS_PANEL_GAP = 12
GAME_MAX_CANVAS_HEIGHT = 680
GAME_VERTICAL_LAYOUT_RESERVE = 64
CANVAS_BORDER_WIDTH = 2
MIN_CELL_SIZE = 5
MAX_CELL_SIZE = 24

SLIDER_SECTIONS = (
    (
        "СРЕДА",
        "Размер поля и восстановление травы",
        (
            ("columns", "Ширина поля, клеток"),
            ("rows", "Высота поля, клеток"),
            ("grass_regrowth", "Восстановление травы, секунд"),
        ),
    ),
    (
        "ТРАВОЯДНЫЕ",
        "Ищут траву, едят и размножаются",
        (
            ("herbivores", "Количество на старте"),
            ("herbivore_reproduction", "Коэффициент размножения"),
            ("herbivore_starvation", "Голод, секунд до смерти"),
            ("herbivore_speed", "Скорость передвижения"),
        ),
    ),
    (
        "ХИЩНИКИ",
        "Охотятся на травоядных и выживают без добычи",
        (
            ("predators", "Количество на старте"),
            ("predator_reproduction", "Коэффициент размножения"),
            ("predator_starvation", "Голод, секунд до смерти"),
            ("predator_speed", "Скорость передвижения"),
        ),
    ),
)


class EcosystemApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Пиксельная экосистема")
        self.root.configure(bg=PANEL_COLOR)
        self.root.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")
        self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.store = SettingsStore()
        self.settings = self.store.load()
        self.simulation: Optional[Simulation] = None
        self.renderer: Optional[CanvasRenderer] = None
        self.settings_frame: Optional[tk.Frame] = None
        self.game_frame: Optional[tk.Frame] = None
        self.after_id: Optional[str] = None
        self.render_after_id: Optional[str] = None
        self.last_tick = time.perf_counter()
        self.paused = False
        self.game_speed = 1.0
        self.speed_button: Optional[tk.Button] = None
        self.start_button: Optional[tk.Button] = None
        self.grass_meter: Optional[tk.Canvas] = None
        self.grass_meter_fill: Optional[int] = None
        self.grass_meter_border: Optional[int] = None
        self.grass_coverage = 0.0
        self.setting_vars: dict[str, tk.Variable] = {}
        self.setting_value_vars: dict[str, tk.StringVar] = {}
        self._updating_settings = False

        self.state_var = tk.StringVar()
        self.game_speed_var = tk.StringVar()
        self.time_var = tk.StringVar()
        self.herbivore_count_var = tk.StringVar()
        self.predator_count_var = tk.StringVar()
        self.settings_summary_var = tk.StringVar()
        self.settings_hint_var = tk.StringVar()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.store.save(self.settings)
        self.show_settings()

    def _on_close(self) -> None:
        self._cancel_game_callbacks()
        if self._has_settings_form():
            self.settings = self._settings_from_vars()
        self.store.save(self.settings)
        self.root.destroy()

    def _cancel_game_callbacks(self) -> None:
        for attribute in ("after_id", "render_after_id"):
            callback_id = getattr(self, attribute, None)
            if callback_id is not None:
                self.root.after_cancel(callback_id)
                setattr(self, attribute, None)

    def _detach_game_frame(self) -> Optional[tk.Frame]:
        old_frame = self.game_frame
        self.game_frame = None
        if old_frame is not None:
            old_frame.pack_forget()
        return old_frame

    def _destroy_after_settings_paint(self, frame: Optional[tk.Frame]) -> None:
        if frame is None:
            return

        def schedule_destroy() -> None:
            self.root.after(SETTINGS_FRAME_CLEANUP_DELAY_MS, frame.destroy)

        self.root.after_idle(schedule_destroy)

    def _detach_settings_frame(self) -> None:
        old_frame = self.settings_frame
        self.settings_frame = None
        if old_frame is not None:
            old_frame.destroy()

    def _has_settings_form(self) -> bool:
        return all(key in self.setting_vars for key in SETTING_KEYS)

    def _settings_from_vars(self) -> GameSettings:
        return GameSettings(**{key: self.setting_vars[key].get() for key in SETTING_KEYS})

    def _settings_changed(self, *_args: str) -> None:
        if self._updating_settings or not self._has_settings_form():
            return
        self.settings = self._settings_from_vars()
        self.store.save(self.settings)
        self._update_settings_feedback()

    def _update_settings_feedback(self) -> None:
        settings = self.settings
        total_animals = settings.herbivores + settings.predators
        self.settings_summary_var.set(
            f"Поле {settings.columns} × {settings.rows} · на старте {total_animals} животных"
        )
        has_animals = total_animals > 0
        self.settings_hint_var.set(
            "Сохраняется автоматически · стрелки — точная настройка"
            if has_animals
            else "Добавьте хотя бы одно животное, чтобы начать симуляцию"
        )
        if self.start_button is not None:
            self.start_button.configure(state="normal" if has_animals else "disabled")

    def _reset_settings(self) -> None:
        defaults = GameSettings()
        self._updating_settings = True
        try:
            for key in SETTING_KEYS:
                self.setting_vars[key].set(getattr(defaults, key))
        finally:
            self._updating_settings = False
        self._settings_changed()

    def show_settings(self) -> None:
        self._cancel_game_callbacks()
        self._detach_settings_frame()
        old_game_frame = self._detach_game_frame()
        self.renderer = None
        self.simulation = None
        self.grass_meter = None
        self.grass_meter_fill = None
        self.grass_meter_border = None
        self.grass_coverage = 0.0
        self.setting_vars = {}
        self.setting_value_vars = {}
        self.start_button = None

        frame = tk.Frame(self.root, bg=PANEL_COLOR, padx=36, pady=30)
        frame.pack(fill="both", expand=True)
        self.settings_frame = frame
        header = tk.Frame(frame, bg=PANEL_COLOR)
        header.pack(fill="x", pady=(0, 20))
        tk.Label(
            header,
            text="СИМУЛЯТОР ЭКОСИСТЕМЫ",
            bg=PANEL_COLOR,
            fg=GRASS_COLOR,
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Собери свою пищевую цепочку",
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
            font=("TkDefaultFont", 22, "bold"),
        ).pack(anchor="w", pady=(3, 4))
        tk.Label(
            header,
            text="Выберите параметры мира — их можно изменить перед следующим запуском.",
            bg=PANEL_COLOR,
            fg=MUTED_COLOR,
        ).pack(anchor="w")

        form = tk.Frame(frame, bg=PANEL_COLOR)
        form.pack(fill="both", expand=True)
        for column, (title, subtitle, specs) in enumerate(SLIDER_SECTIONS):
            form.grid_columnconfigure(column, weight=1, uniform="settings-card")
            section = tk.Frame(
                form,
                bg=CARD_COLOR,
                padx=18,
                pady=16,
                highlightthickness=1,
                highlightbackground=CARD_BORDER_COLOR,
            )
            section.grid(row=0, column=column, sticky="nsew", padx=6)
            tk.Label(
                section,
                text=title,
                bg=CARD_COLOR,
                fg=GRASS_COLOR,
                font=("TkDefaultFont", 10, "bold"),
            ).pack(anchor="w")
            tk.Label(
                section,
                text=subtitle,
                bg=CARD_COLOR,
                fg=MUTED_COLOR,
                anchor="w",
                justify="left",
                wraplength=260,
            ).pack(anchor="w", pady=(3, 10))
            for spec in specs:
                self._add_slider(section, *spec)

        launch_panel = tk.Frame(
            frame,
            bg=CARD_COLOR,
            padx=20,
            pady=16,
            highlightthickness=1,
            highlightbackground=CARD_BORDER_COLOR,
        )
        launch_panel.pack(fill="x", pady=(20, 0))
        launch_copy = tk.Frame(launch_panel, bg=CARD_COLOR)
        launch_copy.pack(side="left", fill="x", expand=True)
        tk.Label(
            launch_copy,
            textvariable=self.settings_summary_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            launch_copy,
            textvariable=self.settings_hint_var,
            bg=CARD_COLOR,
            fg=MUTED_COLOR,
        ).pack(anchor="w", pady=(3, 0))
        tk.Button(
            launch_panel,
            text="Сбросить",
            command=self._reset_settings,
            bg=CARD_SUBTLE_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_BORDER_COLOR,
            activeforeground=TEXT_COLOR,
            relief="flat",
            padx=14,
            pady=9,
        ).pack(side="right", padx=(12, 0))
        self.start_button = tk.Button(
            launch_panel,
            text="▶  НАЧАТЬ СИМУЛЯЦИЮ",
            command=self._start_from_form,
            bg=GRASS_COLOR,
            fg=BUTTON_TEXT_COLOR,
            activebackground="#77d66b",
            activeforeground=BUTTON_TEXT_COLOR,
            disabledforeground="#6e8574",
            relief="flat",
            padx=20,
            pady=10,
            font=("TkDefaultFont", 11, "bold"),
        )
        self.start_button.pack(side="right")
        self.root.bind("<Return>", lambda _event: self._start_from_form())
        self._settings_changed()
        # A game board or history graph can own a substantial canvas. Delay
        # its destruction until the new form completed its first layout pass.
        self._destroy_after_settings_paint(old_game_frame)

    def _add_slider(
        self,
        parent: tk.Frame,
        key: str,
        label: str,
    ) -> None:
        rule = SETTING_RULES[key]
        low, high, resolution, integer = rule.minimum, rule.maximum, rule.step, rule.integer
        value = getattr(self.settings, key)
        variable: tk.Variable = (
            tk.IntVar(value=int(value)) if integer else tk.DoubleVar(value=float(value))
        )
        self.setting_vars[key] = variable
        value_var = tk.StringVar(value=self._format_setting_value(value, integer))
        self.setting_value_vars[key] = value_var
        slot = tk.Frame(parent, bg=CARD_COLOR)
        slot.pack(fill="x", pady=(8, 12))
        label_row = tk.Frame(slot, bg=CARD_COLOR)
        label_row.pack(fill="x", pady=(0, 3))
        tk.Label(
            label_row,
            text=label,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            label_row,
            textvariable=value_var,
            bg=SLIDER_ACCENT_COLOR,
            fg=BUTTON_TEXT_COLOR,
            padx=8,
            pady=2,
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="right")
        scale = tk.Scale(
            slot,
            from_=low,
            to=high,
            resolution=resolution,
            orient="horizontal",
            variable=variable,
            length=235,
            showvalue=False,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            troughcolor=SLIDER_TROUGH_COLOR,
            activebackground=SLIDER_ACCENT_COLOR,
            highlightthickness=1,
            highlightbackground=CARD_COLOR,
            highlightcolor=SLIDER_ACCENT_COLOR,
            takefocus=True,
            bd=1,
            sliderrelief="raised",
        )
        scale.pack(fill="x")
        range_row = tk.Frame(slot, bg=CARD_COLOR)
        range_row.pack(fill="x")
        low_text = self._format_setting_value(low, integer)
        high_text = self._format_setting_value(high, integer)
        tk.Label(range_row, text=f"мин. {low_text}", bg=CARD_COLOR, fg=MUTED_COLOR).pack(
            side="left"
        )
        tk.Label(range_row, text=f"макс. {high_text}", bg=CARD_COLOR, fg=MUTED_COLOR).pack(
            side="right"
        )

        def sync_value(*_args: str) -> None:
            value_var.set(self._format_setting_value(variable.get(), integer))
            self._settings_changed()

        variable.trace_add("write", sync_value)

        def move_with_key(direction: int) -> str:
            scale.focus_set()
            current = float(variable.get())
            new_value = min(high, max(low, current + direction * resolution))
            variable.set(int(new_value) if integer else round(new_value, 1))
            return "break"

        scale.bind("<Button-1>", lambda _event: scale.focus_set(), add="+")
        scale.bind("<Left>", lambda _event: move_with_key(-1))
        scale.bind("<Down>", lambda _event: move_with_key(-1))
        scale.bind("<Right>", lambda _event: move_with_key(1))
        scale.bind("<Up>", lambda _event: move_with_key(1))

    @staticmethod
    def _format_setting_value(value: int | float, integer: bool) -> str:
        return str(int(value)) if integer else f"{float(value):g}"

    def _start_from_form(self) -> None:
        settings = self._settings_from_vars()
        if settings.herbivores == 0 and settings.predators == 0:
            messagebox.showerror("Пустой старт", "Добавь хотя бы одно животное.")
            return
        self.start_game(settings)

    def start_game(self, settings: GameSettings) -> None:
        self._detach_settings_frame()
        self.root.unbind("<Return>")
        self.settings = settings
        self.store.save(settings)
        self.simulation = Simulation(settings)
        self.paused = False
        self.game_speed = 1.0

        frame = tk.Frame(self.root, bg=PANEL_COLOR)
        frame.pack(fill="both", expand=True)
        self.game_frame = frame
        self._build_game_ui(frame)
        self.last_tick = time.perf_counter()
        self._tick()
        if not self.simulation.finished:
            self._render_tick()

    def _build_game_ui(self, frame: tk.Frame) -> None:
        assert self.simulation is not None
        window_width = self.root.winfo_width()
        if window_width <= 1:
            window_width = DEFAULT_WINDOW_WIDTH
        window_height = self.root.winfo_height()
        if window_height <= 1:
            window_height = DEFAULT_WINDOW_HEIGHT
        cell_size = self._cell_size_for_viewport(
            self.simulation.columns, self.simulation.rows, window_width, window_height
        )
        top = tk.Frame(frame, bg=PANEL_COLOR, padx=GAME_CONTENT_PADDING, pady=8)
        top.pack(fill="x")
        tk.Label(
            top,
            text="ПИКСЕЛЬНАЯ ЭКОСИСТЕМА",
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
            font=("TkFixedFont", 11, "bold"),
        ).pack(side="left", fill="x", expand=True)
        self.speed_button = self._toolbar_button(
            top, "▶ ×2", self._toggle_game_speed, "#b9dff0", "#102117"
        )
        self.speed_button.pack(side="right", padx=(6, 0))
        self._toolbar_button(top, "Завершить", self._force_finish, "#f3b6ae", "#331211").pack(
            side="right", padx=(6, 0)
        )
        self._toolbar_button(top, "Пауза", self._toggle_pause, "#b7e3b0", "#102117").pack(
            side="right", padx=(6, 0)
        )
        self._toolbar_button(top, "Новые настройки", self.show_settings, "#b7e3b0", "#102117").pack(
            side="right"
        )

        content = tk.Frame(frame, bg=PANEL_COLOR)
        content.pack(fill="both", expand=True, padx=GAME_CONTENT_PADDING, pady=(0, 8))
        self._build_stats_panel(content)

        board_area = tk.Frame(content, bg="#0d1510")
        board_area.pack(side="left", fill="both", expand=True)
        holder = tk.Frame(board_area, bg="#0d1510")
        holder.pack(expand=True)
        canvas = tk.Canvas(
            holder,
            width=self.simulation.columns * cell_size,
            height=self.simulation.rows * cell_size,
            bg=EMPTY_COLOR,
            highlightthickness=CANVAS_BORDER_WIDTH,
            highlightbackground="#4f7657",
        )
        canvas.pack()
        self.renderer = CanvasRenderer(canvas, self.simulation, cell_size)
        tk.Label(
            board_area,
            text="Зелёный — трава    Голубой — травоядное    Красный — хищник",
            bg=PANEL_COLOR,
            fg=MUTED_COLOR,
            pady=6,
        ).pack()

    @staticmethod
    def _cell_size_for_viewport(
        columns: int, rows: int, window_width: int, window_height: int
    ) -> int:
        available_width = max(
            MIN_CELL_SIZE,
            window_width
            - 2 * GAME_CONTENT_PADDING
            - GAME_STATS_PANEL_WIDTH
            - GAME_STATS_PANEL_GAP
            - 2 * CANVAS_BORDER_WIDTH,
        )
        available_height = max(MIN_CELL_SIZE, window_height - GAME_VERTICAL_LAYOUT_RESERVE)
        return max(
            MIN_CELL_SIZE,
            min(
                MAX_CELL_SIZE,
                available_width // columns,
                GAME_MAX_CANVAS_HEIGHT // rows,
                available_height // rows,
            ),
        )

    @staticmethod
    def _toolbar_button(
        parent: tk.Frame, text: str, command, background: str, foreground: str
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=background,
            activeforeground=foreground,
            relief="flat",
            padx=12,
        )

    def _build_stats_panel(self, parent: tk.Frame) -> None:
        panel = tk.Frame(parent, bg=PANEL_COLOR, width=GAME_STATS_PANEL_WIDTH)
        panel.pack(side="left", fill="y", padx=(0, GAME_STATS_PANEL_GAP))
        panel.pack_propagate(False)

        def group(title: str) -> tk.LabelFrame:
            box = tk.LabelFrame(
                panel,
                text=title,
                bg=PANEL_COLOR,
                fg=GRASS_COLOR,
                padx=10,
                pady=8,
                font=("TkFixedFont", 10, "bold"),
            )
            box.pack(fill="x", pady=(0, 12))
            return box

        state = group("СОСТОЯНИЕ ИГРЫ")
        tk.Label(
            state, textvariable=self.state_var, width=24, anchor="w", bg=PANEL_COLOR, fg=TEXT_COLOR
        ).pack()
        timing = group("СКОРОСТЬ + ВРЕМЯ")
        tk.Label(
            timing,
            textvariable=self.game_speed_var,
            width=24,
            anchor="w",
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
        ).pack()
        tk.Label(
            timing, textvariable=self.time_var, width=24, anchor="w", bg=PANEL_COLOR, fg=TEXT_COLOR
        ).pack()
        counts = group("СЧЁТЧИКИ")
        tk.Label(
            counts,
            textvariable=self.herbivore_count_var,
            width=24,
            anchor="w",
            bg=PANEL_COLOR,
            fg=HERBIVORE_COLOR,
        ).pack()
        tk.Label(
            counts,
            textvariable=self.predator_count_var,
            width=24,
            anchor="w",
            bg=PANEL_COLOR,
            fg=PREDATOR_COLOR,
        ).pack()
        tk.Label(counts, text="Трава", anchor="w", bg=PANEL_COLOR, fg=GRASS_COLOR).pack(
            fill="x", pady=(6, 3)
        )
        self.grass_meter = tk.Canvas(
            counts,
            height=16,
            bg=GRASS_METER_BACKGROUND,
            highlightthickness=0,
            bd=0,
            takefocus=False,
        )
        self.grass_meter_fill = self.grass_meter.create_rectangle(
            0, 0, 0, 0, fill=GRASS_COLOR, outline=""
        )
        self.grass_meter_border = self.grass_meter.create_rectangle(
            0, 0, 0, 0, outline=GRASS_METER_BORDER
        )
        self.grass_meter.pack(fill="x")
        self.grass_meter.bind("<Configure>", lambda _event: self._render_grass_meter())
        self._render_grass_meter()

    def _update_status(self) -> None:
        assert self.simulation is not None
        herbivores, predators, grass = self.simulation.counts()
        self.state_var.set("ПАУЗА" if self.paused else "ИГРА")
        self.game_speed_var.set(f"Скорость: ×{int(self.game_speed)}")
        self.time_var.set(f"Время: {self.simulation.elapsed:06.1f} с")
        self.herbivore_count_var.set(f"Травоядные: {herbivores:4d}")
        self.predator_count_var.set(f"Хищники:   {predators:4d}")
        self.grass_coverage = self._grass_coverage(
            grass, self.simulation.columns, self.simulation.rows
        )
        self._render_grass_meter()

    @staticmethod
    def _grass_coverage(ready_grass: int, columns: int, rows: int) -> float:
        maximum = max(1, columns * rows)
        return min(1.0, max(0.0, ready_grass / maximum))

    def _render_grass_meter(self) -> None:
        if (
            self.grass_meter is None
            or self.grass_meter_fill is None
            or self.grass_meter_border is None
        ):
            return
        width = max(1, self.grass_meter.winfo_width())
        height = max(1, self.grass_meter.winfo_height())
        inner_width = max(0, width - 2)
        fill_width = round(inner_width * self.grass_coverage)
        self.grass_meter.coords(
            self.grass_meter_fill,
            1,
            1,
            1 + fill_width,
            max(1, height - 1),
        )
        self.grass_meter.itemconfigure(
            self.grass_meter_fill, state="normal" if fill_width else "hidden"
        )
        self.grass_meter.coords(self.grass_meter_border, 0, 0, width - 1, height - 1)

    def _toggle_pause(self) -> None:
        self.paused = not self.paused
        self.last_tick = time.perf_counter()

    def _toggle_game_speed(self) -> None:
        self.game_speed = 2.0 if self.game_speed == 1.0 else 1.0
        if self.speed_button is not None:
            self.speed_button.configure(text="▶ ×1" if self.game_speed == 2.0 else "▶ ×2")

    def _force_finish(self) -> None:
        if self.simulation is None or self.simulation.finished:
            return
        self.simulation.finish()
        self._cancel_game_callbacks()
        self._show_game_over()

    def _tick(self) -> None:
        self.after_id = None
        if self.simulation is None:
            return
        now = time.perf_counter()
        dt = min(0.1, max(0.0, now - self.last_tick)) * self.game_speed
        self.last_tick = now
        if not self.paused:
            self.simulation.step(dt)
        if self.simulation.finished:
            self._cancel_game_callbacks()
            self._show_game_over()
            return
        self.after_id = self.root.after(TICK_MS, self._tick)

    def _render_tick(self) -> None:
        self.render_after_id = None
        if self.simulation is None or self.simulation.finished:
            return
        if not self.paused and self.renderer is not None:
            self.renderer.draw()
        self._update_status()
        self.render_after_id = self.root.after(RENDER_MS, self._render_tick)

    def _show_game_over(self) -> None:
        self._cancel_game_callbacks()
        old_game_frame = self._detach_game_frame()
        if old_game_frame is not None:
            old_game_frame.destroy()
        self.renderer = None
        self.speed_button = None
        assert self.simulation is not None

        frame = tk.Frame(self.root, bg=PANEL_COLOR, padx=24, pady=20)
        frame.pack(fill="both", expand=True)
        self.game_frame = frame
        tk.Label(
            frame,
            text="ИГРА ОКОНЧЕНА",
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
            font=("TkFixedFont", 19, "bold"),
        ).pack(pady=(4, 4))
        tk.Label(frame, text=self.simulation.finish_reason, bg=PANEL_COLOR, fg=MUTED_COLOR).pack(
            pady=(0, 10)
        )
        graph = tk.Canvas(frame, bg="#101a14", highlightthickness=1, highlightbackground="#4f7657")
        graph.pack(fill="both", expand=True, padx=8, pady=4)
        graph.bind(
            "<Configure>", lambda event: self._draw_history_graph(graph, event.width, event.height)
        )
        self._draw_history_graph(graph, 760, 420)
        tk.Button(
            frame,
            text="Новые настройки",
            command=self.show_settings,
            bg=GRASS_COLOR,
            fg="#102117",
            activebackground="#77d66b",
            relief="flat",
            padx=16,
            pady=7,
        ).pack(pady=(10, 0))

    def _draw_history_graph(self, graph: tk.Canvas, width: int, height: int) -> None:
        if self.simulation is None:
            return
        graph.delete("all")
        width, height = max(1, width), max(1, height)
        history = self.simulation.history
        left, top, right, bottom = 68, 28, 24, 54
        plot_width, plot_height = max(1, width - left - right), max(1, height - top - bottom)
        max_time = max(1.0, history[-1][0])
        max_count = max(1, max(max(point[1], point[2]) for point in history))
        graph.create_text(
            width // 2,
            12,
            text="Численность животных во времени",
            fill=TEXT_COLOR,
            font=("TkDefaultFont", 11, "bold"),
        )
        for index in range(6):
            fraction = index / 5
            y = bottom + top + plot_height * (1 - fraction)
            graph.create_line(left, y, width - right, y, fill="#294233")
            graph.create_text(
                left - 10, y, text=str(round(max_count * fraction)), fill=MUTED_COLOR, anchor="e"
            )
        axis_bottom = top + plot_height
        graph.create_line(left, top, left, axis_bottom, fill="#71917a", width=2)
        graph.create_line(left, axis_bottom, width - right, axis_bottom, fill="#71917a", width=2)
        graph.create_text(left, axis_bottom + 22, text="0 с", fill=MUTED_COLOR, anchor="w")
        graph.create_text(
            width - right, axis_bottom + 22, text=f"{max_time:.1f} с", fill=MUTED_COLOR, anchor="e"
        )

        def point(index: int, count: int) -> tuple[float, float]:
            elapsed = history[index][0]
            return (
                left + elapsed / max_time * plot_width,
                top + plot_height - count / max_count * plot_height,
            )

        herbivore_points: list[float] = []
        predator_points: list[float] = []
        for index, (_, herbivores, predators) in enumerate(history):
            herbivore_points.extend(point(index, herbivores))
            predator_points.extend(point(index, predators))
        if len(herbivore_points) == 2:
            herbivore_points *= 2
            predator_points *= 2
        graph.create_line(*herbivore_points, fill=HERBIVORE_COLOR, width=3, smooth=True)
        graph.create_line(*predator_points, fill=PREDATOR_COLOR, width=3, smooth=True)
        legend_y = height - 18
        graph.create_rectangle(
            left, legend_y - 5, left + 12, legend_y + 7, fill=HERBIVORE_COLOR, outline=""
        )
        graph.create_text(left + 20, legend_y + 1, text="Травоядные", fill=TEXT_COLOR, anchor="w")
        graph.create_rectangle(
            left + 150, legend_y - 5, left + 162, legend_y + 7, fill=PREDATOR_COLOR, outline=""
        )
        graph.create_text(left + 170, legend_y + 1, text="Хищники", fill=TEXT_COLOR, anchor="w")
