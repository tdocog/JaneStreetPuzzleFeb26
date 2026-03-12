from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

Cell = tuple[int, int]
Region = frozenset[Cell]
ForcedEntry = tuple[int, int, int]


def triangular(n: int) -> int:
    return n * (n + 1) // 2


def neighbors(cell: Cell, rows: int, cols: int):
    r, c = cell
    if r > 0:
        yield (r - 1, c)
    if r + 1 < rows:
        yield (r + 1, c)
    if c > 0:
        yield (r, c - 1)
    if c + 1 < cols:
        yield (r, c + 1)


def normalize(points) -> tuple[Cell, ...]:
    pts = list(points)
    min_r = min(r for r, _ in pts)
    min_c = min(c for _, c in pts)
    return tuple(sorted((r - min_r, c - min_c) for r, c in pts))


def all_transforms(points) -> list[tuple[Cell, ...]]:
    pts = list(points)
    transformed = set()
    fns = (
        lambda r, c: (r, c),
        lambda r, c: (r, -c),
        lambda r, c: (-r, c),
        lambda r, c: (-r, -c),
        lambda r, c: (c, r),
        lambda r, c: (c, -r),
        lambda r, c: (-c, r),
        lambda r, c: (-c, -r),
    )
    for fn in fns:
        transformed.add(normalize(fn(r, c) for r, c in pts))
    return sorted(transformed)


@dataclass
class Puzzle:
    rows: int
    cols: int
    fixed_values: dict[Cell, int]


class SubtilesNotebookSolver:
    def __init__(self, puzzle: Puzzle):
        self.puzzle = puzzle
        self.fixed_by_k = defaultdict(set)
        for cell, value in puzzle.fixed_values.items():
            self.fixed_by_k[value].add(cell)

        ordered_cells = [(r, c) for r in range(puzzle.rows) for c in range(puzzle.cols)]
        self.cell_to_bit = {cell: (1 << i) for i, cell in enumerate(ordered_cells)}
        self.bit_to_cell = {bit: cell for cell, bit in self.cell_to_bit.items()}

        self.allowed_cells_cache = {}
        self.allowed_mask_cache = {}
        self.region_mask_cache = {}
        self.raw_frontier_cache = {}
        self.raw_frontier_mask_cache = {}
        self.canonical_shape_cache = {}
        self.transforms_cache = {}
        self.placement_cache = {}
        self.has_candidate_cache = {}

        self.stats = {}

    def allowed_cells_for_k(self, k: int) -> set[Cell]:
        if k in self.allowed_cells_cache:
            return self.allowed_cells_cache[k]
        allowed = {
            cell
            for cell in self.cell_to_bit
            if self.puzzle.fixed_values.get(cell) in (None, k)
        }
        self.allowed_cells_cache[k] = allowed
        return allowed

    def allowed_mask_for_k(self, k: int) -> int:
        if k in self.allowed_mask_cache:
            return self.allowed_mask_cache[k]
        mask = 0
        for cell in self.allowed_cells_for_k(k):
            mask |= self.cell_to_bit[cell]
        self.allowed_mask_cache[k] = mask
        return mask

    def region_mask(self, region: Region) -> int:
        if region in self.region_mask_cache:
            return self.region_mask_cache[region]
        mask = 0
        for cell in region:
            mask |= self.cell_to_bit[cell]
        self.region_mask_cache[region] = mask
        return mask

    def raw_frontier(self, region: Region) -> set[Cell]:
        if region in self.raw_frontier_cache:
            return self.raw_frontier_cache[region]
        out = set()
        for cell in region:
            for nb in neighbors(cell, self.puzzle.rows, self.puzzle.cols):
                if nb not in region:
                    out.add(nb)
        self.raw_frontier_cache[region] = out
        return out

    def raw_frontier_mask(self, region: Region) -> int:
        if region in self.raw_frontier_mask_cache:
            return self.raw_frontier_mask_cache[region]
        mask = 0
        for cell in self.raw_frontier(region):
            mask |= self.cell_to_bit[cell]
        self.raw_frontier_mask_cache[region] = mask
        return mask

    def canonical_shape(self, region: Region) -> tuple[Cell, ...]:
        if region in self.canonical_shape_cache:
            return self.canonical_shape_cache[region]
        canonical = min(all_transforms(region))
        self.canonical_shape_cache[region] = canonical
        return canonical

    def transforms_for_shape(self, canonical_shape: tuple[Cell, ...]) -> list[tuple[Cell, ...]]:
        if canonical_shape in self.transforms_cache:
            return self.transforms_cache[canonical_shape]
        out = all_transforms(canonical_shape)
        self.transforms_cache[canonical_shape] = out
        return out

    def candidate_translations(self, transform: tuple[Cell, ...], required: set[Cell]):
        max_r = max(r for r, _ in transform)
        max_c = max(c for _, c in transform)
        min_dr, max_dr = 0, self.puzzle.rows - 1 - max_r
        min_dc, max_dc = 0, self.puzzle.cols - 1 - max_c

        if max_dr < min_dr or max_dc < min_dc:
            return set()

        if not required:
            return {
                (dr, dc)
                for dr in range(min_dr, max_dr + 1)
                for dc in range(min_dc, max_dc + 1)
            }

        if len(required) == 1:
            req = next(iter(required))
            anchors = {req, *neighbors(req, self.puzzle.rows, self.puzzle.cols)}
            shifts = set()
            for anchor_r, anchor_c in anchors:
                for shape_r, shape_c in transform:
                    dr = anchor_r - shape_r
                    dc = anchor_c - shape_c
                    if min_dr <= dr <= max_dr and min_dc <= dc <= max_dc:
                        shifts.add((dr, dc))
            return shifts

        threshold = max(0, len(required) - 1)
        hit_counts = {}
        for req_r, req_c in required:
            for shape_r, shape_c in transform:
                dr = req_r - shape_r
                dc = req_c - shape_c
                if dr < min_dr or dr > max_dr or dc < min_dc or dc > max_dc:
                    continue
                key = (dr, dc)
                hit_counts[key] = hit_counts.get(key, 0) + 1

        return {shift for shift, count in hit_counts.items() if count >= threshold}

    def placements_of_shape(self, shape: Region, k: int, required: set[Cell]) -> list[Region]:
        canonical = self.canonical_shape(shape)
        key = (k, canonical)
        if key in self.placement_cache:
            return self.placement_cache[key]

        allowed = self.allowed_cells_for_k(k)
        seen = set()
        for transform in self.transforms_for_shape(canonical):
            for dr, dc in self.candidate_translations(transform, required):
                placed = frozenset((r + dr, c + dc) for r, c in transform)
                if placed in seen:
                    continue
                if all(cell in allowed for cell in placed):
                    seen.add(placed)

        placements = sorted(seen, key=lambda region: tuple(sorted(region)))
        self.placement_cache[key] = placements
        return placements

    def generate_candidates(self, k: int, prev_region: Region | None, used_mask: int) -> list[Region]:
        required = self.fixed_by_k.get(k, set())

        if k == 1:
            if len(required) > 1:
                return []
            if len(required) == 1:
                only = next(iter(required))
                if (self.cell_to_bit[only] & used_mask) == 0 and only in self.allowed_cells_for_k(1):
                    return [frozenset({only})]
                return []
            return [
                frozenset({cell})
                for cell in self.allowed_cells_for_k(1)
                if (self.cell_to_bit[cell] & used_mask) == 0
            ]

        if prev_region is None:
            return []

        allowed_mask = self.allowed_mask_for_k(k)
        required_bits = {cell: self.cell_to_bit[cell] for cell in required}
        candidates = set()

        for placed_prev in self.placements_of_shape(prev_region, k, required):
            placed_mask = self.region_mask(placed_prev)
            if placed_mask & used_mask:
                continue

            missing = required - placed_prev
            if len(missing) > 1:
                continue

            frontier_mask = self.raw_frontier_mask(placed_prev) & allowed_mask & ~used_mask
            if frontier_mask == 0:
                continue

            if len(missing) == 1:
                needed = next(iter(missing))
                needed_bit = required_bits[needed]
                if frontier_mask & needed_bit:
                    candidates.add(placed_prev | {needed})
                continue

            mask = frontier_mask
            while mask:
                lsb = mask & -mask
                candidates.add(placed_prev | {self.bit_to_cell[lsb]})
                mask ^= lsb

        return sorted(candidates, key=lambda region: tuple(sorted(region)))

    def has_candidate(self, k: int, prev_region: Region, used_mask: int) -> bool:
        key = (k, self.canonical_shape(prev_region), used_mask)
        if key in self.has_candidate_cache:
            return self.has_candidate_cache[key]
        answer = bool(self.generate_candidates(k, prev_region, used_mask))
        self.has_candidate_cache[key] = answer
        return answer

    def remaining_capacity_ok(self, used_count: int, k: int, n: int) -> bool:
        remaining_cells = self.puzzle.rows * self.puzzle.cols - used_count
        needed = triangular(n) - triangular(k)
        return remaining_cells >= needed

    def solve(self, n: int, max_nodes: int = 5_000_000, timeout_s: float = 30.0) -> dict[int, Region]:
        if triangular(n) > self.puzzle.rows * self.puzzle.cols:
            raise ValueError(f"N={n} does not fit in grid.")
        if any(value > n for value in self.fixed_by_k):
            raise ValueError("Fixed clues contain values above N.")
        if any(len(self.fixed_by_k.get(k, set())) > k for k in range(1, n + 1)):
            raise ValueError("Fixed clues violate count constraints.")

        placed = {}
        started = time.time()
        nodes = 0

        def dfs(k: int, prev_region: Region | None, used_mask: int, used_count: int) -> bool:
            nonlocal nodes
            nodes += 1
            if nodes > max_nodes:
                return False
            if (time.time() - started) > timeout_s:
                return False
            if k > n:
                return True

            for region in self.generate_candidates(k, prev_region, used_mask):
                region_mask = self.region_mask(region)
                next_used_mask = used_mask | region_mask
                next_used_count = used_count + k
                placed[k] = region

                if not self.remaining_capacity_ok(next_used_count, k, n):
                    del placed[k]
                    continue

                if k < n and not self.has_candidate(k + 1, region, next_used_mask):
                    del placed[k]
                    continue

                if dfs(k + 1, region, next_used_mask, next_used_count):
                    return True

                del placed[k]

            return False

        ok = dfs(1, None, 0, 0)
        self.stats = {"nodes": nodes, "seconds": time.time() - started}

        if not ok:
            raise ValueError("No solution found within limits.")
        return placed


def _grid_shape(clues) -> tuple[int, int]:
    if hasattr(clues, "shape"):
        rows, cols = clues.shape
        return int(rows), int(cols)
    rows = len(clues)
    cols = len(clues[0]) if rows else 0
    return rows, cols


def build_fixed_values(clues, forced_list: Sequence[ForcedEntry]) -> dict[Cell, int]:
    rows, cols = _grid_shape(clues)
    fixed: dict[Cell, int] = {}

    for r in range(rows):
        for c in range(cols):
            value = int(clues[r][c])
            if value > 0:
                fixed[(r, c)] = value

    for r, c, value in forced_list:
        existing = fixed.get((r, c))
        if existing is not None and existing != value:
            raise ValueError(f"Conflict at {(r, c)}: {existing} vs {value}")
        fixed[(r, c)] = int(value)

    return fixed


def can_solve_with(
    clues,
    forced_list: Sequence[ForcedEntry],
    n: int,
    max_nodes: int = 3000,
    timeout_s: float = 0.6,
):
    rows, cols = _grid_shape(clues)
    solver = SubtilesNotebookSolver(Puzzle(rows, cols, build_fixed_values(clues, forced_list)))
    try:
        solver.solve(n, max_nodes=max_nodes, timeout_s=timeout_s)
        return True, solver.stats
    except ValueError:
        return False, solver.stats


def discover_forced_subset(
    clues,
    candidates: Sequence[ForcedEntry],
    n: int,
    max_nodes: int = 3000,
    timeout_s: float = 0.6,
):
    selected = list(candidates)
    ok, _ = can_solve_with(clues, selected, n, max_nodes=max_nodes, timeout_s=timeout_s)
    if not ok:
        raise ValueError("Candidate scaffold does not solve under discovery budget.")

    removed: list[ForcedEntry] = []
    for item in list(candidates):
        trial = [x for x in selected if x != item]
        ok, _ = can_solve_with(clues, trial, n, max_nodes=max_nodes, timeout_s=timeout_s)
        if ok:
            selected = trial
            removed.append(item)

    return selected, removed


def render_solution(rows: int, cols: int, placed: dict[int, Region]) -> list[list[int]]:
    grid = [[0 for _ in range(cols)] for _ in range(rows)]
    for value, region in placed.items():
        for r, c in region:
            grid[r][c] = value
    return grid


__all__ = [
    "Cell",
    "Region",
    "ForcedEntry",
    "Puzzle",
    "SubtilesNotebookSolver",
    "triangular",
    "neighbors",
    "normalize",
    "all_transforms",
    "build_fixed_values",
    "can_solve_with",
    "discover_forced_subset",
    "render_solution",
]
