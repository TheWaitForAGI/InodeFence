"""Check canonical documents and local Markdown links in Git-visible files.

Supports ordinary inline/image links and reference links, including optional
link titles. Fenced code and inline code are skipped. This is a path existence
check, not a complete Markdown parser or an anchor validator.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

CANONICAL_DOCUMENTS = (
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "docs/START_HERE.md",
    "docs/STATUS.md",
    "docs/DECISIONS.md",
    "docs/GLOSSARY.md",
    "docs/research/design/architecture.md",
    "docs/research/design/security-contracts.md",
)
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
DESTINATION = r'(<[^>]+>|[^\s)]+)(?:\s+["\'][^\n]*?["\'])?'
INLINE_LINK = re.compile(r"!?\[[^\]\n]*\]\(" + DESTINATION + r"\)")
REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*" + DESTINATION)
REFERENCE_LINK = re.compile(r"!?\[([^\]\n]+)\]\[([^\]\n]*)\]")
INLINE_CODE = re.compile(r"(`+).*?\1")


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Keep line numbers while excluding backtick and tilde fenced examples."""
    lines = []
    fence_character = ""
    fence_length = 0
    for number, line in enumerate(text.splitlines(), 1):
        match = FENCE.match(line)
        if fence_character:
            if (
                match
                and match[1][0] == fence_character
                and len(match[1]) >= fence_length
                and not line[match.end() :].strip()
            ):
                fence_character = ""
            continue
        if match:
            fence_character, fence_length = match[1][0], len(match[1])
            continue
        if line.startswith(("    ", "\t")):
            continue
        lines.append((number, INLINE_CODE.sub("", line)))
    return lines


def check_document(document: Path) -> list[str]:
    """Report missing local destinations, resolved relative to this document."""
    lines = prose_lines(document.read_text(encoding="utf-8"))
    references = {}
    for _, line in lines:
        if match := REFERENCE_DEFINITION.match(line):
            references[" ".join(match[1].lower().split())] = match[2]

    errors = []
    for number, line in lines:
        destinations = [match[1] for match in INLINE_LINK.finditer(line)]
        if match := REFERENCE_DEFINITION.match(line):
            destinations.append(match[2])
        for match in REFERENCE_LINK.finditer(line):
            label = " ".join((match[2] or match[1]).lower().split())
            if label not in references:
                errors.append(f"{document}:{number}: undefined reference [{label}]")
        for destination in destinations:
            destination = destination.removeprefix("<").removesuffix(">")
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = document.parent / unquote(parsed.path)
            if not target.exists():
                errors.append(f"{document}:{number}: missing link target {destination}")
    return errors


def check_canonical_documents(root: Path) -> list[str]:
    return [
        f"Missing canonical document: {name}"
        for name in CANONICAL_DOCUMENTS
        if not (root / name).is_file()
    ]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    # Include new, untracked docs during local development; skip ignored raw data.
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    documents = sorted({name for name in result.stdout.split("\0") if name.endswith(".md")})
    errors = check_canonical_documents(root)
    for name in documents:
        document = root / name
        if document.is_file():
            errors.extend(check_document(document))
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Docs check: PASS ({len(documents)} Markdown files; canonical documents present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
