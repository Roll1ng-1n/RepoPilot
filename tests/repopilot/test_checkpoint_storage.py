from __future__ import annotations

import json

import pytest

from repopilot import checkpoint_storage
from repopilot.artifacts import RunArtifacts


def checkpoint(text):
    return {
        "schema_version": 2,
        "status": "RUNNING",
        "messages": [{"role": "tool", "content": text}],
        "tool_results": [{"output": text}],
    }


def test_schema3_redacts_and_reuses_immutable_objects_without_losing_history(tmp_path):
    artifacts = RunArtifacts(tmp_path / "runs", secrets=["secret-fixture"])
    text = "secret-fixture 中文\n" * 4000
    value = checkpoint(text)
    artifacts.write_checkpoint(value)
    physical = json.loads((artifacts.path / "checkpoint.json").read_text())
    assert physical["schema_version"] == 3
    assert len(physical["content_objects"]) == 2
    objects = list((artifacts.path / "objects").iterdir())
    assert len(objects) == 1
    assert "secret-fixture" not in objects[0].read_text()
    inode = objects[0].stat().st_ino
    artifacts.write_checkpoint(value)
    assert objects[0].stat().st_ino == inode
    reopened = RunArtifacts.reopen(tmp_path / "runs", artifacts.run_id, secrets=[])
    loaded = reopened.read_checkpoint()
    assert loaded["messages"][0]["content"] == text.replace("secret-fixture", "[REDACTED]")
    assert loaded["tool_results"][0]["output"] == loaded["messages"][0]["content"]
    # A changed mutable container gets a new object even when the old string is cached.
    value["messages"][0]["content"] += "changed"
    artifacts.write_checkpoint(value)
    assert len(list((artifacts.path / "objects").iterdir())) == 2
    assert artifacts.read_checkpoint()["messages"][0]["content"].endswith("changed")


@pytest.mark.parametrize("damage", ["missing", "truncated", "modified"])
def test_bad_objects_are_detected_on_read_and_before_replacing_current_checkpoint(tmp_path, damage):
    artifacts = RunArtifacts(tmp_path, secrets=[])
    value = checkpoint("large output" * 4000)
    artifacts.write_checkpoint(value)
    current = (artifacts.path / "checkpoint.json").read_bytes()
    obj = next((artifacts.path / "objects").iterdir())
    if damage == "missing":
        obj.unlink()
    elif damage == "truncated":
        obj.write_bytes(obj.read_bytes()[:-1])
    else:
        obj.write_bytes(b"X" + obj.read_bytes()[1:])
    with pytest.raises(ValueError, match="missing|checksum"):
        artifacts.read_checkpoint()
    with pytest.raises(ValueError, match="missing|checksum"):
        artifacts.write_checkpoint(value)
    assert (artifacts.path / "checkpoint.json").read_bytes() == current


def test_partial_object_and_interrupted_checkpoint_publication_keep_previous_state(tmp_path, monkeypatch):
    artifacts = RunArtifacts(tmp_path, secrets=[])
    artifacts.write_checkpoint(checkpoint("old"))
    current = (artifacts.path / "checkpoint.json").read_bytes()
    original = checkpoint_storage.atomic_write

    def partial(destination, payload):
        if destination.suffix == ".utf8":
            destination.write_bytes(payload[:-1])
        else:
            original(destination, payload)

    monkeypatch.setattr(checkpoint_storage, "atomic_write", partial)
    with pytest.raises(ValueError, match="checksum"):
        artifacts.write_checkpoint(checkpoint("new" * 20000))
    assert (artifacts.path / "checkpoint.json").read_bytes() == current

    monkeypatch.setattr(checkpoint_storage, "atomic_write", original)
    import repopilot.artifacts as module

    def interrupted(destination, payload):
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "atomic_write", interrupted)
    with pytest.raises(KeyboardInterrupt):
        artifacts.write_checkpoint(checkpoint("different" * 20000))
    assert (artifacts.path / "checkpoint.json").read_bytes() == current
    assert artifacts.read_checkpoint()["messages"][0]["content"] == "old"


@pytest.mark.parametrize("schema", [1, 2])
def test_old_checkpoint_schemas_remain_readable(tmp_path, schema):
    artifacts = RunArtifacts(tmp_path, secrets=[])
    value = {**checkpoint("complete old history"), "schema_version": schema}
    (artifacts.path / "checkpoint.json").write_text(json.dumps(value))
    assert artifacts.read_checkpoint() == value


def test_modified_manifest_cannot_replace_existing_fields_or_escape_object_directory(tmp_path):
    artifacts = RunArtifacts(tmp_path, secrets=[])
    artifacts.write_checkpoint(checkpoint("x" * 20000))
    path = artifacts.path / "checkpoint.json"
    value = json.loads(path.read_text())
    value["content_objects"][0]["path"] = ["status"]
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="placeholder"):
        artifacts.read_checkpoint()
    value["content_objects"][0]["sha256"] = "../../outside"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="reference"):
        artifacts.read_checkpoint()


def test_replaced_object_directory_is_rejected_for_reads_and_cached_writes(tmp_path):
    artifacts = RunArtifacts(tmp_path, secrets=[])
    value = checkpoint("x" * 20000)
    artifacts.write_checkpoint(value)
    current = (artifacts.path / "checkpoint.json").read_bytes()
    objects = artifacts.path / "objects"
    moved = artifacts.path / "moved-objects"
    objects.rename(moved)
    objects.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        artifacts.read_checkpoint()
    with pytest.raises(ValueError, match="symlink"):
        artifacts.write_checkpoint(value)
    assert (artifacts.path / "checkpoint.json").read_bytes() == current
