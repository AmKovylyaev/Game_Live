"""Efficient sparse tracking of ready and regrowing grass cells."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .constants import GRASS_GROWTH_STEPS, GRASS_INDEPENDENT_START_CHANCE

Cell = tuple[int, int]


@dataclass(slots=True)
class GrassField:
    columns: int
    rows: int
    ready: set[Cell] = field(init=False)
    growth: dict[Cell, float] = field(default_factory=dict)
    independent: set[Cell] = field(default_factory=set)
    changed_cells: set[Cell] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.ready = {(x, y) for x in range(self.columns) for y in range(self.rows)}

    @property
    def ready_count(self) -> int:
        return len(self.ready)

    def is_ready(self, cell: Cell) -> bool:
        return cell in self.ready

    def consume(self, cell: Cell) -> bool:
        if cell not in self.ready:
            return False
        self.ready.remove(cell)
        self.growth[cell] = 0.0
        self.independent.discard(cell)
        self.changed_cells.add(cell)
        return True

    def growth_value(self, cell: Cell) -> float:
        return 1.0 if cell in self.ready else self.growth.get(cell, 0.0)

    def growth_stage(self, cell: Cell) -> int:
        if cell in self.ready:
            return GRASS_GROWTH_STEPS
        return min(
            GRASS_GROWTH_STEPS - 1,
            int(self.growth.get(cell, 0.0) * GRASS_GROWTH_STEPS),
        )

    def take_changed_cells(self) -> set[Cell]:
        changed_cells = self.changed_cells
        self.changed_cells = set()
        return changed_cells

    def tick(self, dt: float, regrowth_seconds: float) -> None:
        if not self.growth:
            return
        growth_step = dt / regrowth_seconds
        independent_chance = 1.0 - (1.0 - GRASS_INDEPENDENT_START_CHANCE) ** max(0.0, dt)
        for cell in tuple(self.growth):
            previous_stage = self.growth_stage(cell)
            if self._has_ready_neighbor(cell) or cell in self.independent:
                self.growth[cell] = min(1.0, self.growth[cell] + growth_step)
            elif random.random() < independent_chance:
                self.independent.add(cell)
                self.growth[cell] = min(1.0, self.growth[cell] + growth_step)

            if self.growth[cell] >= 1.0:
                self.ready.add(cell)
                self.growth.pop(cell, None)
                self.independent.discard(cell)

            if self.growth_stage(cell) != previous_stage:
                self.changed_cells.add(cell)

    def _has_ready_neighbor(self, cell: Cell) -> bool:
        x, y = cell
        return any(
            (neighbor_x, neighbor_y) in self.ready
            for neighbor_x in range(max(0, x - 1), min(self.columns, x + 2))
            for neighbor_y in range(max(0, y - 1), min(self.rows, y + 2))
            if (neighbor_x, neighbor_y) != cell
        )
