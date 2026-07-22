"""Compare indexed target lookup with an exact full-scan reference search.

Run with ``uv run python -m benchmarks.target_search``. The benchmark does not
advance the simulation, so it measures only the work of finding five nearest
grass cells or herbivores.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import time
from dataclasses import dataclass
from heapq import nsmallest
from typing import Callable, Iterable, TypeVar

from ecosystem.animals import Herbivore
from ecosystem.settings import GameSettings
from ecosystem.simulation import Simulation

Target = TypeVar("Target")

BENCHMARK_COLUMNS = 100
BENCHMARK_ROWS = 70
BENCHMARK_HERBIVORES = 300
BENCHMARK_PREDATORS = 150
DEFAULT_ROUNDS = 5
NEAREST_COUNT = 5


@dataclass(frozen=True, slots=True)
class SearchBatch:
    elapsed_ms: float
    candidates_examined: int


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    reference_median_ms: float
    reference_p95_ms: float
    indexed_median_ms: float
    indexed_p95_ms: float
    reference_candidates_per_query: float
    indexed_candidates_per_query: float


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = math.ceil(percentile * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _reference_nearest(
    x: float,
    y: float,
    candidates: Iterable[Target],
    *,
    position: Callable[[Target], tuple[float, float]],
    tie_breaker: Callable[[Target], object],
) -> list[tuple[float, Target]]:
    return nsmallest(
        NEAREST_COUNT,
        (
            (math.hypot(candidate_x - x, candidate_y - y), candidate)
            for candidate in candidates
            for candidate_x, candidate_y in (position(candidate),)
        ),
        key=lambda result: (result[0], tie_breaker(result[1])),
    )


def _create_simulation() -> Simulation:
    return Simulation(
        GameSettings(
            columns=BENCHMARK_COLUMNS,
            rows=BENCHMARK_ROWS,
            herbivores=BENCHMARK_HERBIVORES,
            predators=BENCHMARK_PREDATORS,
            grass_regrowth=30.0,
            herbivore_reproduction=0.1,
            predator_reproduction=0.1,
            herbivore_speed=0.5,
            predator_speed=0.5,
        ),
        rng=random.Random(20_260_721),
    )


def _verify_exact_results(
    simulation: Simulation,
    grass_cells: tuple[tuple[int, int], ...],
    herbivores: tuple[Herbivore, ...],
) -> None:
    for herbivore in herbivores:
        indexed = simulation.grass_index.nearest(
            herbivore.x,
            herbivore.y,
            count=NEAREST_COUNT,
            tie_breaker=lambda cell: cell,
        ).nearest
        reference = _reference_nearest(
            herbivore.x,
            herbivore.y,
            grass_cells,
            position=lambda cell: (cell[0] + 0.5, cell[1] + 0.5),
            tie_breaker=lambda cell: cell,
        )
        if indexed != reference:
            raise AssertionError("grass index returned different nearest cells")

    for predator in simulation.predators:
        indexed = simulation.herbivore_index.nearest(
            predator.x,
            predator.y,
            count=NEAREST_COUNT,
            tie_breaker=lambda herbivore: herbivore.entity_id,
        ).nearest
        reference = _reference_nearest(
            predator.x,
            predator.y,
            herbivores,
            position=lambda herbivore: (herbivore.x, herbivore.y),
            tie_breaker=lambda herbivore: herbivore.entity_id,
        )
        if indexed != reference:
            raise AssertionError("herbivore index returned different nearest targets")


def _measure_reference(
    simulation: Simulation,
    grass_cells: tuple[tuple[int, int], ...],
    herbivores: tuple[Herbivore, ...],
) -> SearchBatch:
    started = time.perf_counter()
    candidates_examined = 0
    for herbivore in herbivores:
        _reference_nearest(
            herbivore.x,
            herbivore.y,
            grass_cells,
            position=lambda cell: (cell[0] + 0.5, cell[1] + 0.5),
            tie_breaker=lambda cell: cell,
        )
        candidates_examined += len(grass_cells)
    for predator in simulation.predators:
        _reference_nearest(
            predator.x,
            predator.y,
            herbivores,
            position=lambda herbivore: (herbivore.x, herbivore.y),
            tie_breaker=lambda herbivore: herbivore.entity_id,
        )
        candidates_examined += len(herbivores)
    return SearchBatch((time.perf_counter() - started) * 1_000, candidates_examined)


def _measure_indexed(simulation: Simulation, herbivores: tuple[Herbivore, ...]) -> SearchBatch:
    started = time.perf_counter()
    candidates_examined = 0
    for herbivore in herbivores:
        query = simulation.grass_index.nearest(
            herbivore.x,
            herbivore.y,
            count=NEAREST_COUNT,
            tie_breaker=lambda cell: cell,
        )
        candidates_examined += query.candidates_examined
    for predator in simulation.predators:
        query = simulation.herbivore_index.nearest(
            predator.x,
            predator.y,
            count=NEAREST_COUNT,
            tie_breaker=lambda herbivore: herbivore.entity_id,
        )
        candidates_examined += query.candidates_examined
    return SearchBatch((time.perf_counter() - started) * 1_000, candidates_examined)


def run_benchmark(*, rounds: int = DEFAULT_ROUNDS) -> BenchmarkResult:
    """Measure an indexed batch and a full-scan batch over the same world state."""
    if rounds < 1:
        raise ValueError("rounds must be at least 1")
    simulation = _create_simulation()
    grass_cells = tuple(simulation.grass.ready)
    herbivores = tuple(simulation.herbivores)
    _verify_exact_results(simulation, grass_cells, herbivores)

    reference_batches = [
        _measure_reference(simulation, grass_cells, herbivores) for _ in range(rounds)
    ]
    indexed_batches = [_measure_indexed(simulation, herbivores) for _ in range(rounds)]
    queries_per_batch = len(herbivores) + len(simulation.predators)

    return BenchmarkResult(
        reference_median_ms=statistics.median(batch.elapsed_ms for batch in reference_batches),
        reference_p95_ms=_percentile([batch.elapsed_ms for batch in reference_batches], 0.95),
        indexed_median_ms=statistics.median(batch.elapsed_ms for batch in indexed_batches),
        indexed_p95_ms=_percentile([batch.elapsed_ms for batch in indexed_batches], 0.95),
        reference_candidates_per_query=(
            reference_batches[0].candidates_examined / queries_per_batch
        ),
        indexed_candidates_per_query=(indexed_batches[0].candidates_examined / queries_per_batch),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Pixel Ecosystem target-search algorithms."
    )
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help="Measured batches")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_benchmark(rounds=args.rounds)
    print("Exact target-search benchmark")
    print(
        f"Scene: {BENCHMARK_COLUMNS}×{BENCHMARK_ROWS}, "
        f"{BENCHMARK_HERBIVORES} herbivores, {BENCHMARK_PREDATORS} predators"
    )
    print(
        "Full scan median / p95: "
        f"{result.reference_median_ms:.2f} / {result.reference_p95_ms:.2f} ms"
    )
    print(
        "Spatial index median / p95: "
        f"{result.indexed_median_ms:.2f} / {result.indexed_p95_ms:.2f} ms"
    )
    print(
        "Candidates per query: "
        f"{result.reference_candidates_per_query:.1f} → "
        f"{result.indexed_candidates_per_query:.1f}"
    )


if __name__ == "__main__":
    main()
