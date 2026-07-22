"""Object-oriented animal behaviour for the ecosystem simulation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from itertools import count
from typing import TYPE_CHECKING, ClassVar, Deque, Optional

from .constants import (
    HERBIVORE_FOOD_NEEDED,
    HERBIVORE_REPRODUCTION_WINDOW,
    PREDATOR_FOOD_NEEDED,
    PREDATOR_REPRODUCTION_WINDOW,
)

if TYPE_CHECKING:
    from .settings import GameSettings


_ANIMAL_IDS = count()


def _next_animal_id() -> int:
    return next(_ANIMAL_IDS)


@dataclass(slots=True, eq=False)
class Animal:
    x: float
    y: float
    hungry_for: float = 0.0
    meals: Deque[float] = field(default_factory=deque)
    speed_effect_for: float = 0.0
    target: Optional[object] = None
    entity_id: int = field(default_factory=_next_animal_id, init=False)

    speed_setting: ClassVar[str]
    starvation_setting: ClassVar[str]
    reproduction_setting: ClassVar[str]
    speed_multiplier: ClassVar[float]
    meal_effect_duration: ClassVar[float]
    food_needed: ClassVar[int]
    reproduction_window: ClassVar[float]

    def effective_speed(self, settings: "GameSettings") -> float:
        speed = getattr(settings, self.speed_setting)
        return speed * self.speed_multiplier if self.speed_effect_for > 0 else speed

    def advance_timers(self, dt: float) -> None:
        self.hungry_for += dt
        self.speed_effect_for = max(0.0, self.speed_effect_for - dt)

    def eat(self, now: float) -> bool:
        """Apply a meal and report whether this meal completes reproduction."""
        self.hungry_for = 0.0
        self.target = None
        self.speed_effect_for = self.meal_effect_duration
        self.meals.append(now)
        while self.meals and now - self.meals[0] > self.reproduction_window:
            self.meals.popleft()
        if len(self.meals) >= self.food_needed:
            self.meals.clear()
            return True
        return False

    def starvation_limit(self, settings: "GameSettings") -> float:
        return getattr(settings, self.starvation_setting)

    def reproduction_coefficient(self, settings: "GameSettings") -> float:
        return getattr(settings, self.reproduction_setting)


@dataclass(slots=True, eq=False)
class Herbivore(Animal):
    speed_setting: ClassVar[str] = "herbivore_speed"
    starvation_setting: ClassVar[str] = "herbivore_starvation"
    reproduction_setting: ClassVar[str] = "herbivore_reproduction"
    speed_multiplier: ClassVar[float] = 1.25
    meal_effect_duration: ClassVar[float] = 1.5
    food_needed: ClassVar[int] = HERBIVORE_FOOD_NEEDED
    reproduction_window: ClassVar[float] = HERBIVORE_REPRODUCTION_WINDOW


@dataclass(slots=True, eq=False)
class Predator(Animal):
    speed_setting: ClassVar[str] = "predator_speed"
    starvation_setting: ClassVar[str] = "predator_starvation"
    reproduction_setting: ClassVar[str] = "predator_reproduction"
    speed_multiplier: ClassVar[float] = 0.5
    meal_effect_duration: ClassVar[float] = 1.0
    food_needed: ClassVar[int] = PREDATOR_FOOD_NEEDED
    reproduction_window: ClassVar[float] = PREDATOR_REPRODUCTION_WINDOW
