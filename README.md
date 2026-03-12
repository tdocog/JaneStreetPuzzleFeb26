# Feb2026: Subtiles 2 Walkthrough

Puzzle link (official solution page):  
https://www.janestreet.com/puzzles/subtiles-2-solution/

## TL;DR
- Fill some cells with positive integers so the grid has one `1`, two `2`s, ..., up to `N` copies of `N`.
- For each value `k`, all `k` cells must form one orthogonally connected region.
- For `k > 1`, the `k`-region must contain the `(k-1)` shape (up to rotation/reflection).
- After solving, compute each row sum and return:  
  **`min(row sums) * max(row sums)`**.

## Repo Navigation
- [refactored.ipynb](/home/jdoco/projects/puzzles/Feb2026/refactored.ipynb): end-to-end walkthrough (visuals, forced-cell discovery, solve, final answer).
- [solver.py](/home/jdoco/projects/puzzles/Feb2026/solver.py): solver logic and helper functions used by the notebook.
- [image.png](/home/jdoco/projects/puzzles/Feb2026/image.png): puzzle image used in the notebook.

## Quick Use
1. Open `refactored.ipynb`.
2. Run cells top-to-bottom.
3. If you want to change search/solver behavior, edit `solver.py` and rerun notebook cells.
