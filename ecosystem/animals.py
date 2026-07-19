"""Object-oriented animal behaviour for the ecosystem simulation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Deque, Optional

from .constants import (
    HERBIVORE_FOOD_NEEDED,
    HERBIVORE_REPRODUCTION_WINDOW,
    PREDATOR_FOOD_NEEDED,
    PREDATOR_REPRODUCTION_WINDOW,
)

if TYPE_CHECKING:
    from .settings import GameSettings


@dataclass(slots=True, eq=False)
class Animal:
    x: float
    y: float
    hungry_for: float = 0.0
    meals: Deque[float] = field(default_factory=deque)
    speed_effect_for: float = 0.0
    target: Optional[object] = None

    name: ClassVar[str]

    def effective_speed(self, settings: "GameSettings") -> float:
        speed = self.base_speed(settings)
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

    def base_speed(self, settings: "GameSettings") -> float:
        raise NotImplementedError

    def starvation_limit(self, settings: "GameSettings") -> float:
        raise NotImplementedError

    @property
    def speed_multiplier(self) -> float:
        raise NotImplementedError

    @property
    def meal_effect_duration(self) -> float:
        raise NotImplementedError

    @property
    def food_needed(self) -> int:
        raise NotImplementedError

    @property
    def reproduction_window(self) -> float:
        raise NotImplementedError

    def reproduction_coefficient(self, settings: "GameSettings") -> float:
        raise NotImplementedError


@dataclass(slots=True, eq=False)
class Herbivore(Animal):
    name: ClassVar[str] = "herbivore"

    def base_speed(self, settings: "GameSettings") -> float:
        return settings.herbivore_speed

    def starvation_limit(self, settings: "GameSettings") -> float:
        return settings.herbivore_starvation

    @property
    def speed_multiplier(self) -> float:
        return 1.25

    @property
    def meal_effect_duration(self) -> float:
        return 1.5

    @property
    def food_needed(self) -> int:
        return HERBIVORE_FOOD_NEEDED

    @property
    def reproduction_window(self) -> float:
        return HERBIVORE_REPRODUCTION_WINDOW

    def reproduction_coefficient(self, settings: "GameSettings") -> float:
        return settings.herbivore_reproduction


@dataclass(slots=True, eq=False)
class Predator(Animal):
    name: ClassVar[str] = "predator"

    def base_speed(self, settings: "GameSettings") -> float:
        return settings.predator_speed

    def starvation_limit(self, settings: "GameSettings") -> float:
        return settings.predator_starvation

    @property
    def speed_multiplier(self) -> float:
        return 0.5

    @property
    def meal_effect_duration(self) -> float:
        return 1.0

    @property
    def food_needed(self) -> int:
        return PREDATOR_FOOD_NEEDED

    @property
    def reproduction_window(self) -> float:
        return PREDATOR_REPRODUCTION_WINDOW

    def reproduction_coefficient(self, settings: "GameSettings") -> float:
        return settings.predator_reproduction
