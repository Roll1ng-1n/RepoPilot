"""Durable, redacted immutable text objects referenced by Checkpoint schema 3."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path


def atomic_write(destination: Path, payload: bytes) -> None:
    descriptor, name = tempfile.mkstemp(dir=destination.parent, prefix=".checkpoint-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, destination)
        sync_directory(destination.parent)
    finally:
        temporary = Path(name)
        if temporary.exists():
            temporary.unlink()


def sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class CheckpointStorage:
    """Only Python strings are cached: immutable content cannot become stale.

    Repository observations are never cached. Every object is verified before
    a new checkpoint references it; publishing the checkpoint is the last step.
    """

    threshold = 16 * 1024

    def __init__(self, artifacts):
        self.artifacts = artifacts
        self.cache = {}

    def _directory(self):
        directory = self.artifacts.path / "objects"
        if directory.is_symlink():
            raise ValueError("Checkpoint object directory must not be a symlink.")
        if not directory.exists():
            directory.mkdir()
            sync_directory(self.artifacts.path)
        return directory

    def _validate(self, reference):
        digest = reference.get("sha256")
        size = reference.get("bytes")
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or type(size) is not int
            or size < 0
        ):
            raise ValueError("Checkpoint has an invalid content object reference.")
        directory = self.artifacts.path / "objects"
        if directory.is_symlink():
            raise ValueError("Checkpoint object directory must not be a symlink.")
        path = directory / (digest + ".utf8")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Checkpoint content object is missing: {digest}.")
        actual = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(128 * 1024):
                actual.update(chunk)
        if path.stat().st_size != size or actual.hexdigest() != digest:
            raise ValueError(f"Checkpoint content object checksum mismatch: {digest}.")
        return path

    def pack(self, checkpoint):
        if checkpoint.get("schema_version", 1) not in {2, 3}:
            return checkpoint
        references = []
        validated = set()

        def visit(value, path):
            if isinstance(value, str) and len(value) >= self.threshold:
                cached = self.cache.get(id(value))
                if cached is not None and cached[0] is value:
                    reference = cached[1]
                else:
                    payload = self.artifacts._redact(value).encode("utf-8", errors="surrogatepass")
                    digest = hashlib.sha256(payload).hexdigest()
                    reference = {"sha256": digest, "bytes": len(payload)}
                    destination = self._directory() / (digest + ".utf8")
                    if not destination.exists():
                        atomic_write(destination, payload)
                    # Keeping a strong reference avoids id reuse. Cache cardinality
                    # is bounded; evicting only causes rehashing, never data loss.
                    if len(self.cache) >= 4096:
                        self.cache.clear()
                    self.cache[id(value)] = (value, reference)
                if reference["sha256"] not in validated:
                    self._validate(reference)
                    validated.add(reference["sha256"])
                references.append({"path": path, **reference})
                return None
            if isinstance(value, dict):
                return {
                    key: visit(item, [*path, key]) for key, item in value.items() if path or key != "content_objects"
                }
            if isinstance(value, list):
                return [visit(item, [*path, index]) for index, item in enumerate(value)]
            return value

        compact = visit(checkpoint, [])
        compact["schema_version"] = 3
        compact["content_objects"] = references
        return compact

    def unpack(self, checkpoint):
        if checkpoint.get("schema_version") != 3:
            return checkpoint
        references = checkpoint.pop("content_objects", None)
        if not isinstance(references, list):
            raise ValueError("Checkpoint schema 3 has invalid content objects.")
        seen = set()
        values = {}
        for reference in references:
            if not isinstance(reference, dict) or not isinstance(reference.get("path"), list) or not reference["path"]:
                raise ValueError("Checkpoint has an invalid content object path.")
            path = reference["path"]
            if any(type(part) not in {str, int} for part in path) or tuple(path) in seen:
                raise ValueError("Checkpoint has an invalid or duplicate content object path.")
            seen.add(tuple(path))
            digest = reference.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Checkpoint has an invalid content object reference.")
            if digest not in values:
                object_path = self._validate(reference)
                values[digest] = object_path.read_bytes().decode("utf-8", errors="surrogatepass")
            elif len(values[digest].encode("utf-8", errors="surrogatepass")) != reference.get("bytes"):
                raise ValueError("Checkpoint content object has inconsistent length.")
            destination = checkpoint
            try:
                for part in path[:-1]:
                    if isinstance(part, int) and part < 0:
                        raise ValueError("Negative content object index.")
                    destination = destination[part]
                last = path[-1]
                if isinstance(last, int) and last < 0 or destination[last] is not None:
                    raise ValueError("Content object placeholder was modified.")
                destination[last] = values[digest]
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise ValueError("Checkpoint has an invalid content object placeholder.") from error
        return checkpoint
