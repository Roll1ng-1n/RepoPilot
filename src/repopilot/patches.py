"""Normalize explicit block patches to Git unified diffs before risk review."""

from __future__ import annotations

import difflib
from pathlib import Path


class PatchFormatError(ValueError):
    pass


def normalize_patch(patch: str, root: Path) -> str:
    """Accept unified diffs or exact-context Begin Patch Add/Update/Delete blocks.

    Conversion only reads files. Git applies the resulting diff atomically after
    the normal scoped-instruction and approval checks. Ambiguous contexts fail.
    """
    if not patch.startswith("*** Begin Patch"):
        return patch
    lines = patch.splitlines()
    if lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise PatchFormatError("Block patches must begin with *** Begin Patch and end with *** End Patch.")
    output = []
    touched = set()
    index = 1
    while index < len(lines) - 1:
        header = lines[index]
        operation = next(
            (kind for kind in ("Add", "Update", "Delete") if header.startswith(f"*** {kind} File: ")), None
        )
        if operation is None:
            raise PatchFormatError(
                "Expected *** Add File:, *** Update File:, or *** Delete File:. Moves require a unified diff."
            )
        name = header.split(": ", 1)[1]
        path = root / name
        if not name or Path(name).is_absolute() or any(char in name for char in ("\t", '"', "\\")):
            raise PatchFormatError("Use an unquoted repository-relative path in block patch headers.")
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as error:
            raise PatchFormatError("Patch paths must remain inside the Target Repository.") from error
        if path.is_symlink() or path.resolve() in touched:
            raise PatchFormatError("Block patches cannot target symlinks or repeat a file. Use a unified diff.")
        touched.add(path.resolve())
        if operation == "Add":
            if path.exists():
                raise PatchFormatError(f"{name} already exists; use Update File.")
            before = ""
        else:
            if not path.is_file():
                raise PatchFormatError(f"{name} does not exist; inspect the repository before patching.")
            before = path.read_bytes().decode("utf-8")
        index += 1
        body = []
        while index < len(lines) - 1 and not lines[index].startswith(
            ("*** Add File:", "*** Update File:", "*** Delete File:")
        ):
            body.append(lines[index])
            index += 1
        if operation == "Add":
            if any(not line.startswith("+") for line in body):
                raise PatchFormatError("Every line of Add File must start with +.")
            after = "".join(line[1:] + "\n" for line in body)
        elif operation == "Delete":
            if body:
                raise PatchFormatError("Delete File takes only a file header, without hunks.")
            after = ""
        else:
            after = _update(before, body, name)
        prefix = f'diff --git "a/{name}" "b/{name}"\n'
        if operation == "Add":
            prefix += "new file mode 100644\n"
        elif operation == "Delete":
            mode = "100755" if path.stat().st_mode & 0o111 else "100644"
            prefix += f"deleted file mode {mode}\n"
        changes = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="/dev/null" if operation == "Add" else "a/" + name,
            tofile="/dev/null" if operation == "Delete" else "b/" + name,
        )
        diff = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in changes)
        if not diff and operation == "Update":
            raise PatchFormatError(f"Patch makes no change to {name}; read the current file and verify the result.")
        output.append(prefix + diff)
    if not output:
        raise PatchFormatError("Patch contains no file changes.")
    return "".join(output)


def _update(before: str, body: list[str], name: str) -> str:
    source = before.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in before else "\n"
    cursor = 0
    index = 0
    if not body:
        raise PatchFormatError(f"Update File {name} needs at least one @@ hunk.")
    while index < len(body):
        if not body[index].startswith("@@"):
            raise PatchFormatError("Each Update File hunk must start with @@, with context lines prefixed by a space.")
        anchor = body[index][2:].strip()
        index += 1
        if anchor:
            matches = [i for i in range(cursor, len(source)) if source[i].rstrip("\r\n") == anchor]
            if len(matches) != 1:
                raise PatchFormatError(f"Hunk anchor is absent or ambiguous in {name}; include more context.")
            cursor = matches[0] + 1
        old, new = [], []
        eof = False
        while index < len(body) and not body[index].startswith("@@"):
            line = body[index]
            index += 1
            if line == "*** End of File":
                eof = True
                break
            if not line or line[0] not in " +-":
                raise PatchFormatError("Hunk lines need a space (context), - (removed), or + (added).")
            if line[0] in " -":
                old.append(line[1:])
            if line[0] in " +":
                new.append(line[1:])
        candidates = [
            i
            for i in range(cursor, len(source) - len(old) + 1)
            if [line.rstrip("\r\n") for line in source[i : i + len(old)]] == old
            and (not eof or i + len(old) == len(source))
        ]
        if len(candidates) != 1:
            raise PatchFormatError(
                f"Hunk context is absent or ambiguous in {name}; read the file and include unique context."
            )
        start = candidates[0]
        replacement = [line + newline for line in new]
        source[start : start + len(old)] = replacement
        cursor = start + len(replacement)
    return "".join(source)
