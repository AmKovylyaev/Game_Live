"""Regression checks for shared settings rules and animal configuration."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ecosystem.animals import Herbivore, Predator
from ecosystem.grass import GrassField
from ecosystem.settings import SETTING_KEYS, GameSettings, SettingsStore, _frozen_settings_directory
from ecosystem.simulation import Simulation
from ecosystem.ui.app import (
    CANVAS_BORDER_WIDTH,
    DEFAULT_WINDOW_WIDTH,
    GAME_CONTENT_PADDING,
    GAME_MAX_CANVAS_HEIGHT,
    GAME_STATS_PANEL_GAP,
    GAME_STATS_PANEL_WIDTH,
    GAME_VERTICAL_LAYOUT_RESERVE,
    MIN_WINDOW_HEIGHT,
    SETTINGS_FRAME_CLEANUP_DELAY_MS,
    SLIDER_SECTIONS,
    EcosystemApp,
)


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
            store = SettingsStore(Path(directory) / "nested" / "settings.json")
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


class GameFrameCleanupTests(unittest.TestCase):
    def test_cleanup_waits_for_the_settings_form_layout(self) -> None:
        class Root:
            def __init__(self) -> None:
                self.idle_callbacks: list[object] = []
                self.callbacks: list[tuple[int, object]] = []

            def after_idle(self, callback: object) -> None:
                self.idle_callbacks.append(callback)

            def after(self, delay_ms: int, callback: object) -> None:
                self.callbacks.append((delay_ms, callback))

        class Frame:
            def __init__(self) -> None:
                self.hidden = False
                self.destroyed = False

            def pack_forget(self) -> None:
                self.hidden = True

            def destroy(self) -> None:
                self.destroyed = True

        app = EcosystemApp.__new__(EcosystemApp)
        root = Root()
        frame = Frame()
        app.root = root  # type: ignore[assignment]
        app.game_frame = frame  # type: ignore[assignment]

        detached_frame = app._detach_game_frame()
        app._destroy_after_settings_paint(detached_frame)

        self.assertIsNone(app.game_frame)
        self.assertTrue(frame.hidden)
        self.assertFalse(frame.destroyed)
        self.assertEqual(len(root.idle_callbacks), 1)
        self.assertEqual(root.callbacks, [])
        root.idle_callbacks[0]()  # type: ignore[operator]
        self.assertEqual(len(root.callbacks), 1)
        delay_ms, callback = root.callbacks[0]
        self.assertEqual(delay_ms, SETTINGS_FRAME_CLEANUP_DELAY_MS)
        callback()  # type: ignore[operator]
        self.assertTrue(frame.destroyed)


class GameViewportTests(unittest.TestCase):
    def test_wide_field_fits_next_to_the_stats_panel(self) -> None:
        columns = 100
        cell_size = EcosystemApp._cell_size_for_viewport(
            columns=columns,
            rows=22,
            window_width=DEFAULT_WINDOW_WIDTH,
            window_height=MIN_WINDOW_HEIGHT,
        )
        available_width = (
            DEFAULT_WINDOW_WIDTH
            - 2 * GAME_CONTENT_PADDING
            - GAME_STATS_PANEL_WIDTH
            - GAME_STATS_PANEL_GAP
            - 2 * CANVAS_BORDER_WIDTH
        )

        self.assertLessEqual(columns * cell_size, available_width)

    def test_every_supported_height_fits_the_minimum_window(self) -> None:
        available_height = min(
            GAME_MAX_CANVAS_HEIGHT,
            MIN_WINDOW_HEIGHT - GAME_VERTICAL_LAYOUT_RESERVE,
        )

        for rows in range(8, 71):
            cell_size = EcosystemApp._cell_size_for_viewport(
                columns=8,
                rows=rows,
                window_width=DEFAULT_WINDOW_WIDTH,
                window_height=MIN_WINDOW_HEIGHT,
            )

            self.assertLessEqual(rows * cell_size, available_height)


class GrassMeterTests(unittest.TestCase):
    def test_coverage_uses_the_current_field_area(self) -> None:
        self.assertEqual(EcosystemApp._grass_coverage(50, columns=10, rows=10), 0.5)
        self.assertEqual(EcosystemApp._grass_coverage(150, columns=10, rows=10), 1.0)
        self.assertEqual(EcosystemApp._grass_coverage(-1, columns=10, rows=10), 0.0)


class PackagedSettingsTests(unittest.TestCase):
    def test_frozen_settings_use_platform_conventions(self) -> None:
        home = Path("/tmp/example-home")

        self.assertEqual(
            _frozen_settings_directory(platform="darwin", home=home),
            home / "Library" / "Application Support" / "Pixel Ecosystem",
        )
        self.assertEqual(
            _frozen_settings_directory(
                platform="win32",
                environment={"APPDATA": "C:/Users/example/AppData/Roaming"},
                home=home,
            ),
            Path("C:/Users/example/AppData/Roaming") / "Pixel Ecosystem",
        )
        self.assertEqual(
            _frozen_settings_directory(
                platform="linux", environment={"XDG_CONFIG_HOME": "/tmp/config"}, home=home
            ),
            Path("/tmp/config/pixel-ecosystem"),
        )
