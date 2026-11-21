# Proof — t-0123456789ab

**Run** `r-20260101T000000-abcdef` · **Flow** `fix-issue` · **Product** `openjiuwen`

**Source** `manual:GH-1` · **Base commit** `abc1234`

**State** `proved` · **Stop reason** `completed`

**Proof SHA-256** `017754fd09b5b0846077a552a5f06b4809cff12bffc6c5cbba25b2282d286340`

## Verdict

**ALLOW** — all P0 passed; P1 pass rate 100%.

| Scenario | Priority | Result | Exit | Duration (ms) |
|---|---|---|---|---|
| `add-negative` | P0 | PASS | 0 | 90 |
| `add-positive` | P0 | PASS | 0 | 80 |
| `mul-positive` | P1 | PASS | 0 | 70 |

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
