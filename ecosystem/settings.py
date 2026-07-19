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


@dataclass(frozen=True, slots=True)
class SettingRule:
    """Validation and UI metadata for one setting."""

    minimum: float
    maximum: float
    step: float
    integer: bool = False

    def normalize(self, value: Any, default: int | float) -> int | float:
        try:
            number = int(value) if self.integer else float(value)
        except (TypeError, ValueError):
            number = default
        number = min(self.maximum, max(self.minimum, number))
        return int(number) if self.integer else round(number, 1)


SETTING_RULES = {
    "columns": SettingRule(8, 100, 1, integer=True),
    "rows": SettingRule(8, 70, 1, integer=True),
    "herbivores": SettingRule(0, 300, 1, integer=True),
    "predators": SettingRule(0, 150, 1, integer=True),
    "grass_regrowth": SettingRule(3, 30, 1),
    "herbivore_reproduction": SettingRule(0.1, 3, 0.1),
    "predator_reproduction": SettingRule(0.1, 3, 0.1),
    "herbivore_starvation": SettingRule(5, 15, 1),
    "predator_starvation": SettingRule(5, 15, 1),
    "herbivore_speed": SettingRule(0.5, 6, 0.1),
    "predator_speed": SettingRule(0.5, 8, 0.1),
}
SETTING_KEYS = tuple(SETTING_RULES)
REPRODUCTION_KEYS = ("herbivore_reproduction", "predator_reproduction")


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
        legacy_reproduction = SETTING_RULES["herbivore_reproduction"].normalize(
            data.get("reproduction_coefficient"), defaults.herbivore_reproduction
        )
        values = {
            name: rule.normalize(data.get(name, getattr(defaults, name)), getattr(defaults, name))
            for name, rule in SETTING_RULES.items()
        }
        for name in REPRODUCTION_KEYS:
            values[name] = SETTING_RULES[name].normalize(
                data.get(name, legacy_reproduction), legacy_reproduction
            )
        return cls(**values)

    def to_dict(self) -> dict[str, int | float]:
        return {name: getattr(self, name) for name in SETTING_KEYS}


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
