"""Tests for indexed target lookup and deterministic simulation state."""

from __future__ import annotations

import math
import random
import unittest
from heapq import nsmallest

from ecosystem.animals import Herbivore
from ecosystem.constants import MAX_HERBIVORE_POPULATION, MAX_PREDATOR_POPULATION
from ecosystem.grass import GrassField
from ecosystem.settings import GameSettings
from ecosystem.simulation import Simulation
from ecosystem.spatial import SpatialIndex


class SpatialIndexTests(unittest.TestCase):
    def test_nearest_items_match_a_full_scan_without_visiting_every_item(self) -> None:
        points = [(column, row) for column in range(20) for row in range(20)]
        index = SpatialIndex[tuple[int, int]](columns=20, rows=20, bucket_size=4)
        for column, row in points:
            index.add((column, row), column + 0.5, row + 0.5)

        query_x, query_y = 10.2, 9.8
        indexed = index.nearest(
            query_x,
            query_y,
            count=5,
            tie_breaker=lambda point: point,
        )
        expected = nsmallest(
            5,
            (
                (math.hypot(column + 0.5 - query_x, row + 0.5 - query_y), (column, row))
                for column, row in points
            ),
            key=lambda result: (result[0], result[1]),
        )

        self.assertEqual(indexed.nearest, expected)
        self.assertLess(indexed.candidates_examined, len(points))

    def test_moving_and_removing_an_item_updates_the_index(self) -> None:
        index = SpatialIndex[str](columns=16, rows=16, bucket_size=4)
        index.add("near", 1.0, 1.0)
        index.add("far", 14.0, 14.0)

        self.assertEqual(index.nearest(1.0, 1.0, count=1, tie_breaker=str).nearest[0][1], "near")

        index.update("far", 1.2, 1.2)
        index.remove("near")

        self.assertFalse(index.contains("near"))
        self.assertEqual(index.nearest(1.0, 1.0, count=1, tie_breaker=str).nearest[0][1], "far")


class GrassIndexEventTests(unittest.TestCase):
    def test_regrown_grass_is_reported_without_consuming_render_changes(self) -> None:
        field = GrassField(columns=2, rows=2)

        field.consume((0, 0))
        self.assertEqual(field.take_changed_cells(), {(0, 0)})
        field.tick(1.0, regrowth_seconds=1.0, rng=random.Random(1))

        self.assertEqual(field.take_newly_ready_cells(), {(0, 0)})
        self.assertEqual(field.take_changed_cells(), {(0, 0)})


class SimulationSpatialLifecycleTests(unittest.TestCase):
    def test_indices_follow_grass_consumption_regrowth_birth_and_starvation(self) -> None:
        simulation = Simulation(
            GameSettings(columns=4, rows=4, herbivores=1, predators=0),
            rng=random.Random(7),
        )
        herbivore = simulation.herbivores[0]
        herbivore.x = herbivore.y = 0.5
        herbivore.target = (0, 0)
        simulation.herbivore_index.update(herbivore, herbivore.x, herbivore.y)

        simulation._move_herbivores(0.0)

        self.assertFalse(simulation.grass_index.contains((0, 0)))
        self.assertTrue(simulation.herbivore_index.contains(herbivore))

        simulation.grass.tick(1.0, regrowth_seconds=1.0, rng=simulation.rng)
        simulation._index_newly_ready_grass()
        self.assertTrue(simulation.grass_index.contains((0, 0)))

        simulation._spawn_offspring(herbivore, 1.0)
        self.assertEqual(simulation.herbivore_index.item_count, 2)

        herbivore.hungry_for = 100.0
        simulation._remove_starved_animals()
        self.assertFalse(simulation.herbivore_index.contains(herbivore))

    def test_predator_removes_prey_from_the_lookup_index(self) -> None:
        simulation = Simulation(
            GameSettings(columns=4, rows=4, herbivores=1, predators=1),
            rng=random.Random(9),
        )
        herbivore = simulation.herbivores[0]
        predator = simulation.predators[0]
        herbivore.x = herbivore.y = predator.x = predator.y = 0.5
        simulation.herbivore_index.update(herbivore, herbivore.x, herbivore.y)
        predator.target = herbivore

        simulation._move_predators(0.0)

        self.assertEqual(simulation.herbivores, [])
        self.assertFalse(simulation.herbivore_index.contains(herbivore))


class PopulationLimitTests(unittest.TestCase):
    def test_offspring_do_not_exceed_the_population_caps(self) -> None:
        herbivore_simulation = Simulation(
            GameSettings(columns=8, rows=8, herbivores=MAX_HERBIVORE_POPULATION, predators=0),
            rng=random.Random(3),
        )
        predator_simulation = Simulation(
            GameSettings(columns=8, rows=8, herbivores=0, predators=MAX_PREDATOR_POPULATION),
            rng=random.Random(4),
        )

        herbivore_simulation._spawn_offspring(herbivore_simulation.herbivores[0], 3.0)
        predator_simulation._spawn_offspring(predator_simulation.predators[0], 3.0)

        self.assertEqual(len(herbivore_simulation.herbivores), MAX_HERBIVORE_POPULATION)
        self.assertEqual(herbivore_simulation.herbivore_index.item_count, MAX_HERBIVORE_POPULATION)
        self.assertEqual(len(predator_simulation.predators), MAX_PREDATOR_POPULATION)


class PredatorTargetingTests(unittest.TestCase):
    def test_nearby_prey_always_uses_the_closest_target(self) -> None:
        simulation = Simulation(GameSettings(columns=8, rows=8), rng=random.Random(0))
        closest = Herbivore(2.5, 0.5)
        farther = Herbivore(3.5, 0.5)
        simulation.rng = random.Random(0)

        target = simulation._choose_predator_target([(2.0, closest), (3.0, farther)])

        self.assertIs(target, closest)

    def test_distant_prey_keeps_the_weighted_choice(self) -> None:
        simulation = Simulation(GameSettings(columns=8, rows=8), rng=random.Random(0))
        closer = Herbivore(3.6, 0.5)
        farther = Herbivore(4.5, 0.5)
        simulation.rng = random.Random(0)

        target = simulation._choose_predator_target([(3.1, closer), (4.0, farther)])

        self.assertIs(target, farther)


class PredatorStartPositionTests(unittest.TestCase):
    def test_predators_start_within_ten_cells_of_a_herbivore(self) -> None:
        simulation = Simulation(
            GameSettings(columns=30, rows=22, herbivores=4, predators=10),
            rng=random.Random(12),
        )

        for predator in simulation.predators:
            distance_to_nearest_prey = min(
                math.hypot(predator.x - herbivore.x, predator.y - herbivore.y)
                for herbivore in simulation.herbivores
            )
            self.assertLessEqual(distance_to_nearest_prey, 10.0)

    def test_predators_without_herbivores_use_a_valid_random_position(self) -> None:
        simulation = Simulation(
            GameSettings(columns=8, rows=8, herbivores=0, predators=1),
            rng=random.Random(12),
        )
        predator = simulation.predators[0]

        self.assertGreaterEqual(predator.x, 0.5)
        self.assertLessEqual(predator.x, 7.5)
        self.assertGreaterEqual(predator.y, 0.5)
        self.assertLessEqual(predator.y, 7.5)


class DeterministicSimulationTests(unittest.TestCase):
    def test_equal_seeds_produce_equal_world_state(self) -> None:
        settings = GameSettings(
            columns=12,
            rows=10,
            herbivores=4,
            predators=2,
            grass_regrowth=4.0,
            herbivore_reproduction=0.1,
            predator_reproduction=0.1,
        )
        first = Simulation(settings, rng=random.Random(42))
        second = Simulation(settings, rng=random.Random(42))

        for _ in range(20):
            first.step(0.1)
            second.step(0.1)

        self.assertEqual(first.counts(), second.counts())
        self.assertEqual(first.grass.ready, second.grass.ready)
        self.assertEqual(first.grass.growth, second.grass.growth)
        self.assertEqual(
            [(animal.x, animal.y, animal.hungry_for) for animal in first.animals],
            [(animal.x, animal.y, animal.hungry_for) for animal in second.animals],
        )
