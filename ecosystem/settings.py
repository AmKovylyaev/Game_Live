"""Persistent game configuration and validation."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .constants import (
    DEFAULT_GRASS_REGROWTH_SECONDS,
    DEFAULT_HERBIVORE_SPEED,
    DEFAULT_HERBIVORE_STARVATION,
    DEFAULT_PREDATOR_SPEED,
    DEFAULT_PREDATOR_STARVATION,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_SETTINGS_DIRECTORY = "Pixel Ecosystem"


def _frozen_settings_directory(
    platform: str | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the conventional settings directory for a packaged app."""

    platform = sys.platform if platform is None else platform
    environment = os.environ if environment is None else environment
    home = Path.home() if home is None else home
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_SETTINGS_DIRECTORY
    if platform == "win32":
        app_data = environment.get("APPDATA")
        return (
            Path(app_data) / APP_SETTINGS_DIRECTORY
            if app_data
            else home / "AppData" / "Roaming" / APP_SETTINGS_DIRECTORY
        )
    config_home = environment.get("XDG_CONFIG_HOME")
    return (
        Path(config_home) / "pixel-ecosystem"
        if config_home
        else home / ".config" / "pixel-ecosystem"
    )


def _settings_path() -> Path:
    if getattr(sys, "frozen", False):
        return _frozen_settings_directory() / "settings.json"
    return PROJECT_ROOT / "settings.json"


SETTINGS_PATH = _settings_path()


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
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(
                    json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n"
                )
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        except OSError:
            # A read-only directory must not prevent the game from running.
            pass
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
