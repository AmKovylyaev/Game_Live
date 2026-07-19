"""Persistent game configuration and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_GRASS_REGROWTH_SECONDS,
    DEFAULT_HERBIVORE_SPEED,
    DEFAULT_HERBIVORE_STARVATION,
    DEFAULT_PREDATOR_SPEED,
    DEFAULT_PREDATOR_STARVATION,
)

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"


@dataclass(slots=True)
class GameSettings:
    columns: int = 30
    rows: int = 22
    herbivores: int = 8
    predators: int = 3
    grass_regrowth: float = DEFAULT_GRASS_REGROWTH_SECONDS
    herbivore_reproduction: float = 1.0
    predator_reproduction: float = 1.0
    herbivore_starvation: float = DEFAULT_HERBIVORE_STARVATION
    predator_starvation: float = DEFAULT_PREDATOR_STARVATION
    herbivore_speed: float = DEFAULT_HERBIVORE_SPEED
    predator_speed: float = DEFAULT_PREDATOR_SPEED

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameSettings":
        defaults = cls()

        def number(name: str, default: float, low: float, high: float, *, integer: bool = False) -> float | int:
            try:
                value = int(data.get(name, default)) if integer else float(data.get(name, default))
            except (TypeError, ValueError):
                value = default
            return min(high, max(low, value))

        legacy_reproduction = number("reproduction_coefficient", defaults.herbivore_reproduction, 0.1, 3)
        return cls(
            columns=int(number("columns", defaults.columns, 8, 100, integer=True)),
            rows=int(number("rows", defaults.rows, 8, 70, integer=True)),
            herbivores=int(number("herbivores", defaults.herbivores, 0, 300, integer=True)),
            predators=int(number("predators", defaults.predators, 0, 150, integer=True)),
            grass_regrowth=round(number("grass_regrowth", defaults.grass_regrowth, 3, 30), 1),
            herbivore_reproduction=round(number("herbivore_reproduction", legacy_reproduction, 0.1, 3), 1),
            predator_reproduction=round(number("predator_reproduction", legacy_reproduction, 0.1, 3), 1),
            herbivore_starvation=round(number("herbivore_starvation", defaults.herbivore_starvation, 5, 15), 1),
            predator_starvation=round(number("predator_starvation", defaults.predator_starvation, 5, 15), 1),
            herbivore_speed=round(number("herbivore_speed", defaults.herbivore_speed, 0.5, 6), 1),
            predator_speed=round(number("predator_speed", defaults.predator_speed, 0.5, 8), 1),
        )

    def to_dict(self) -> dict[str, int | float]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "herbivores": self.herbivores,
            "predators": self.predators,
            "grass_regrowth": self.grass_regrowth,
            "herbivore_reproduction": self.herbivore_reproduction,
            "predator_reproduction": self.predator_reproduction,
            "herbivore_starvation": self.herbivore_starvation,
            "predator_starvation": self.predator_starvation,
            "herbivore_speed": self.herbivore_speed,
            "predator_speed": self.predator_speed,
        }


class SettingsStore:
    """Small JSON repository. Settings are read once and cached by the UI."""

    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path

    def load(self) -> GameSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return GameSettings.from_dict(data)
        except (OSError, json.JSONDecodeError):
            pass
        return GameSettings()

    def save(self, settings: GameSettings) -> None:
        try:
            self.path.write_text(
                json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            # A read-only directory must not prevent the game from running.
            pass
