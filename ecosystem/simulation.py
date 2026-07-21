"""Core rules and update loop for the ecosystem."""

from __future__ import annotations

import math
import random
from itertools import chain
from typing import Iterable, Optional, TypeVar

from .animals import Animal, Herbivore, Predator
from .constants import HISTORY_INTERVAL, MAX_HISTORY_POINTS, PREDATOR_ONLY_DELAY, TARGET_BUCKET_SIZE
from .grass import Cell, GrassField
from .settings import GameSettings
from .spatial import SpatialIndex

Target = TypeVar("Target")


class Simulation:
    """Owns the world state and applies all simulation rules each frame."""

    def __init__(
        self,
        settings: GameSettings,
        *,
        rng: random.Random | None = None,
        bucket_size: int = TARGET_BUCKET_SIZE,
    ) -> None:
        self.settings = settings
        self.columns = settings.columns
        self.rows = settings.rows
        self.rng = rng if rng is not None else random.Random()
        self.grass = GrassField(settings.columns, settings.rows)
        self.grass_index = SpatialIndex[Cell](self.columns, self.rows, bucket_size)
        for cell in self.grass.ready:
            self.grass_index.add(cell, cell[0] + 0.5, cell[1] + 0.5)
        self.herbivores = [Herbivore(*self._random_position()) for _ in range(settings.herbivores)]
        self.predators = [Predator(*self._random_position()) for _ in range(settings.predators)]
        self.herbivore_index = SpatialIndex[Herbivore](self.columns, self.rows, bucket_size)
        for herbivore in self.herbivores:
            self.herbivore_index.add(herbivore, herbivore.x, herbivore.y)
        self.elapsed = 0.0
        self.history: list[tuple[float, int, int]] = [
            (0.0, len(self.herbivores), len(self.predators))
        ]
        self._history_timer = 0.0
        self.predator_only_started: Optional[float] = None
        self.finished = False
        self.finish_reason = ""

    @property
    def animals(self) -> Iterable[Animal]:
        return chain(self.herbivores, self.predators)

    def _random_position(self) -> tuple[float, float]:
        return (
            self.rng.uniform(0.5, max(0.5, self.columns - 0.5)),
            self.rng.uniform(0.5, max(0.5, self.rows - 0.5)),
        )

    def step(self, dt: float) -> None:
        if self.finished:
            return
        self.elapsed += dt
        self.grass.tick(dt, self.settings.grass_regrowth, rng=self.rng)
        self._index_newly_ready_grass()
        for animal in self.animals:
            animal.advance_timers(dt)

        self._move_herbivores(dt)
        self._move_predators(dt)
        self._remove_starved_animals()
        self._record_history(dt)
        self._check_finished()

    def finish(self, reason: str = "Игра завершена вручную.") -> None:
        if self.finished:
            return
        self.finished = True
        self.finish_reason = reason
        self._record_history(0.0, force=True)

    def counts(self) -> tuple[int, int, int]:
        return len(self.herbivores), len(self.predators), self.grass.ready_count

    def _move_herbivores(self, dt: float) -> None:
        for herbivore in tuple(self.herbivores):
            target = herbivore.target
            if not (isinstance(target, tuple) and self.grass_index.contains(target)):
                target = self._choose_target(
                    self.grass_index.nearest(
                        herbivore.x,
                        herbivore.y,
                        count=5,
                        tie_breaker=lambda cell: cell,
                    ).nearest
                )
                herbivore.target = target
            if target is None:
                continue
            cell = target
            reached_target = self._move_towards(herbivore, cell[0] + 0.5, cell[1] + 0.5, dt)
            self.herbivore_index.update(herbivore, herbivore.x, herbivore.y)
            if reached_target and self.grass.consume(cell):
                self.grass_index.remove(cell)
                self._handle_meal(herbivore)

    def _move_predators(self, dt: float) -> None:
        for predator in tuple(self.predators):
            target = predator.target
            if not (isinstance(target, Herbivore) and self.herbivore_index.contains(target)):
                target = self._choose_target(
                    self.herbivore_index.nearest(
                        predator.x,
                        predator.y,
                        count=5,
                        tie_breaker=lambda prey: prey.entity_id,
                    ).nearest,
                )
                predator.target = target
            if target is None:
                continue
            prey = target
            reached_target = self._move_towards(predator, prey.x, prey.y, dt)
            if reached_target and self.herbivore_index.contains(prey):
                self.herbivores.remove(prey)
                self.herbivore_index.remove(prey)
                self._handle_meal(predator)

    def _handle_meal(self, animal: Animal) -> None:
        if animal.eat(self.elapsed):
            self._spawn_offspring(animal, animal.reproduction_coefficient(self.settings))

    def _spawn_offspring(self, parent: Animal, coefficient: float) -> None:
        children = int(coefficient)
        if self.rng.random() < coefficient - children:
            children += 1
        for _ in range(children):
            child = self._spawn_near(parent)
            if isinstance(child, Herbivore):
                self.herbivores.append(child)
                self.herbivore_index.add(child, child.x, child.y)
            else:
                self.predators.append(child)

    def _spawn_near(self, parent: Animal) -> Animal:
        angle = self.rng.random() * math.tau
        radius = 0.65
        x = min(max(parent.x + math.cos(angle) * radius, 0.5), self.columns - 0.5)
        y = min(max(parent.y + math.sin(angle) * radius, 0.5), self.rows - 0.5)
        return Herbivore(x, y) if isinstance(parent, Herbivore) else Predator(x, y)

    def _move_towards(self, animal: Animal, target_x: float, target_y: float, dt: float) -> bool:
        dx, dy = target_x - animal.x, target_y - animal.y
        distance = math.hypot(dx, dy)
        if distance <= 0.12:
            return True
        speed = animal.effective_speed(self.settings)
        travel = min(distance, speed * dt)
        animal.x = min(max(animal.x + dx / distance * travel, 0.5), self.columns - 0.5)
        animal.y = min(max(animal.y + dy / distance * travel, 0.5), self.rows - 0.5)
        return distance <= speed * dt + 0.12

    def _choose_target(self, nearest: list[tuple[float, Target]]) -> Optional[Target]:
        if not nearest:
            return None
        weights = [1.0 / max(distance, 0.05) for distance, _ in nearest]
        choice = self.rng.random() * sum(weights)
        for weight, (_, candidate) in zip(weights, nearest, strict=True):
            choice -= weight
            if choice <= 0:
                return candidate
        return nearest[-1][1]

    def _index_newly_ready_grass(self) -> None:
        for cell in self.grass.take_newly_ready_cells():
            self.grass_index.add(cell, cell[0] + 0.5, cell[1] + 0.5)

    def _remove_starved_animals(self) -> None:
        living_herbivores: list[Herbivore] = []
        for herbivore in self.herbivores:
            if herbivore.hungry_for < herbivore.starvation_limit(self.settings):
                living_herbivores.append(herbivore)
            else:
                self.herbivore_index.remove(herbivore)
        self.herbivores = living_herbivores
        self.predators = [
            animal
            for animal in self.predators
            if animal.hungry_for < animal.starvation_limit(self.settings)
        ]

    def _record_history(self, dt: float, *, force: bool = False) -> None:
        self._history_timer += dt
        if not force and self._history_timer < HISTORY_INTERVAL:
            return
        if len(self.history) >= MAX_HISTORY_POINTS:
            self.history = self.history[::2]
        self.history.append((self.elapsed, len(self.herbivores), len(self.predators)))
        self._history_timer = 0.0

    def _check_finished(self) -> None:
        herbivores, predators, grass = self.counts()
        if herbivores == 0 and predators > 0:
            if self.predator_only_started is None:
                self.predator_only_started = self.elapsed
            elif self.elapsed - self.predator_only_started >= PREDATOR_ONLY_DELAY:
                self.finish("Травоядные закончились. Хищники остались без добычи.")
            return
        if herbivores > 0 and predators == 0:
            self.predator_only_started = None
            if grass == 0:
                self.finish("Остались только травоядные — вся трава съедена.")
            return
        if herbivores > 0 and predators > 0:
            self.predator_only_started = None
            return
        self.finish("Все животные погибли.")
