# ADR 021 — React Compiler stays opt-in until it pays for itself

Status: accepted, 2026-11-25.

## Context

M10.4 asks for React Compiler behind a measured build. The compiler can remove hand-written
memoisation, but it also rewrites components and can grow the bundle. "Enable it because it is
modern" is not a measurement.

## Measurement

`scripts/measure_web.py` builds both ways and records size and build time; `web/e2e/perf.spec.ts`
measures the first queue render and fails on a console error. Numbers on this machine:

| Build | Total | JS | Build time | First queue render (3 runs) |
|---|---|---|---|---|
| plain | 552,627 B | 449,184 B | 13.25 s | 609 / 469 / 801 ms |
| compiler | 587,612 B | 484,169 B | 22.28 s | 573 / 674 / 868 ms |

Bundle grows **6.33%** (JS +7.8%), build is ~68% slower, and the render difference is noise: the
medians move in opposite directions by less than the spread. No console errors either way.

## Decision

The compiler is available behind `WORKS_REACT_COMPILER=1` and is **not** part of the default build.
`python scripts/measure_web.py --max-growth 5` fails if a future compiler build grows the bundle past
5%, so re-enabling it needs a fresh measurement, not a config flip.

Revisit when either the bundle overhead drops below 5% or a real interaction benchmark (not first
paint on a seeded queue) shows a repeatable win.
