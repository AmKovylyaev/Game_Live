"""Incremental canvas renderer that avoids recreating thousands of items."""

from __future__ import annotations

import tkinter as tk

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
        f"{round(first + (second - first) * amount):02x}"
        for first, second in zip(start_rgb, end_rgb, strict=True)
    )


class CanvasRenderer:
    def __init__(self, canvas: tk.Canvas, simulation: Simulation, cell_size: int) -> None:
        self.canvas = canvas
        self.simulation = simulation
        self.cell_size = cell_size
        self.grass_items: dict[tuple[int, int], int] = {}
        self.animal_items: dict[int, int] = {}
        self._draw_static_field()

    def draw(self) -> None:
        self._draw_grass()
        self._draw_animals()

    def _draw_static_field(self) -> None:
        width = self.simulation.columns * self.cell_size
        height = self.simulation.rows * self.cell_size
        self.canvas.create_rectangle(
            0,
            0,
            width,
            height,
            fill=GRASS_COLOR,
            outline="",
            tags=("grass-background",),
        )
        for column in range(1, self.simulation.columns):
            x = column * self.cell_size
            self.canvas.create_line(x, 0, x, height, fill=GRID_COLOR, tags=("grass-grid",))
        for row in range(1, self.simulation.rows):
            y = row * self.cell_size
            self.canvas.create_line(0, y, width, y, fill=GRID_COLOR, tags=("grass-grid",))

    def _draw_grass(self) -> None:
        field = self.simulation.grass
        changed_cells = field.take_changed_cells()
        if not changed_cells:
            return

        for cell in changed_cells:
            x, y = cell
            left, top = x * self.cell_size, y * self.cell_size
            if field.is_ready(cell):
                item = self.grass_items.pop(cell, None)
                if item is not None:
                    self.canvas.delete(item)
                continue

            stage = field.growth_stage(cell)
            color = blend_colors(GRASS_RECOVERY_START, GRASS_COLOR, stage / GRASS_GROWTH_STEPS)
            item = self.grass_items.get(cell)
            if item is None:
                self.grass_items[cell] = self.canvas.create_rectangle(
                    left,
                    top,
                    left + self.cell_size,
                    top + self.cell_size,
                    fill=color,
                    outline="",
                    tags=("grass-overlay",),
                )
            else:
                self.canvas.itemconfigure(item, fill=color)

        self.canvas.tag_raise("grass-grid")
        self.canvas.tag_raise("animals")

    def _draw_animals(self) -> None:
        inset = max(1, self.cell_size // 5)
        live_ids: set[int] = set()
        for animal in self.simulation.animals:
            animal_id = animal.entity_id
            live_ids.add(animal_id)
            left = int((animal.x - 0.5) * self.cell_size) + inset
            top = int((animal.y - 0.5) * self.cell_size) + inset
            right = int((animal.x + 0.5) * self.cell_size) - inset
            bottom = int((animal.y + 0.5) * self.cell_size) - inset
            color = HERBIVORE_COLOR if isinstance(animal, Herbivore) else PREDATOR_COLOR
            body = self.animal_items.get(animal_id)
            if body is None:
                body = self.canvas.create_rectangle(
                    left,
                    top,
                    max(left + 2, right),
                    max(top + 2, bottom),
                    fill=color,
                    outline="#102117",
                    tags=("animals",),
                )
                self.animal_items[animal_id] = body
            else:
                self.canvas.coords(body, left, top, max(left + 2, right), max(top + 2, bottom))

        for animal_id in set(self.animal_items) - live_ids:
            body = self.animal_items.pop(animal_id)
            self.canvas.delete(body)
