"""Strict application of validated unified diffs to an in-memory file set."""

import re
from typing import Dict

from .source_review import SourceReviewError, _patch_paths
from .source_context import normalize_source_path


_HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?")


def apply_unified_patch(patch: str, files: Dict[str, str]) -> Dict[str, str]:
    """Apply a reviewer patch exactly to supplied UTF-8 files, rejecting drift."""
    paths = _patch_paths(patch)
    for line in patch.splitlines():
        if line.startswith(("new file mode ", "deleted file mode ", "old mode ", "new mode ")):
            raise SourceReviewError("file creation, deletion, and mode changes are not supported")
        if line.startswith(("--- ", "+++ ")) and line[4:].split("\t", 1)[0] == "/dev/null":
            raise SourceReviewError("file creation and deletion are not supported")
    if not paths.issubset(files):
        raise SourceReviewError("patch references a file missing from the approval context")
    lines = patch.splitlines()
    result = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("diff --git "):
            index += 1
            continue
        header = line[len("diff --git ") :]
        if not header.startswith("a/"):
            raise SourceReviewError("patch contains an unsupported file path")
        tail = header[2:]
        candidates = []
        offset = 0
        while True:
            split = tail.find(" b/", offset)
            if split < 0:
                break
            if tail[:split] == tail[split + 3 :]:
                candidates.append(tail[:split])
            offset = split + 1
        if len(candidates) != 1:
            raise SourceReviewError("patch contains an unsupported or ambiguous file path")
        path = normalize_source_path(candidates[0])
        original = files[path].splitlines(keepends=True)
        output = []
        cursor = 0
        index += 1
        while index < len(lines) and not lines[index].startswith("diff --git "):
            match = _HUNK.fullmatch(lines[index])
            if not match:
                index += 1
                continue
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            # Unified diff line positions are one based; a zero range starts at zero.
            target = old_start if old_count == 0 else old_start - 1
            new_target = new_start if new_count == 0 else new_start - 1
            if target < cursor or target > len(original):
                raise SourceReviewError("patch hunk has an invalid source position")
            output.extend(original[cursor:target])
            if new_target != len(output):
                raise SourceReviewError("patch hunk has an invalid replacement position")
            cursor = target
            old_seen = new_seen = 0
            index += 1
            newline = "\r\n" if any(item.endswith("\r\n") for item in original) else "\n"
            while index < len(lines) and lines[index] and lines[index][0] in " +-":
                body = lines[index]
                marker, value = body[0], body[1:]
                no_newline = (
                    index + 1 < len(lines)
                    and lines[index + 1] == r"\ No newline at end of file"
                )
                if marker in " -":
                    if cursor >= len(original):
                        raise SourceReviewError("patch does not match the current file contents")
                    current = original[cursor]
                    if current.rstrip("\r\n") != value:
                        raise SourceReviewError("patch does not match the current file contents")
                    has_newline = current.endswith(("\n", "\r"))
                    if has_newline == no_newline:
                        raise SourceReviewError("patch newline marker does not match the current file")
                    cursor += 1
                    old_seen += 1
                if marker in " +":
                    output.append(value + ("" if no_newline else newline))
                    new_seen += 1
                index += 1
                if no_newline:
                    index += 1
            if old_seen != old_count or new_seen != new_count:
                raise SourceReviewError("patch hunk line counts do not match its header")
        output.extend(original[cursor:])
        result[path] = "".join(output)
    if set(result) != paths:
        raise SourceReviewError("patch did not produce replacement contents for every file")
    return result
