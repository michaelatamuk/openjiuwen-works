from __future__ import annotations

from scripts.dump_route_classes import app_routes, problems

from works.interfaces.api.route_classes import ROUTE_CLASSES

VALID = {"async-safe", "blocking", "subprocess", "sse"}


def test_every_route_is_classified() -> None:
    routes = app_routes()

    assert len(routes) >= 30
    assert problems(routes) == []


def test_every_class_and_note_is_filled() -> None:
    for key, (route_class, note) in ROUTE_CLASSES.items():
        assert route_class in VALID, key
        assert note.strip(), key
