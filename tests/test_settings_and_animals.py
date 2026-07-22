"""Regression checks for shared settings rules and animal configuration."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ecosystem.animals import Herbivore, Predator
from ecosystem.constants import RENDER_MS, TICK_MS
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
from ecosystem.ui.renderer import CanvasRenderer


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

    def test_failed_atomic_save_keeps_the_previous_settings(self) -> None:
        saved_settings = GameSettings(columns=42, herbivores=12)
        updated_settings = GameSettings(columns=75, predators=9)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            store.save(saved_settings)

            with patch("ecosystem.settings.os.replace", side_effect=OSError):
                store.save(updated_settings)

            self.assertEqual(store.load(), saved_settings)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])


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

    def test_changed_cells_are_reported_only_when_the_visual_stage_changes(self) -> None:
        field = GrassField(columns=2, rows=2)

        field.consume((0, 0))
        self.assertEqual(field.take_changed_cells(), {(0, 0)})

        field.tick(0.1, regrowth_seconds=1.0)
        self.assertEqual(field.take_changed_cells(), set())

        field.tick(0.15, regrowth_seconds=1.0)
        self.assertEqual(field.growth_stage((0, 0)), 1)
        self.assertEqual(field.take_changed_cells(), {(0, 0)})

        field.tick(0.75, regrowth_seconds=1.0)
        self.assertTrue(field.is_ready((0, 0)))
        self.assertEqual(field.growth_stage((0, 0)), 5)
        self.assertEqual(field.take_changed_cells(), {(0, 0)})


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


class CanvasRendererTests(unittest.TestCase):
    class RecordingCanvas:
        def __init__(self) -> None:
            self._next_item = 1
            self.items: dict[int, dict[str, object]] = {}
            self.configured: list[int] = []
            self.deleted: list[int] = []

        def _create(self, kind: str, *coords: int, **options: object) -> int:
            item = self._next_item
            self._next_item += 1
            self.items[item] = {"kind": kind, "coords": coords, "options": options}
            return item

        def create_rectangle(self, *coords: int, **options: object) -> int:
            return self._create("rectangle", *coords, **options)

        def create_line(self, *coords: int, **options: object) -> int:
            return self._create("line", *coords, **options)

        def coords(self, item: int, *coords: int) -> None:
            self.items[item]["coords"] = coords

        def itemconfigure(self, item: int, **options: object) -> None:
            self.items[item]["options"].update(options)  # type: ignore[union-attr]
            self.configured.append(item)

        def delete(self, item: int) -> None:
            self.deleted.append(item)
            self.items.pop(item, None)

        def tag_raise(self, _tag: str) -> None:
            pass

    def test_grass_uses_a_static_background_and_updates_only_changed_cells(self) -> None:
        simulation = Simulation(GameSettings(columns=3, rows=2, herbivores=0, predators=0))
        canvas = self.RecordingCanvas()
        renderer = CanvasRenderer(canvas, simulation, cell_size=12)  # type: ignore[arg-type]

        renderer.draw()
        rectangles = [item for item in canvas.items.values() if item["kind"] == "rectangle"]
        self.assertEqual(len(rectangles), 1)
        self.assertEqual(renderer.grass_items, {})

        simulation.grass.consume((1, 1))
        renderer.draw()
        overlay = renderer.grass_items[(1, 1)]
        self.assertIn(overlay, canvas.items)

        simulation.grass.tick(0.1, regrowth_seconds=1.0)
        renderer.draw()
        self.assertEqual(canvas.configured, [])

        simulation.grass.tick(0.15, regrowth_seconds=1.0)
        renderer.draw()
        self.assertEqual(canvas.configured, [overlay])

        simulation.grass.tick(0.75, regrowth_seconds=1.0)
        renderer.draw()
        self.assertNotIn((1, 1), renderer.grass_items)
        self.assertIn(overlay, canvas.deleted)

    def test_each_animal_uses_one_canvas_rectangle(self) -> None:
        simulation = Simulation(GameSettings(columns=3, rows=2, herbivores=1, predators=0))
        canvas = self.RecordingCanvas()
        renderer = CanvasRenderer(canvas, simulation, cell_size=12)  # type: ignore[arg-type]

        renderer.draw()

        rectangles = [item for item in canvas.items.values() if item["kind"] == "rectangle"]
        self.assertEqual(len(rectangles), 2)
        self.assertEqual(set(renderer.animal_items), {simulation.herbivores[0].entity_id})


class SettingsUiTests(unittest.TestCase):
    def test_settings_form_exposes_every_saved_setting_once(self) -> None:
        visible_keys = [
            key for _title, _subtitle, specs in SLIDER_SECTIONS for key, _label in specs
        ]

        self.assertCountEqual(visible_keys, SETTING_KEYS)


class ReturnKeyBindingTests(unittest.TestCase):
    class Root:
        def __init__(self) -> None:
            self.bind_calls: list[tuple[str, object]] = []

        def bind(self, sequence: str, callback: object) -> None:
            self.bind_calls.append((sequence, callback))

    def test_return_key_is_bound_only_once(self) -> None:
        app = EcosystemApp.__new__(EcosystemApp)
        root = self.Root()
        app.root = root  # type: ignore[assignment]
        app._return_key_bound = False

        app._bind_return_key()
        app._bind_return_key()

        self.assertEqual([sequence for sequence, _callback in root.bind_calls], ["<Return>"])

    def test_return_key_starts_only_an_open_settings_form(self) -> None:
        app = EcosystemApp.__new__(EcosystemApp)
        app.settings_frame = object()  # type: ignore[assignment]
        app.setting_vars = dict.fromkeys(SETTING_KEYS, object())  # type: ignore[assignment]
        starts: list[None] = []
        app._start_from_form = lambda: starts.append(None)  # type: ignore[method-assign]

        app._start_from_return()
        app.settings_frame = None
        app._start_from_return()

        self.assertEqual(starts, [None])


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


class GameLoopTests(unittest.TestCase):
    class Root:
        def __init__(self) -> None:
            self.callbacks: list[tuple[int, object]] = []

        def after(self, delay_ms: int, callback: object) -> str:
            self.callbacks.append((delay_ms, callback))
            return str(len(self.callbacks))

        def after_cancel(self, _callback_id: str) -> None:
            pass

    class Renderer:
        def __init__(self) -> None:
            self.draw_calls = 0

        def draw(self) -> None:
            self.draw_calls += 1

    def test_simulation_and_render_use_separate_callbacks(self) -> None:
        app = EcosystemApp.__new__(EcosystemApp)
        root = self.Root()
        renderer = self.Renderer()
        app.root = root  # type: ignore[assignment]
        app.after_id = None
        app.render_after_id = None
        app.last_tick = 0.0
        app.paused = False
        app.game_speed = 1.0
        app.simulation = Simulation(GameSettings(columns=2, rows=2, herbivores=1, predators=0))
        app.renderer = renderer  # type: ignore[assignment]
        app._update_status = lambda: None  # type: ignore[method-assign]

        app._tick()
        app._render_tick()

        self.assertIn((TICK_MS, app._tick), root.callbacks)
        self.assertIn((RENDER_MS, app._render_tick), root.callbacks)
        self.assertEqual(renderer.draw_calls, 1)


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
