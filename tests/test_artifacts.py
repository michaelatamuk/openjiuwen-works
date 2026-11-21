from __future__ import annotations

import hashlib

from works.artifacts import collect_artifacts


def test_preview_artifacts_are_copied_and_classified(tmp_path) -> None:
    source = tmp_path / "preview"
    source.mkdir()
    (source / "story.png").write_bytes(b"png")
    (source / "run.log").write_text("ok\n", encoding="utf-8")
    (source / "clip.mp4").write_bytes(b"mp4")
    (source / "nested").mkdir()
    (source / "nested" / "trace.json").write_text("{}", encoding="utf-8")

    destination = tmp_path / "run" / "artifacts"
    artifacts = collect_artifacts(source, destination)

    assert [item.kind for item in artifacts] == ["video", "trace", "log", "screenshot"]
    assert [item.path for item in artifacts] == [
        "artifacts/clip.mp4",
        "artifacts/nested/trace.json",
        "artifacts/run.log",
        "artifacts/story.png",
    ]
    assert (destination / "nested" / "trace.json").exists()
    expected = hashlib.sha256(b"png").hexdigest()
    assert next(item for item in artifacts if item.kind == "screenshot").sha256 == expected


def test_a_missing_preview_tree_is_empty(tmp_path) -> None:
    assert collect_artifacts(tmp_path / "absent", tmp_path / "dest") == []
