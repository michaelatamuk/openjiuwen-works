# Proof — t-0123456789ab

**Run** `r-20260101T000000-abcdef` · **Flow** `fix-issue` · **Product** `openjiuwen`

**Source** `manual:GH-1` · **Base commit** `abc1234`

**Task kind** `fix`

**Next step** read the run log

**Checks SHA-256** `—`

**State** `proved` · **Stop reason** `completed`

**Proof SHA-256** `8f3723277c035cfb6965808bb1a6b1aaafce5e18b37a5e0896d8fefa7dbaeaab`

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

## Feature coverage

No feature map was recorded for this proof.

## Artifacts

No runtime artifacts were attached.

## Memory recall

No memory recall was recorded.

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
- build attempts: `1`
- model: `fake-builder-1` · provider: `fixture`
- engine: `native`
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
