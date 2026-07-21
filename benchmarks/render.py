"""Measure Tk Canvas rendering under a repeatable maximum-load scene.

Run with ``uv run python -m benchmarks.render``. The benchmark measures only
the renderer: animal movement and grass growth are prepared outside the timed
section so simulation AI does not affect the numbers.
"""

from __future__ import annotations

import argparse
import math
import statistics
import time
import tkinter as tk
from dataclasses import dataclass

from ecosystem.settings import GameSettings
from ecosystem.simulation import Simulation
from ecosystem.ui.renderer import CanvasRenderer

BENCHMARK_COLUMNS = 100
BENCHMARK_ROWS = 70
BENCHMARK_HERBIVORES = 300
BENCHMARK_PREDATORS = 150
BENCHMARK_CELL_SIZE = 6
FRAME_DT = 0.025
DEFAULT_FRAMES = 240
DEFAULT_GROWING_CELLS = 1_400
WARMUP_FRAMES = 20


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    initial_draw_ms: float
    median_draw_ms: float
    p95_draw_ms: float
    median_flush_ms: float
    canvas_items: int


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = math.ceil(percentile * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _growing_cells(simulation: Simulation, count: int) -> list[tuple[int, int]]:
    cells = [
        (column, row) for row in range(simulation.rows) for column in range(simulation.columns)
    ]
    selected = cells[:count]
    for cell in selected:
        simulation.grass.consume(cell)
    return selected


def _advance_scene(
    simulation: Simulation,
    growing_cells: list[tuple[int, int]],
    frame: int,
) -> None:
    for index, animal in enumerate(simulation.animals):
        animal.x = 0.5 + (index * 7 + frame * 0.8) % (simulation.columns - 1)
        animal.y = 0.5 + (index * 11 + frame * 0.6) % (simulation.rows - 1)

    simulation.grass.tick(FRAME_DT, regrowth_seconds=1.0)
    for cell in growing_cells:
        if simulation.grass.is_ready(cell):
            simulation.grass.consume(cell)


def _draw_frame(root: tk.Tk, renderer: CanvasRenderer) -> tuple[float, float]:
    started = time.perf_counter()
    renderer.draw()
    draw_ms = (time.perf_counter() - started) * 1_000
    started = time.perf_counter()
    root.update_idletasks()
    flush_ms = (time.perf_counter() - started) * 1_000
    return draw_ms, flush_ms


def run_benchmark(
    *, frames: int = DEFAULT_FRAMES, growing_cells: int = DEFAULT_GROWING_CELLS, show: bool = False
) -> BenchmarkResult:
    """Run a local Canvas benchmark and return timing statistics in milliseconds."""
    if frames < 1:
        raise ValueError("frames must be at least 1")
    maximum_cells = BENCHMARK_COLUMNS * BENCHMARK_ROWS
    if not 0 <= growing_cells <= maximum_cells:
        raise ValueError(f"growing_cells must be between 0 and {maximum_cells}")

    root = tk.Tk()
    try:
        root.title("Pixel Ecosystem render benchmark")
        if not show:
            root.withdraw()
        simulation = Simulation(
            GameSettings(
                columns=BENCHMARK_COLUMNS,
                rows=BENCHMARK_ROWS,
                herbivores=BENCHMARK_HERBIVORES,
                predators=BENCHMARK_PREDATORS,
            )
        )
        canvas = tk.Canvas(
            root,
            width=BENCHMARK_COLUMNS * BENCHMARK_CELL_SIZE,
            height=BENCHMARK_ROWS * BENCHMARK_CELL_SIZE,
            highlightthickness=0,
        )
        canvas.pack()
        renderer = CanvasRenderer(canvas, simulation, BENCHMARK_CELL_SIZE)
        active_cells = _growing_cells(simulation, growing_cells)
        initial_draw_ms, _ = _draw_frame(root, renderer)

        for frame in range(WARMUP_FRAMES):
            _advance_scene(simulation, active_cells, frame)
            _draw_frame(root, renderer)

        draw_samples: list[float] = []
        flush_samples: list[float] = []
        for frame in range(frames):
            _advance_scene(simulation, active_cells, frame + WARMUP_FRAMES)
            draw_ms, flush_ms = _draw_frame(root, renderer)
            draw_samples.append(draw_ms)
            flush_samples.append(flush_ms)

        return BenchmarkResult(
            initial_draw_ms=initial_draw_ms,
            median_draw_ms=statistics.median(draw_samples),
            p95_draw_ms=_percentile(draw_samples, 0.95),
            median_flush_ms=statistics.median(flush_samples),
            canvas_items=len(canvas.find_all()),
        )
    finally:
        root.destroy()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure Pixel Ecosystem Tk Canvas render time.")
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES, help="Measured frames")
    parser.add_argument(
        "--growing-cells",
        type=int,
        default=DEFAULT_GROWING_CELLS,
        help="Number of simultaneously regrowing cells",
    )
    parser.add_argument("--show", action="store_true", help="Show the benchmark window")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        result = run_benchmark(
            frames=args.frames,
            growing_cells=args.growing_cells,
            show=args.show,
        )
    except tk.TclError as error:
        raise SystemExit("Tkinter requires a desktop display to run this benchmark.") from error

    print("Tk Canvas render benchmark")
    print(
        f"Scene: {BENCHMARK_COLUMNS}×{BENCHMARK_ROWS}, "
        f"{BENCHMARK_HERBIVORES} herbivores, {BENCHMARK_PREDATORS} predators, "
        f"{args.growing_cells} regrowing cells"
    )
    print(f"Initial draw: {result.initial_draw_ms:.2f} ms")
    print(f"Draw median / p95: {result.median_draw_ms:.2f} / {result.p95_draw_ms:.2f} ms")
    print(f"Tk flush median: {result.median_flush_ms:.2f} ms")
    print(f"Canvas items after benchmark: {result.canvas_items}")


if __name__ == "__main__":
    main()
