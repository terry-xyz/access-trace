"""In-memory validation and bounding for uploaded source context."""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Set, Tuple


MAX_SOURCE_FILES = 200
MAX_SOURCE_FILE_BYTES = 512 * 1024
MAX_SOURCE_REQUEST_BYTES = 5 * 1024 * 1024
MAX_REVIEW_SOURCE_BYTES = 64 * 1024
MAX_REVIEW_FILE_BYTES = 32 * 1024
MAX_GITIGNORE_RULES = 10_000
MAX_GITIGNORE_PATTERN_BYTES = 1024
MAX_SOURCE_PATH_BYTES = 4096
MAX_GITIGNORE_MATCH_WORK = 20_000_000
GitIgnoreToken = Tuple[str, Any]
GitIgnoreRule = Tuple[str, List[GitIgnoreToken], bool, bool, bool, bool]

GENERATED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".next",
        ".nuxt",
        ".venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
        "__pycache__",
        "bower_components",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "out",
        "Pods",
        "site-packages",
        "target",
        "venv",
        "vendor",
    }
)
SENSITIVE_DIRECTORIES = frozenset(
    {".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker"}
)
SENSITIVE_FILENAMES = frozenset(
    {".npmrc", ".pypirc", ".netrc", ".envrc", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
)
SENSITIVE_EXTENSIONS = frozenset({".key", ".pem", ".p12", ".pfx"})
SENSITIVE_CONFIG_EXTENSIONS = frozenset(
    {"", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt", ".properties"}
)
SENSITIVE_STEMS = frozenset(
    {
        "credential", "credentials", "secret", "secrets", "token", "tokens",
        "service-account", "service_account", "client-secret", "client_secret",
        "access-token", "access_token",
    }
)


class SourceContextError(ValueError):
    """Raised when a source manifest violates its request contract."""


@dataclass(frozen=True)
class SourceFile:
    """One accepted file, held only in the active request's memory."""

    path: str
    content: str
    size_bytes: int


@dataclass
class PreparedSourceContext:
    """Validated files and skipped-file details for one source review."""

    files: List[SourceFile] = field(default_factory=list)
    skipped: List[Dict[str, str]] = field(default_factory=list)

    def cleanup(self) -> None:
        """Release uploaded source text after review; nothing was written to disk."""
        self.files.clear()


def normalize_source_path(path: Any) -> str:
    """Return a canonical relative POSIX path or reject unsafe path syntax."""
    if not isinstance(path, str):
        raise SourceContextError("each source path must be text")
    if not path or "\x00" in path:
        raise SourceContextError("source paths must be non-empty and contain no NUL")
    try:
        path.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise SourceContextError("source paths must be valid UTF-8 text") from error
    if len(path.encode("utf-8")) > MAX_SOURCE_PATH_BYTES:
        raise SourceContextError("source paths must be 4096 bytes or fewer")
    if path.startswith("/") or "\\" in path or re.match(r"^[A-Za-z]:", path):
        raise SourceContextError("source paths must be relative POSIX paths")
    parts = path.split("/")
    if any(part == ".." for part in parts):
        raise SourceContextError("source paths must not contain parent traversal")
    normalized_parts = [part for part in parts if part not in {"", "."}]
    if not normalized_parts:
        raise SourceContextError("source paths must name a file")
    normalized = PurePosixPath(*normalized_parts).as_posix()
    if normalized.startswith("/"):
        raise SourceContextError("source paths must be relative POSIX paths")
    return normalized


def _request_size(payload: Dict[str, Any]) -> int:
    """Estimate compact UTF-8 JSON size for callers that lack the raw body bytes."""
    try:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        # JSON can carry lone surrogate escapes although those are not UTF-8 source.
        serialized = "".join(
            "\\u{:04x}".format(ord(character))
            if 0xD800 <= ord(character) <= 0xDFFF
            else character
            for character in serialized
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise SourceContextError("source context must be valid UTF-8 JSON data") from error
    return len(serialized)


def _is_binary_text(content: str) -> bool:
    """Treat non-text control characters as binary while allowing common whitespace."""
    for character in content:
        if character in "\t\n\r":
            continue
        if unicodedata.category(character) == "Cc":
            return True
    return False


def _gitignore_rules(
    content: str, base_path: str, max_rules: int
) -> Tuple[List[GitIgnoreRule], Optional[str]]:
    """Parse the common Git ignore pattern forms into scoped rules.

    Rules support comments, escaped comment/negation prefixes, directory-only
    patterns, anchored patterns, `*`, `?`, character classes, and `**`. Git has
    additional escaping and directory-pruning edge cases; those are intentionally
    not emulated by this small standard-library matcher.
    """
    parsed: List[GitIgnoreRule] = []
    for original in content.splitlines():
        line = original.rstrip()
        if not line:
            continue
        if line.startswith("\\#"):
            line = line[1:]
        elif line.startswith("#"):
            continue
        negated = False
        if line.startswith("\\!"):
            line = line[1:]
        elif line.startswith("!"):
            negated = True
            line = line[1:]
        if not line:
            continue
        directory_only = line.endswith("/")
        line = line.rstrip("/")
        anchored = line.startswith("/")
        pattern = line.lstrip("/")
        if not pattern:
            continue
        if len(pattern.encode("utf-8")) > MAX_GITIGNORE_PATTERN_BYTES:
            return parsed, "gitignore-pattern-limit"
        if len(parsed) >= max_rules:
            return parsed, "gitignore-rule-limit"
        parsed.append(
            (
                base_path,
                _compile_gitignore_pattern(pattern),
                negated,
                directory_only,
                anchored,
                "/" in pattern,
            )
        )
    return parsed, None


def _compile_gitignore_pattern(pattern: str) -> List[GitIgnoreToken]:
    """Compile supported globs to bounded NFA tokens instead of backtracking regexes."""
    tokens: List[GitIgnoreToken] = []
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 1
                if index + 1 < len(pattern) and pattern[index + 1] == "/":
                    tokens.append(("globstar-directories", None))
                    index += 1
                else:
                    tokens.append(("globstar", None))
            else:
                tokens.append(("star", None))
        elif character == "?":
            tokens.append(("any", None))
        elif character == "[":
            closing = pattern.find("]", index + 1)
            if closing == -1:
                tokens.append(("literal", "["))
            else:
                group = pattern[index + 1 : closing]
                negated = group.startswith("!")
                if negated:
                    group = group[1:]
                members = set()
                ranges = []
                group_index = 0
                while group_index < len(group):
                    if (
                        group_index + 2 < len(group)
                        and group[group_index + 1] == "-"
                        and group_index + 2 < len(group)
                    ):
                        first = ord(group[group_index])
                        last = ord(group[group_index + 2])
                        if first <= last:
                            ranges.append((first, last))
                        else:
                            members.update((group[group_index], "-", group[group_index + 2]))
                        group_index += 3
                    else:
                        members.add(group[group_index])
                        group_index += 1
                tokens.append(("class", (negated, frozenset(members), tuple(ranges))))
                index = closing
        else:
            tokens.append(("literal", character))
        index += 1
    return tokens


class _GitIgnoreWorkBudget:
    """Bound glob-state transitions across all candidate files in one manifest."""

    def __init__(self, remaining: int = MAX_GITIGNORE_MATCH_WORK):
        self.remaining = remaining

    def spend(self) -> None:
        self.remaining -= 1
        if self.remaining < 0:
            raise SourceContextError("gitignore work limit exceeded")


def _class_matches(
    character: str, spec: Any, budget: _GitIgnoreWorkBudget
) -> bool:
    negated, members, ranges = spec
    matched = character in members
    codepoint = ord(character)
    if not matched:
        for first, last in ranges:
            budget.spend()
            if first <= codepoint <= last:
                matched = True
                break
    return not matched if negated else matched


def _glob_matches(
    text: str, tokens: List[GitIgnoreToken], budget: _GitIgnoreWorkBudget
) -> bool:
    """Match a path with an epsilon-NFA whose work is charged to the manifest."""

    def epsilon_closure(states: Set[int]) -> Set[int]:
        closed = set(states)
        pending = list(states)
        while pending:
            state = pending.pop()
            if state < len(tokens) and tokens[state][0] in {
                "star",
                "globstar",
                "globstar-directories",
            }:
                budget.spend()
                next_state = state + 1
                if next_state not in closed:
                    closed.add(next_state)
                    pending.append(next_state)
        return closed

    states = epsilon_closure({0})
    for character in text:
        next_states: Set[int] = set()
        for state in states:
            budget.spend()
            if state >= len(tokens):
                continue
            kind, value = tokens[state]
            if kind == "star" and character != "/":
                next_states.add(state)
            elif kind == "globstar":
                next_states.add(state)
            elif kind == "globstar-directories":
                next_states.add(state)
                if character == "/":
                    next_states.add(state + 1)
            elif kind == "any" and character != "/":
                next_states.add(state + 1)
            elif kind == "literal" and character == value:
                next_states.add(state + 1)
            elif (
                kind == "class"
                and character != "/"
                and _class_matches(character, value, budget)
            ):
                next_states.add(state + 1)
        states = epsilon_closure(next_states)
        if not states:
            return False
    return len(tokens) in epsilon_closure(states)


def _rule_matches(
    relative_path: str,
    tokens: List[GitIgnoreToken],
    directory_only: bool,
    anchored: bool,
    has_slash: bool,
    budget: _GitIgnoreWorkBudget,
) -> bool:
    parts = relative_path.split("/")
    if not has_slash:
        if anchored:
            candidates = (
                ["/".join(parts[:index]) for index in range(1, len(parts))]
                if directory_only
                else [relative_path]
            )
            return any(_glob_matches(candidate, tokens, budget) for candidate in candidates)
        segments = parts[:-1] if directory_only else parts
        return any(_glob_matches(segment, tokens, budget) for segment in segments)
    candidates = ["/".join(parts[:index]) for index in range(1, len(parts) + 1)]
    if directory_only:
        candidates = candidates[:-1]
    return any(_glob_matches(candidate, tokens, budget) for candidate in candidates)


def _generated_directory_reason(path: str) -> Optional[str]:
    parts = path.split("/")
    if any(part in GENERATED_DIRECTORIES for part in parts[:-1]):
        return "generated-or-dependency-directory"
    return None


def sensitive_source_path(path: str) -> bool:
    """Keep common credential files out of both source review and site uploads."""
    parts = [part.casefold() for part in path.split("/")]
    name = parts[-1]
    suffix = PurePosixPath(name).suffix
    stem = name[: -len(suffix)] if suffix else name
    return (
        any(part in SENSITIVE_DIRECTORIES for part in parts[:-1])
        or name in SENSITIVE_FILENAMES
        or name == ".env"
        or name.startswith(".env.")
        or suffix in SENSITIVE_EXTENSIONS
        or (suffix in SENSITIVE_CONFIG_EXTENSIONS and stem in SENSITIVE_STEMS)
    )


def _gitignore_reason(
    path: str, rules: List[GitIgnoreRule], budget: _GitIgnoreWorkBudget
) -> Optional[str]:
    parts = path.split("/")
    ignored = False
    # .gitignore files are applied from shallower to deeper locations, preserving
    # source order within each file so a later negation can restore a path.
    for base_path, tokens, negated, directory_only, anchored, has_slash in rules:
        base = base_path.split("/") if base_path else []
        if parts[: len(base)] != base:
            continue
        relative = "/".join(parts[len(base) :])
        if not relative:
            continue
        if _rule_matches(relative, tokens, directory_only, anchored, has_slash, budget):
            ignored = not negated
    return "gitignore" if ignored else None


def prepare_source_context(payload: Any) -> PreparedSourceContext:
    """Validate, filter, and bound a source manifest without writing its text."""
    if not isinstance(payload, dict) or set(payload) != {"files"}:
        raise SourceContextError('source context must be an object with a "files" array')
    if _request_size(payload) > MAX_SOURCE_REQUEST_BYTES:
        raise SourceContextError("source context exceeds the request size limit")
    entries = payload.get("files")
    if not isinstance(entries, list):
        raise SourceContextError('source context "files" must be an array')
    if len(entries) > MAX_SOURCE_FILES:
        raise SourceContextError("source context contains too many files")

    normalized_entries = []
    seen_paths = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {"path", "content", "selectionType"}:
            raise SourceContextError("each source file must contain path and content fields")
        path = normalize_source_path(entry.get("path"))
        content = entry.get("content")
        if not isinstance(content, str):
            raise SourceContextError("each source file content must be text")
        if "\x00" in content:
            raise SourceContextError("source text must not contain NUL characters")
        if path in seen_paths:
            raise SourceContextError("source paths must be unique after normalization")
        seen_paths.add(path)
        selection_type = entry.get("selectionType", "file")
        if not isinstance(selection_type, str) or selection_type not in {"file", "directory"}:
            raise SourceContextError('selectionType must be "file" or "directory"')
        try:
            size_bytes = len(content.encode("utf-8", errors="strict"))
        except UnicodeEncodeError:
            # JSON strings containing unpaired surrogates are not valid UTF-8 text.
            normalized_entries.append((path, content, selection_type, None))
            continue
        normalized_entries.append((path, content, selection_type, size_bytes))

    normalized_entries.sort(key=lambda item: item[0])
    gitignore_rules: List[GitIgnoreRule] = []
    gitignore_limit_reason: Optional[str] = None
    for path, content, selection_type, size_bytes in normalized_entries:
        if selection_type != "directory" or PurePosixPath(path).name != ".gitignore":
            continue
        if (
            size_bytes is None
            or size_bytes > MAX_SOURCE_FILE_BYTES
            or _is_binary_text(content)
        ):
            gitignore_limit_reason = "gitignore-file-unavailable"
            break
        else:
            base = str(PurePosixPath(path).parent)
            if base == ".":
                base = ""
            new_rules, limit_reason = _gitignore_rules(
                content, base, MAX_GITIGNORE_RULES - len(gitignore_rules)
            )
            gitignore_rules.extend(new_rules)
            if limit_reason:
                gitignore_limit_reason = limit_reason
                break

    gitignore_skip_reasons: Dict[str, str] = {}
    gitignore_work_limit_exceeded = False
    if gitignore_limit_reason is None:
        match_budget = _GitIgnoreWorkBudget()
        for path, content, selection_type, size_bytes in normalized_entries:
            if (
                selection_type != "directory"
                or size_bytes is None
                or size_bytes > MAX_REVIEW_FILE_BYTES
                or _is_binary_text(content)
                or _generated_directory_reason(path)
            ):
                continue
            try:
                ignore_reason = _gitignore_reason(path, gitignore_rules, match_budget)
            except SourceContextError:
                gitignore_work_limit_exceeded = True
                break
            if ignore_reason:
                gitignore_skip_reasons[path] = ignore_reason

    prepared = PreparedSourceContext()
    review_bytes = 0
    for path, content, selection_type, size_bytes in normalized_entries:
        if sensitive_source_path(path):
            prepared.skipped.append({"path": path, "reason": "sensitive-file"})
            continue
        if size_bytes is None:
            prepared.skipped.append({"path": path, "reason": "unsupported-utf8"})
            continue
        if size_bytes > MAX_SOURCE_FILE_BYTES:
            prepared.skipped.append({"path": path, "reason": "file-size-limit"})
            continue
        if _is_binary_text(content):
            prepared.skipped.append({"path": path, "reason": "unsupported-binary"})
            continue
        generated_reason = _generated_directory_reason(path)
        if generated_reason:
            prepared.skipped.append({"path": path, "reason": generated_reason})
            continue
        if selection_type == "directory":
            if gitignore_limit_reason:
                prepared.skipped.append({"path": path, "reason": gitignore_limit_reason})
                continue
            if gitignore_work_limit_exceeded:
                prepared.skipped.append({"path": path, "reason": "gitignore-work-limit"})
                continue
            ignore_reason = gitignore_skip_reasons.get(path)
            if ignore_reason:
                prepared.skipped.append({"path": path, "reason": ignore_reason})
                continue
        if size_bytes > MAX_REVIEW_FILE_BYTES:
            prepared.skipped.append({"path": path, "reason": "review-file-size-limit"})
            continue
        if review_bytes + size_bytes > MAX_REVIEW_SOURCE_BYTES:
            prepared.skipped.append({"path": path, "reason": "review-source-budget"})
            continue
        prepared.files.append(SourceFile(path, content, size_bytes))
        review_bytes += size_bytes
    return prepared
