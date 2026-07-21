"""Exact nearest-neighbour queries over a lightweight spatial hash."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from heapq import heapify, heappop, nsmallest
from typing import Callable, Generic, TypeVar

Item = TypeVar("Item")
Bucket = tuple[int, int]
Position = tuple[float, float]


@dataclass(frozen=True, slots=True)
class NearestQuery(Generic[Item]):
    """The exact nearest items and the work required to find them."""

    nearest: list[tuple[float, Item]]
    buckets_examined: int
    candidates_examined: int


@dataclass(slots=True)
class SpatialIndex(Generic[Item]):
    """Stores moving or static items in square buckets within a bounded world."""

    columns: int
    rows: int
    bucket_size: int
    _buckets: dict[Bucket, set[Item]] = field(default_factory=dict, init=False)
    _locations: dict[Item, Bucket] = field(default_factory=dict, init=False)
    _positions: dict[Item, Position] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.columns < 1 or self.rows < 1 or self.bucket_size < 1:
            raise ValueError("world dimensions and bucket_size must be positive")

    @property
    def item_count(self) -> int:
        return len(self._locations)

    @property
    def bucket_count(self) -> int:
        return len(self._buckets)

    def contains(self, item: Item) -> bool:
        return item in self._locations

    def add(self, item: Item, x: float, y: float) -> None:
        self.update(item, x, y)

    def update(self, item: Item, x: float, y: float) -> None:
        next_bucket = self._bucket_for(x, y)
        previous_bucket = self._locations.get(item)
        self._positions[item] = (x, y)
        if previous_bucket == next_bucket:
            return
        if previous_bucket is not None:
            previous_items = self._buckets[previous_bucket]
            previous_items.remove(item)
            if not previous_items:
                self._buckets.pop(previous_bucket)
        self._locations[item] = next_bucket
        self._buckets.setdefault(next_bucket, set()).add(item)

    def remove(self, item: Item) -> None:
        bucket = self._locations.pop(item, None)
        self._positions.pop(item, None)
        if bucket is None:
            return
        items = self._buckets[bucket]
        items.remove(item)
        if not items:
            self._buckets.pop(bucket)

    def nearest(
        self,
        x: float,
        y: float,
        *,
        count: int,
        tie_breaker: Callable[[Item], object],
    ) -> NearestQuery[Item]:
        """Return the exact closest items without scanning distant buckets."""
        if count < 1 or not self._buckets:
            return NearestQuery([], buckets_examined=0, candidates_examined=0)

        bucket_heap = [
            (self._bucket_lower_bound(x, y, bucket), bucket, items)
            for bucket, items in self._buckets.items()
        ]
        heapify(bucket_heap)
        candidates: list[tuple[float, Item]] = []
        buckets_examined = 0
        candidates_examined = 0

        while bucket_heap:
            _, _, items = heappop(bucket_heap)
            buckets_examined += 1
            for item in items:
                item_x, item_y = self._positions[item]
                candidates.append((math.hypot(item_x - x, item_y - y), item))
                candidates_examined += 1

            if len(candidates) < count:
                continue
            nearest = nsmallest(
                count,
                candidates,
                key=lambda result: (result[0], tie_breaker(result[1])),
            )
            next_lower_bound = bucket_heap[0][0] if bucket_heap else math.inf
            if next_lower_bound > nearest[-1][0]:
                return NearestQuery(nearest, buckets_examined, candidates_examined)

        nearest = nsmallest(
            count,
            candidates,
            key=lambda result: (result[0], tie_breaker(result[1])),
        )
        return NearestQuery(nearest, buckets_examined, candidates_examined)

    def _bucket_for(self, x: float, y: float) -> Bucket:
        column = min(self.columns - 1, max(0, int(x)))
        row = min(self.rows - 1, max(0, int(y)))
        return column // self.bucket_size, row // self.bucket_size

    def _bucket_lower_bound(self, x: float, y: float, bucket: Bucket) -> float:
        bucket_x, bucket_y = bucket
        left = bucket_x * self.bucket_size
        top = bucket_y * self.bucket_size
        right = min(self.columns, left + self.bucket_size)
        bottom = min(self.rows, top + self.bucket_size)
        nearest_x = min(max(x, left), right)
        nearest_y = min(max(y, top), bottom)
        return math.hypot(nearest_x - x, nearest_y - y)
