from __future__ import annotations

from types import SimpleNamespace

from works.harness.usage import UsageTotals


def test_provider_usage_events_are_summed() -> None:
    totals = UsageTotals()
    for input_tokens, output_tokens in ((10, 5), (7, 3)):
        totals.add_event(
            SimpleNamespace(
                payload={
                    "usage_metadata": {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                        "total_cost": 0.001,
                    }
                }
            )
        )

    assert totals.tokens == 25
    assert totals.usd == 0.002
    assert totals.calls == 2


def test_result_usage_is_a_fallback_and_never_replaces_the_stream() -> None:
    totals = UsageTotals()
    totals.add_event(
        SimpleNamespace(
            payload={
                "usage_metadata": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
            }
        )
    )
    totals.add_result(
        SimpleNamespace(
            usage=SimpleNamespace(total_tokens=50, input_tokens=40, output_tokens=10),
            cost=SimpleNamespace(micros=2500),
        )
    )

    assert totals.tokens == 120
    assert totals.usd == 0.0025
