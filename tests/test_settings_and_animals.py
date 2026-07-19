"""Regression checks for shared settings rules and animal configuration."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ecosystem.animals import Herbivore, Predator
from ecosystem.grass import GrassField
from ecosystem.settings import SETTING_KEYS, GameSettings, SettingsStore
from ecosystem.simulation import Simulation
from ecosystem.ui.app import SLIDER_SECTIONS


class GameSettingsTests(unittest.TestCase):
    def test_from_dict_normalizes_values_and_keeps_legacy_reproduction(self) -> None:
        settings = GameSettings.from_dict(
            {
                "columns": "120",
                "rows": "not a number",
                "reproduction_coefficient": 2.4,
                "herbivore_reproduction": "invalid",
                "predator_reproduction": 0.01,
                "herbivore_speed": 3.26,
            }
        )

        self.assertEqual(settings.columns, 100)
        self.assertEqual(settings.rows, GameSettings().rows)
        self.assertEqual(settings.herbivore_reproduction, 2.4)
        self.assertEqual(settings.predator_reproduction, 0.1)
        self.assertEqual(settings.herbivore_speed, 3.3)

    def test_to_dict_uses_the_shared_settings_schema(self) -> None:
        self.assertEqual(set(GameSettings().to_dict()), set(SETTING_KEYS))

    def test_store_round_trip(self) -> None:
        settings = GameSettings(columns=42, herbivores=12, predator_speed=4.5)
        with TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            store.save(settings)

            self.assertEqual(store.load(), settings)


class AnimalConfigurationTests(unittest.TestCase):
    def test_species_settings_drive_speed_starvation_and_reproduction(self) -> None:
        settings = GameSettings(
            herbivore_speed=2.0,
            predator_speed=4.0,
            herbivore_starvation=7.0,
            predator_starvation=9.0,
            herbivore_reproduction=1.5,
            predator_reproduction=0.5,
        )
        herbivore = Herbivore(1, 1)
        predator = Predator(1, 1)

        herbivore.eat(0.0)
        predator.eat(0.0)

        self.assertEqual(herbivore.effective_speed(settings), 2.5)
        self.assertEqual(predator.effective_speed(settings), 2.0)
        self.assertEqual(herbivore.starvation_limit(settings), 7.0)
        self.assertEqual(predator.starvation_limit(settings), 9.0)
        self.assertEqual(herbivore.reproduction_coefficient(settings), 1.5)
        self.assertEqual(predator.reproduction_coefficient(settings), 0.5)


class GrassFieldTests(unittest.TestCase):
    def test_consumed_grass_regrows_from_a_ready_neighbor(self) -> None:
        field = GrassField(columns=2, rows=2)

        self.assertTrue(field.consume((0, 0)))
        field.tick(0.5, regrowth_seconds=1.0)
        self.assertFalse(field.is_ready((0, 0)))
        self.assertEqual(field.growth_value((0, 0)), 0.5)

        field.tick(0.5, regrowth_seconds=1.0)
        self.assertTrue(field.is_ready((0, 0)))
        self.assertEqual(field.ready_count, 4)


class SimulationSmokeTests(unittest.TestCase):
    def test_empty_ecosystem_finishes_immediately(self) -> None:
        simulation = Simulation(GameSettings(herbivores=0, predators=0))

        simulation.step(0.1)

        self.assertTrue(simulation.finished)
        self.assertEqual(simulation.finish_reason, "Все животные погибли.")

    def test_simulation_steps_without_errors(self) -> None:
        simulation = Simulation(GameSettings(columns=8, rows=8, herbivores=3, predators=1))

        for _ in range(20):
            simulation.step(0.1)

        herbivores, predators, grass = simulation.counts()
        self.assertGreaterEqual(herbivores, 0)
        self.assertGreaterEqual(predators, 0)
        self.assertGreaterEqual(grass, 0)


class SettingsUiTests(unittest.TestCase):
    def test_settings_form_exposes_every_saved_setting_once(self) -> None:
        visible_keys = [
            key for _title, _subtitle, specs in SLIDER_SECTIONS for key, _label in specs
        ]

        self.assertCountEqual(visible_keys, SETTING_KEYS)
