# Proof — t-0123456789ab

**Run** `r-20260101T000000-abcdef` · **Flow** `fix-issue` · **Product** `openjiuwen`

**Source** `manual:GH-1` · **Base commit** `abc1234`

**State** `proved` · **Stop reason** `completed`

**Proof SHA-256** `afd3423d2ce558d7ae5fe08a45bc3098e57dd69d817ba022e24d25a733345d41`

## Verdict

**ALLOW** — all P0 passed; P1 pass rate 100%.

| Scenario | Priority | Result | Exit | Duration (ms) |
|---|---|---|---|---|
| `add-negative` | P0 | PASS | 0 | 90 |
| `add-positive` | P0 | PASS | 0 | 80 |
| `mul-positive` | P1 | PASS | 0 | 70 |

## Findings

| Step | Finding | Confidence | Remaining uncertainty |
|---|---|---|---|
| build | add subtracted instead of adding | 0.95 | none observed |

## Challenge

**ALLOW** — the change is the smallest one that explains the defect.

| Concern |
|---|
| no stress test for integer overflow |

Model `fake-challenger-1` · provider `fixture` · prompt `eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee`.

## Residual risk

- Not tested: `Windows-specific path handling`

## Commands

| Step | Command | Exit | Duration (ms) | Output SHA-256 |
|---|---|---|---|---|
| reproduce | `python -m pytest -q` | 1 | 180 | `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` |
| test | `python -m pytest -q` | 0 | 240 | `eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` |

_Reproduction must fail on the base commit; the test step must pass after the change._

## Change

| File | + | - |
|---|---|---|
| `calc/core.py` | 1 | 1 |

Files changed: **1**.

## Policy

No violations.

## Cost

- tokens: `1200`
- usd: `0.0120`
- wall: `4321 ms`
- model: `fake-builder-1` · provider: `fixture`
- prompt: `build` · sha256: `ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff`

## Diff

```diff
diff --git a/calc/core.py b/calc/core.py
--- a/calc/core.py
+++ b/calc/core.py
@@ -4,2 +4,2 @@
 def add(a: int, b: int) -> int:
-    return a - b
+    return a + b
```
