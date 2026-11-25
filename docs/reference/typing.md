# Typing

`py.typed` ships in the wheel and mypy runs in `--strict` mode over `src` on every push. That is the
baseline; this page covers the one thing strict mode cannot enforce on its own: explicit `Any`.

## The Any ratchet

Adapter boundaries (provider SDKs, `openjiuwen`, JSON payloads) still need a bounded amount of `Any`.
Removing all of it in one change would be a rewrite, so the gate records the current count per file:

```bash
python scripts/check_typing_ratchet.py           # compare
python scripts/check_typing_ratchet.py --update  # only after removing Any on purpose
```

It runs mypy with `--disallow-any-explicit --warn-return-any` and compares the `[explicit-any]` and
`[no-any-return]` errors with `docs/reference/typing-baseline.json`. A file or the total may shrink;
growth fails the build. New files start at zero.

## Changing the baseline

`--update` is a reviewed act, like changing a test: it belongs in the same commit that removes or
adds `Any`, and the diff should show the number going down. The gate exists so "temporary" `Any`
does not become permanent by accident.

## Not doing

No second type checker. pyright/ty would duplicate mypy and produce two opinions about the same code.
