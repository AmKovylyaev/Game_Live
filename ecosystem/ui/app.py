"""Tkinter application shell and settings interface."""

from __future__ import annotations

import time
import tkinter as tk
from typing import Optional

from tkinter import messagebox

from ..constants import (
    EMPTY_COLOR,
    GRASS_COLOR,
    HERBIVORE_COLOR,
    MUTED_COLOR,
    PANEL_COLOR,
    PREDATOR_COLOR,
    TEXT_COLOR,
    TICK_MS,
)
from ..settings import GameSettings, SettingsStore
from ..simulation import Simulation
from .renderer import CanvasRenderer


class EcosystemApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Пиксельная экосистема")
        self.root.configure(bg=PANEL_COLOR)
        self.root.minsize(1000, 720)
        self.store = SettingsStore()
        self.settings = self.store.load()
        self.simulation: Optional[Simulation] = None
        self.renderer: Optional[CanvasRenderer] = None
        self.canvas: Optional[tk.Canvas] = None
        self.settings_frame: Optional[tk.Frame] = None
        self.game_frame: Optional[tk.Frame] = None
        self.after_id: Optional[str] = None
        self.last_tick = time.perf_counter()
        self.paused = False
        self.game_speed = 1.0
        self.speed_button: Optional[tk.Button] = None
        self.setting_vars: dict[str, tk.Variable] = {}

        self.state_var = tk.StringVar()
        self.game_speed_var = tk.StringVar()
        self.time_var = tk.StringVar()
        self.herbivore_count_var = tk.StringVar()
        self.predator_count_var = tk.StringVar()
        self.grass_count_var = tk.StringVar()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.store.save(self.settings)
        self.show_settings()

    def _on_close(self) -> None:
        if len(self.setting_vars) == 11:
            self.settings = self._settings_from_vars()
        self.store.save(self.settings)
        self.root.destroy()

    def _detach_game_frame(self) -> None:
        old_frame = self.game_frame
        self.game_frame = None
        if old_frame is not None:
            old_frame.pack_forget()
            self.root.after_idle(old_frame.destroy)

    def _settings_from_vars(self) -> GameSettings:
        return GameSettings(
            columns=int(self.setting_vars["columns"].get()),
            rows=int(self.setting_vars["rows"].get()),
            herbivores=int(self.setting_vars["herbivores"].get()),
            predators=int(self.setting_vars["predators"].get()),
            grass_regrowth=float(self.setting_vars["grass_regrowth"].get()),
            herbivore_reproduction=float(self.setting_vars["herbivore_reproduction"].get()),
            predator_reproduction=float(self.setting_vars["predator_reproduction"].get()),
            herbivore_starvation=float(self.setting_vars["herbivore_starvation"].get()),
            predator_starvation=float(self.setting_vars["predator_starvation"].get()),
            herbivore_speed=float(self.setting_vars["herbivore_speed"].get()),
            predator_speed=float(self.setting_vars["predator_speed"].get()),
        )

    def _settings_changed(self, _value: str = "") -> None:
        if len(self.setting_vars) == 11:
            self.settings = self._settings_from_vars()
            self.store.save(self.settings)

    def show_settings(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self._detach_game_frame()
        self.canvas = None
        self.renderer = None
        self.simulation = None
        self.setting_vars = {}

        frame = tk.Frame(self.root, bg=PANEL_COLOR, padx=32, pady=28)
        frame.pack(fill="both", expand=True)
        self.settings_frame = frame
        tk.Label(frame, text="ПИКСЕЛЬНАЯ ЭКОСИСТЕМА", bg=PANEL_COLOR, fg=TEXT_COLOR, font=("TkFixedFont", 19, "bold")).pack(
            pady=(18, 6)
        )
        tk.Label(
            frame,
            text="Настрой поле и запусти маленькую пищевую цепочку",
            bg=PANEL_COLOR,
            fg=MUTED_COLOR,
        ).pack(pady=(0, 22))

        form = tk.Frame(frame, bg=PANEL_COLOR)
        form.pack()
        for column, (title, specs) in enumerate(self._slider_sections()):
            section = tk.Frame(form, bg=PANEL_COLOR, padx=12)
            section.grid(row=0, column=column, sticky="n")
            tk.Label(section, text=title, bg=PANEL_COLOR, fg=GRASS_COLOR, font=("TkFixedFont", 10, "bold")).pack(
                anchor="w", pady=(0, 5)
            )
            for spec in specs:
                self._add_slider(section, *spec)

        tk.Button(
            frame,
            text="▶  НАЧАТЬ ИГРУ",
            command=self._start_from_form,
            bg=GRASS_COLOR,
            fg="#102117",
            activebackground="#77d66b",
            activeforeground="#102117",
            relief="flat",
            padx=22,
            pady=10,
            font=("TkDefaultFont", 11, "bold"),
        ).pack(pady=(24, 10))
        tk.Label(
            frame,
            text="Настройки сохраняются автоматически • стрелки меняют выбранный ползунок",
            bg=PANEL_COLOR,
            fg=MUTED_COLOR,
        ).pack()
        self.root.bind("<Return>", lambda _event: self._start_from_form())

    @staticmethod
    def _slider_sections():
        return [
            ("ОБЩИЕ", [
                ("columns", "Ширина поля, клеток", 8, 100, 1, True),
                ("rows", "Высота поля, клеток", 8, 70, 1, True),
                ("grass_regrowth", "Восстановление травы, секунд", 3, 30, 1, False),
            ]),
            ("ТРАВОЯДНЫЕ", [
                ("herbivores", "Количество на старте", 0, 300, 1, True),
                ("herbivore_reproduction", "Коэффициент размножения", 0.1, 3, 0.1, False),
                ("herbivore_starvation", "Голод, секунд до смерти", 5, 15, 1, False),
                ("herbivore_speed", "Скорость передвижения", 0.5, 6, 0.1, False),
            ]),
            ("ХИЩНИКИ", [
                ("predators", "Количество на старте", 0, 150, 1, True),
                ("predator_reproduction", "Коэффициент размножения", 0.1, 3, 0.1, False),
                ("predator_starvation", "Голод, секунд до смерти", 5, 15, 1, False),
                ("predator_speed", "Скорость передвижения", 0.5, 8, 0.1, False),
            ]),
        ]

    def _add_slider(
        self,
        parent: tk.Frame,
        key: str,
        label: str,
        low: float,
        high: float,
        resolution: float,
        integer: bool,
    ) -> None:
        value = getattr(self.settings, key)
        variable: tk.Variable = tk.IntVar(value=int(value)) if integer else tk.DoubleVar(value=float(value))
        self.setting_vars[key] = variable
        slot = tk.Frame(parent, bg=PANEL_COLOR)
        slot.pack(fill="x", pady=(9, 15))
        tk.Label(slot, text=label, bg=PANEL_COLOR, fg=TEXT_COLOR, anchor="w").pack(anchor="w")
        scale = tk.Scale(
            slot,
            from_=low,
            to=high,
            resolution=resolution,
            orient="horizontal",
            variable=variable,
            length=245,
            showvalue=True,
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
            troughcolor="#304c38",
            activebackground=GRASS_COLOR,
            highlightthickness=1,
            highlightbackground=PANEL_COLOR,
            highlightcolor=GRASS_COLOR,
            takefocus=True,
            bd=0,
            command=self._settings_changed,
        )
        scale.pack(fill="x")
        range_row = tk.Frame(slot, bg=PANEL_COLOR)
        range_row.pack(fill="x")
        low_text = str(int(low)) if integer or float(low).is_integer() else f"{low:g}"
        high_text = str(int(high)) if integer or float(high).is_integer() else f"{high:g}"
        tk.Label(range_row, text=f"мин. {low_text}", bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="left")
        tk.Label(range_row, text=f"макс. {high_text}", bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="right")

        def move_with_key(direction: int) -> str:
            scale.focus_set()
            current = float(variable.get())
            new_value = min(high, max(low, current + direction * resolution))
            variable.set(int(new_value) if integer else round(new_value, 1))
            self._settings_changed()
            return "break"

        scale.bind("<Button-1>", lambda _event: scale.focus_set(), add="+")
        scale.bind("<Left>", lambda _event: move_with_key(-1))
        scale.bind("<Down>", lambda _event: move_with_key(-1))
        scale.bind("<Right>", lambda _event: move_with_key(1))
        scale.bind("<Up>", lambda _event: move_with_key(1))

    def _start_from_form(self) -> None:
        settings = self._settings_from_vars()
        if settings.herbivores == 0 and settings.predators == 0:
            messagebox.showerror("Пустой старт", "Добавь хотя бы одно животное.")
            return
        self.start_game(settings)

    def start_game(self, settings: GameSettings) -> None:
        if self.settings_frame is not None:
            self.settings_frame.destroy()
            self.settings_frame = None
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

    def _build_game_ui(self, frame: tk.Frame) -> None:
        assert self.simulation is not None
        cell_size = max(5, min(24, 900 // self.simulation.columns, 680 // self.simulation.rows))
        top = tk.Frame(frame, bg=PANEL_COLOR, padx=12, pady=8)
        top.pack(fill="x")
        tk.Label(top, text="ПИКСЕЛЬНАЯ ЭКОСИСТЕМА", bg=PANEL_COLOR, fg=TEXT_COLOR, font=("TkFixedFont", 11, "bold")).pack(
            side="left", fill="x", expand=True
        )
        self.speed_button = self._toolbar_button(top, "▶ ×2", self._toggle_game_speed, "#b9dff0", "#102117")
        self.speed_button.pack(side="right", padx=(6, 0))
        self._toolbar_button(top, "Завершить", self._force_finish, "#f3b6ae", "#331211").pack(side="right", padx=(6, 0))
        self._toolbar_button(top, "Пауза", self._toggle_pause, "#b7e3b0", "#102117").pack(side="right", padx=(6, 0))
        self._toolbar_button(top, "Новые настройки", self.show_settings, "#b7e3b0", "#102117").pack(side="right")

        content = tk.Frame(frame, bg=PANEL_COLOR)
        content.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self._build_stats_panel(content)

        board_area = tk.Frame(content, bg="#0d1510")
        board_area.pack(side="left", fill="both", expand=True)
        holder = tk.Frame(board_area, bg="#0d1510")
        holder.pack(expand=True)
        self.canvas = tk.Canvas(
            holder,
            width=self.simulation.columns * cell_size,
            height=self.simulation.rows * cell_size,
            bg=EMPTY_COLOR,
            highlightthickness=2,
            highlightbackground="#4f7657",
        )
        self.canvas.pack()
        self.renderer = CanvasRenderer(self.canvas, self.simulation, cell_size)
        self.renderer.draw()
        tk.Label(
            board_area,
            text="Зелёный — трава    Голубой — травоядное    Красный — хищник",
            bg=PANEL_COLOR,
            fg=MUTED_COLOR,
            pady=6,
        ).pack()

    @staticmethod
    def _toolbar_button(parent: tk.Frame, text: str, command, background: str, foreground: str) -> tk.Button:
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
        panel = tk.Frame(parent, bg=PANEL_COLOR, width=250)
        panel.pack(side="left", fill="y", padx=(0, 12))
        panel.pack_propagate(False)

        def group(title: str) -> tk.LabelFrame:
            box = tk.LabelFrame(panel, text=title, bg=PANEL_COLOR, fg=GRASS_COLOR, padx=10, pady=8, font=("TkFixedFont", 10, "bold"))
            box.pack(fill="x", pady=(0, 12))
            return box

        state = group("СОСТОЯНИЕ ИГРЫ")
        tk.Label(state, textvariable=self.state_var, width=24, anchor="w", bg=PANEL_COLOR, fg=TEXT_COLOR).pack()
        timing = group("СКОРОСТЬ + ВРЕМЯ")
        tk.Label(timing, textvariable=self.game_speed_var, width=24, anchor="w", bg=PANEL_COLOR, fg=TEXT_COLOR).pack()
        tk.Label(timing, textvariable=self.time_var, width=24, anchor="w", bg=PANEL_COLOR, fg=TEXT_COLOR).pack()
        counts = group("СЧЁТЧИКИ")
        tk.Label(counts, textvariable=self.herbivore_count_var, width=24, anchor="w", bg=PANEL_COLOR, fg=HERBIVORE_COLOR).pack()
        tk.Label(counts, textvariable=self.predator_count_var, width=24, anchor="w", bg=PANEL_COLOR, fg=PREDATOR_COLOR).pack()
        tk.Label(counts, textvariable=self.grass_count_var, width=24, anchor="w", bg=PANEL_COLOR, fg=GRASS_COLOR).pack()

    def _update_status(self) -> None:
        assert self.simulation is not None
        herbivores, predators, grass = self.simulation.counts()
        self.state_var.set("ПАУЗА" if self.paused else "ИГРА")
        self.game_speed_var.set(f"Скорость: ×{int(self.game_speed)}")
        self.time_var.set(f"Время: {self.simulation.elapsed:06.1f} с")
        self.herbivore_count_var.set(f"Травоядные: {herbivores:4d}")
        self.predator_count_var.set(f"Хищники:   {predators:4d}")
        self.grass_count_var.set(f"Трава:     {grass:4d}")

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
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self._show_game_over()

    def _tick(self) -> None:
        if self.simulation is None:
            return
        now = time.perf_counter()
        dt = min(0.1, max(0.0, now - self.last_tick)) * self.game_speed
        self.last_tick = now
        if not self.paused:
            self.simulation.step(dt)
        if self.renderer is not None:
            self.renderer.draw()
        self._update_status()
        if self.simulation.finished:
            self.after_id = None
            self._show_game_over()
            return
        self.after_id = self.root.after(TICK_MS, self._tick)

    def _show_game_over(self) -> None:
        self._detach_game_frame()
        self.canvas = None
        self.renderer = None
        self.speed_button = None
        assert self.simulation is not None

        frame = tk.Frame(self.root, bg=PANEL_COLOR, padx=24, pady=20)
        frame.pack(fill="both", expand=True)
        self.game_frame = frame
        tk.Label(frame, text="ИГРА ОКОНЧЕНА", bg=PANEL_COLOR, fg=TEXT_COLOR, font=("TkFixedFont", 19, "bold")).pack(pady=(4, 4))
        tk.Label(frame, text=self.simulation.finish_reason, bg=PANEL_COLOR, fg=MUTED_COLOR).pack(pady=(0, 10))
        graph = tk.Canvas(frame, bg="#101a14", highlightthickness=1, highlightbackground="#4f7657")
        graph.pack(fill="both", expand=True, padx=8, pady=4)
        graph.bind("<Configure>", lambda event: self._draw_history_graph(graph, event.width, event.height))
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
        assert self.simulation is not None
        graph.delete("all")
        width, height = max(1, width), max(1, height)
        history = self.simulation.history
        left, top, right, bottom = 68, 28, 24, 54
        plot_width, plot_height = max(1, width - left - right), max(1, height - top - bottom)
        max_time = max(1.0, history[-1][0])
        max_count = max(1, max(max(point[1], point[2]) for point in history))
        graph.create_text(width // 2, 12, text="Численность животных во времени", fill=TEXT_COLOR, font=("TkDefaultFont", 11, "bold"))
        for index in range(6):
            fraction = index / 5
            y = bottom + top + plot_height * (1 - fraction)
            graph.create_line(left, y, width - right, y, fill="#294233")
            graph.create_text(left - 10, y, text=str(round(max_count * fraction)), fill=MUTED_COLOR, anchor="e")
        axis_bottom = top + plot_height
        graph.create_line(left, top, left, axis_bottom, fill="#71917a", width=2)
        graph.create_line(left, axis_bottom, width - right, axis_bottom, fill="#71917a", width=2)
        graph.create_text(left, axis_bottom + 22, text="0 с", fill=MUTED_COLOR, anchor="w")
        graph.create_text(width - right, axis_bottom + 22, text=f"{max_time:.1f} с", fill=MUTED_COLOR, anchor="e")

        def point(index: int, count: int) -> tuple[float, float]:
            elapsed = history[index][0]
            return left + elapsed / max_time * plot_width, top + plot_height - count / max_count * plot_height

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
        graph.create_rectangle(left, legend_y - 5, left + 12, legend_y + 7, fill=HERBIVORE_COLOR, outline="")
        graph.create_text(left + 20, legend_y + 1, text="Травоядные", fill=TEXT_COLOR, anchor="w")
        graph.create_rectangle(left + 150, legend_y - 5, left + 162, legend_y + 7, fill=PREDATOR_COLOR, outline="")
        graph.create_text(left + 170, legend_y + 1, text="Хищники", fill=TEXT_COLOR, anchor="w")
