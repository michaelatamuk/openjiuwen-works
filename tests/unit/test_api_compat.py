from __future__ import annotations

from scripts.check_api_compat import compare


def schema(**paths: dict[str, object]) -> dict[str, object]:
    return {"paths": paths}


def with_schema(name: str, properties: dict[str, object], required: list[str]) -> dict[str, object]:
    return {
        "paths": {},
        "components": {
            "schemas": {name: {"type": "object", "properties": properties, "required": required}}
        },
    }


def test_removing_an_operation_is_breaking() -> None:
    baseline = schema(**{"/tasks": {"get": {}}})
    current = schema()
    assert compare(baseline, current) == ["removed operation GET /tasks"]


def test_adding_an_operation_is_fine() -> None:
    baseline = schema()
    current = schema(**{"/tasks": {"get": {}}})
    assert compare(baseline, current) == []


def test_removing_a_parameter_is_breaking() -> None:
    baseline = schema(**{"/tasks": {"get": {"parameters": [{"name": "limit"}]}}})
    current = schema(**{"/tasks": {"get": {"parameters": []}}})
    assert compare(baseline, current) == ["GET /tasks: parameter limit removed"]


def test_a_new_required_field_is_breaking() -> None:
    baseline = with_schema("Task", {"id": {"type": "string"}}, ["id"])
    current = with_schema(
        "Task", {"id": {"type": "string"}, "state": {"type": "string"}}, ["id", "state"]
    )
    assert compare(baseline, current) == ["Task.state became required"]


def test_a_removed_property_and_a_changed_type_are_breaking() -> None:
    baseline = with_schema("Task", {"id": {"type": "string"}, "risk": {"type": "string"}}, ["id"])
    current = with_schema("Task", {"id": {"type": "integer"}}, ["id"])
    assert compare(baseline, current) == [
        "Task.id type string -> integer",
        "Task.risk removed",
    ]
