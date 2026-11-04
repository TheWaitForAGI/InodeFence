"""Freeze a preregistration draft: fill its TBD-FREEZE tokens, nothing else.

A draft (e.g. ``experiments/preregistration/exp0-pilot-v2.1.md``) carries
``key = TBD-FREEZE`` lines for the values that are only known at freeze time
(engine SHA, image digest, sentinel generator seed, ...). The parser refuses such a
file, so a draft is non-executable by construction. This tool replaces exactly those
tokens and guarantees every other byte is unchanged:

    python scripts/freeze_preregistration.py experiments/preregistration/exp0-pilot-v2.1.md \\
        --engine-sha HEAD --image-digest docker:inodefence-node-tar-effect:7.5.2 \\
        --sentinel-generator-seed 4242 --out /tmp/exp0-pilot-v2.1.frozen.md

``--engine-sha HEAD`` reads the current checkout; ``--image-digest docker:<image>``
reads ``docker image inspect``. ``--set KEY=VALUE`` fills any other token line (for
example ``targets.<id>.image_digest`` or ``exposure_ledger_sha256``). The result is
parsed with the registration parser and a gate preview is printed (format status,
whether the engine SHA matches the current HEAD and whether the checkout is clean),
together with the unified diff and the SHA-256 of the frozen bytes. A token left
unfilled, a value given for a line that is not a token, or any non-token byte
changing makes the tool fail without writing. ``--check`` only inspects a file.
The tool never commits or pushes (the Evidence lane opens the freeze PR).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inodefence.evaluation.rds_preregistration import (  # noqa: E402
    FENCE_CLOSE,
    FENCE_OPEN,
    Preregistration,
    PreregistrationFormatError,
    parse_preregistration,
)
from inodefence.provenance import capture_source  # noqa: E402

TOKEN = "TBD-FREEZE"
NAMED_FLAGS = {
    "engine_sha": "--engine-sha",
    "image_digest": "--image-digest",
    "sentinel_generator_seed": "--sentinel-generator-seed",
}
_LINE = re.compile(
    r"^(?P<lead>\s*)(?P<key>[A-Za-z0-9_.-]+)(?P<sep>\s*=\s*)(?P<value>.*?)(?P<trail>\s*)$"
)


class FreezeError(ValueError):
    pass


def _block_span(lines: list[str]) -> tuple[int, int]:
    """Line indexes (start, end) of the first fenced preregistration block body."""
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == FENCE_OPEN)
    except StopIteration:
        raise FreezeError(f"no {FENCE_OPEN} block") from None
    try:
        end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == FENCE_CLOSE)
    except StopIteration:
        raise FreezeError("preregistration block is not closed") from None
    return start + 1, end


def token_lines(text: str, token: str = TOKEN) -> dict[str, int]:
    """``key -> line index`` of every ``key = <token>`` line inside the block."""
    lines = text.split("\n")
    start, end = _block_span(lines)
    found: dict[str, int] = {}
    for index in range(start, end):
        match = _LINE.match(lines[index])
        if match and not match["key"].startswith("#") and match["value"] == token:
            found[match["key"]] = index
    return found


def fill_tokens(text: str, values: dict[str, str], token: str = TOKEN) -> str:
    """Replace the token on the named key lines; every other byte stays the same.

    Raises when a value targets a line that is not a token line, when a token line
    is left unfilled, or when the rewrite changed anything but the token values.
    """
    lines = text.split("\n")
    tokens = token_lines(text, token)
    unknown = sorted(set(values) - set(tokens))
    if unknown:
        raise FreezeError(f"not {token} lines in the block (refusing to change them): {unknown}")
    missing = sorted(set(tokens) - set(values))
    if missing:
        raise FreezeError(f"{token} still unfilled for: {missing}")
    for key, value in values.items():
        if not value or "\n" in value or value == token:
            raise FreezeError(f"{key}: value must be a nonempty single-line string")
        index = tokens[key]
        match = _LINE.match(lines[index])
        assert match is not None
        lines[index] = f"{match['lead']}{match['key']}{match['sep']}{value}{match['trail']}"
    result = "\n".join(lines)
    _assert_only_tokens_changed(text, result, tokens, values, token)
    return result


def _assert_only_tokens_changed(
    before: str, after: str, tokens: dict[str, int], values: dict[str, str], token: str
) -> None:
    before_lines, after_lines = before.split("\n"), after.split("\n")
    if len(before_lines) != len(after_lines):
        raise FreezeError("line count changed")
    changed = {i for i, (a, b) in enumerate(zip(before_lines, after_lines, strict=True)) if a != b}
    expected = set(tokens.values())
    if changed != expected:
        raise FreezeError(f"lines changed outside the token lines: {sorted(changed - expected)}")
    for key, index in tokens.items():
        if before_lines[index].replace(token, values[key], 1) != after_lines[index]:
            raise FreezeError(f"{key}: line changed beyond the token")


def resolve_engine_sha(value: str) -> str:
    if value.upper() == "HEAD":
        revision = capture_source().revision
        if revision is None:
            raise FreezeError("--engine-sha HEAD: not a git checkout")
        return revision
    return value


def resolve_image_digest(value: str) -> str:
    if value.startswith("docker:"):
        image = value[len("docker:") :]
        completed = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise FreezeError(f"docker image inspect {image}: {completed.stderr.strip()}")
        return completed.stdout.strip()
    return value


def gate_preview(text: str) -> tuple[Preregistration | None, list[str]]:
    """Parse the text and describe the gate state a live run would see."""
    notes: list[str] = []
    try:
        prereg = parse_preregistration(text)
    except PreregistrationFormatError as error:
        return None, [f"format: FAIL ({error})"]
    notes.append("format: OK")
    source = capture_source()
    if source.revision is None:
        notes.append("engine_sha vs HEAD: unknown (not a git checkout)")
    else:
        same = source.revision == prereg.engine_sha
        notes.append(f"engine_sha vs HEAD: {'match' if same else 'MISMATCH'} ({source.revision})")
    notes.append(f"checkout clean: {'no (gate would refuse)' if source.dirty else 'yes'}")
    arms = [arm.value for arm in prereg.arm_policies]
    targets = [target.target_id for target in prereg.targets] or "single image_digest"
    notes.append(
        f"plan: seeds={list(prereg.seeds)} budget={prereg.budget} arms={arms} targets={targets}"
    )
    if prereg.unknown_keys:
        notes.append(f"unknown keys (not compared): {list(prereg.unknown_keys)}")
    return prereg, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("draft", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="where to write the frozen file")
    parser.add_argument("--in-place", action="store_true", help="overwrite the draft")
    parser.add_argument("--check", action="store_true", help="inspect only; no substitution")
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--engine-sha", default=None, help="40-hex commit or HEAD")
    parser.add_argument("--image-digest", default=None, help="sha256:<64hex> or docker:<image>")
    parser.add_argument("--sentinel-generator-seed", type=int, default=None)
    parser.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE", help="any other token line"
    )
    args = parser.parse_args(argv)

    text = args.draft.read_text(encoding="utf-8")
    try:
        tokens = token_lines(text, args.token)
    except FreezeError as error:
        print(f"unusable draft: {error}", file=sys.stderr)
        return 2
    print(f"draft: {args.draft} sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()}")
    print(f"{args.token} lines: {sorted(tokens) or 'none'}")

    if args.check:
        _, notes = gate_preview(text)
        for note in notes:
            print(note)
        return 0 if not tokens and notes[0] == "format: OK" else 2

    if (args.out is None) == (not args.in_place):
        parser.error("choose exactly one of --out PATH / --in-place")
    values: dict[str, str] = {}
    try:
        if args.engine_sha is not None:
            values["engine_sha"] = resolve_engine_sha(args.engine_sha)
        if args.image_digest is not None:
            values["image_digest"] = resolve_image_digest(args.image_digest)
        if args.sentinel_generator_seed is not None:
            values["sentinel_generator_seed"] = str(args.sentinel_generator_seed)
        for item in args.set:
            key, sep, value = item.partition("=")
            if not sep or not key.strip():
                raise FreezeError(f"--set expects KEY=VALUE, got {item!r}")
            values[key.strip()] = value.strip()
        frozen = fill_tokens(text, values, args.token)
    except FreezeError as error:
        print(f"freeze refused: {error}", file=sys.stderr)
        return 2
    prereg, notes = gate_preview(frozen)
    diff = difflib.unified_diff(
        text.splitlines(keepends=True),
        frozen.splitlines(keepends=True),
        fromfile=str(args.draft),
        tofile=str(args.out or args.draft),
    )
    sys.stdout.writelines(diff)
    for note in notes:
        print(note)
    if prereg is None:
        print("frozen text does not parse; nothing written", file=sys.stderr)
        return 2
    target = args.draft if args.in_place else args.out
    target.write_text(frozen, encoding="utf-8")
    digest = hashlib.sha256(frozen.encode("utf-8")).hexdigest()
    print(f"wrote {target} sha256={digest}")
    print("not committed: the Evidence lane opens the freeze PR with this file and sha256")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
