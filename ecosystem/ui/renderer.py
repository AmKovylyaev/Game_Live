"""Incremental canvas renderer that avoids recreating thousands of items."""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from ..animals import Herbivore
from ..constants import (
    GRASS_COLOR,
    GRASS_GROWTH_STEPS,
    GRASS_RECOVERY_START,
    GRID_COLOR,
    HERBIVORE_COLOR,
    PREDATOR_COLOR,
)
from ..simulation import Simulation


def blend_colors(start: str, end: str, amount: float) -> str:
    amount = min(1.0, max(0.0, amount))
    start_rgb = tuple(int(start[index : index + 2], 16) for index in (1, 3, 5))
    end_rgb = tuple(int(end[index : index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(
        f"{round(first + (second - first) * amount):02x}" for first, second in zip(start_rgb, end_rgb)
    )


class CanvasRenderer:
    def __init__(self, canvas: tk.Canvas, simulation: Simulation, cell_size: int) -> None:
        self.canvas = canvas
        self.simulation = simulation
        self.cell_size = cell_size
        self.grass_items: dict[tuple[int, int], int] = {}
        self.grass_states: dict[tuple[int, int], int] = {}
        self.animal_items: dict[int, tuple[int, Optional[int]]] = {}

    def draw(self) -> None:
        self._draw_grass()
        self._draw_animals()

    def _draw_grass(self) -> None:
        field = self.simulation.grass
        for cell in field.iter_cells():
            x, y = cell
            left, top = x * self.cell_size, y * self.cell_size
            if field.is_ready(cell):
                state, color = GRASS_GROWTH_STEPS, GRASS_COLOR
            else:
                stage = min(GRASS_GROWTH_STEPS - 1, int(field.growth_value(cell) * GRASS_GROWTH_STEPS))
                state = stage
                color = blend_colors(GRASS_RECOVERY_START, GRASS_COLOR, stage / GRASS_GROWTH_STEPS)
            item = self.grass_items.get(cell)
            if item is None:
                self.grass_items[cell] = self.canvas.create_rectangle(
                    left,
                    top,
                    left + self.cell_size,
                    top + self.cell_size,
                    fill=color,
                    outline=GRID_COLOR,
                )
            elif self.grass_states.get(cell) != state:
                self.canvas.itemconfigure(item, fill=color)
            self.grass_states[cell] = state

    def _draw_animals(self) -> None:
        inset = max(1, self.cell_size // 5)
        live_ids: set[int] = set()
        for animal in self.simulation.animals:
            animal_id = id(animal)
            live_ids.add(animal_id)
            left = int((animal.x - 0.5) * self.cell_size) + inset
            top = int((animal.y - 0.5) * self.cell_size) + inset
            right = int((animal.x + 0.5) * self.cell_size) - inset
            bottom = int((animal.y + 0.5) * self.cell_size) - inset
            color = HERBIVORE_COLOR if isinstance(animal, Herbivore) else PREDATOR_COLOR
            body, eye = self.animal_items.get(animal_id, (None, None))
            if body is None:
                body = self.canvas.create_rectangle(
                    left, top, max(left + 2, right), max(top + 2, bottom), fill=color, outline="#102117"
                )
                if self.cell_size >= 12:
                    eye_size = max(1, self.cell_size // 10)
                    eye = self.canvas.create_rectangle(
                        right - eye_size * 2,
                        top + eye_size,
                        right - eye_size,
                        top + eye_size * 2,
                        fill="#102117",
                        outline="",
                    )
                self.animal_items[animal_id] = (body, eye)
            else:
                self.canvas.coords(body, left, top, max(left + 2, right), max(top + 2, bottom))
                self.canvas.itemconfigure(body, fill=color)
            if eye is not None:
                eye_size = max(1, self.cell_size // 10)
                self.canvas.coords(eye, right - eye_size * 2, top + eye_size, right - eye_size, top + eye_size * 2)

        for animal_id in set(self.animal_items) - live_ids:
            body, eye = self.animal_items.pop(animal_id)
            self.canvas.delete(body)
            if eye is not None:
                self.canvas.delete(eye)
