"""freeze_preregistration: fills TBD-FREEZE tokens only; refuses anything else."""

import hashlib
from pathlib import Path

import pytest
from scripts import freeze_preregistration as tool

from inodefence.evaluation.rds_preregistration import parse_preregistration
from inodefence.model.provenance import SourceProvenance

SHA = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "ab" * 32
DRAFT = """# EXP-0 v2.1 (draft; TBD-FREEZE until the freeze)

prose mentions TBD-FREEZE too, and must stay untouched.

```preregistration
# comment with TBD-FREEZE inside is not a key line
engine_sha = TBD-FREEZE
image_digest   =  TBD-FREEZE
seeds = 9001, 9002
budget = 6
vocabulary = observed-names
arm.R = unretained-walk-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = TBD-FREEZE
sentinel_count = 3
```

trailing prose with TBD-FREEZE.
"""


TOKEN_KEYS = {"engine_sha", "image_digest", "sentinel_generator_seed"}


@pytest.fixture
def draft(tmp_path: Path) -> Path:
    path = tmp_path / "exp0-pilot-v2.1.md"
    path.write_text(DRAFT, encoding="utf-8")
    return path


@pytest.fixture
def clean_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool, "capture_source", lambda: SourceProvenance(SHA, False))


def _only_token_lines_differ(before: str, after: str, keys: set[str]) -> None:
    b, a = before.split("\n"), after.split("\n")
    assert len(b) == len(a)
    changed = [(x, y) for x, y in zip(b, a, strict=True) if x != y]
    assert {line.split("=")[0].strip() for line, _ in changed} == keys
    for x, y in changed:
        assert x.replace("TBD-FREEZE", "", 1) == y.replace(y.split("=", 1)[1].strip(), "", 1)


def test_token_lines_are_only_key_lines_inside_the_block() -> None:
    assert set(tool.token_lines(DRAFT)) == {"engine_sha", "image_digest", "sentinel_generator_seed"}


def test_fill_replaces_tokens_and_nothing_else() -> None:
    frozen = tool.fill_tokens(
        DRAFT,
        {"engine_sha": SHA, "image_digest": DIGEST, "sentinel_generator_seed": "4242"},
    )
    _only_token_lines_differ(
        DRAFT, frozen, {"engine_sha", "image_digest", "sentinel_generator_seed"}
    )
    assert "image_digest   =  " + DIGEST in frozen  # spacing preserved
    assert frozen.count("TBD-FREEZE") == 4  # title, prose, comment, trailer untouched
    prereg = parse_preregistration(frozen)
    assert prereg.engine_sha == SHA and prereg.image_digest == DIGEST
    assert prereg.sentinel_generator_seed == 4242
    assert tool.token_lines(frozen) == {}


@pytest.mark.parametrize(
    ("values", "fragment"),
    [
        (
            {"engine_sha": SHA, "image_digest": DIGEST},
            "still unfilled for: \\['sentinel_generator_seed'\\]",
        ),
        (
            {
                "engine_sha": SHA,
                "image_digest": DIGEST,
                "sentinel_generator_seed": "1",
                "budget": "9",
            },
            "not TBD-FREEZE lines",
        ),
        ({"engine_sha": "", "image_digest": DIGEST, "sentinel_generator_seed": "1"}, "nonempty"),
        (
            {"engine_sha": "a\nb", "image_digest": DIGEST, "sentinel_generator_seed": "1"},
            "single-line",
        ),
    ],
)
def test_fill_refuses_missing_extra_or_malformed_values(values: dict, fragment: str) -> None:
    with pytest.raises(tool.FreezeError, match=fragment):
        tool.fill_tokens(DRAFT, values)


def test_cli_freezes_a_copy_reports_diff_sha_and_gate(
    draft: Path, tmp_path: Path, clean_engine: None, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def fake_run(command, **_kwargs):
        class Done:
            returncode = 0
            stdout = DIGEST + "\n"
            stderr = ""

        assert command[:3] == ["docker", "image", "inspect"] and command[-1] == "img:7.5.2"
        return Done()

    monkeypatch.setattr(tool.subprocess, "run", fake_run)
    out = tmp_path / "frozen.md"
    code = tool.main(
        [
            str(draft),
            "--engine-sha",
            "HEAD",
            "--image-digest",
            "docker:img:7.5.2",
            "--sentinel-generator-seed",
            "4242",
            "--out",
            str(out),
        ]
    )
    text = capsys.readouterr().out
    assert code == 0 and out.is_file()
    frozen = out.read_text(encoding="utf-8")
    assert draft.read_text(encoding="utf-8") == DRAFT  # the draft is untouched
    _only_token_lines_differ(
        DRAFT, frozen, {"engine_sha", "image_digest", "sentinel_generator_seed"}
    )
    assert f"+engine_sha = {SHA}" in text and "-engine_sha = TBD-FREEZE" in text
    assert "format: OK" in text and "engine_sha vs HEAD: match" in text
    assert f"sha256={hashlib.sha256(frozen.encode()).hexdigest()}" in text
    assert "not committed" in text


def test_cli_refuses_when_a_token_is_left(
    draft: Path, tmp_path: Path, clean_engine: None, capsys
) -> None:
    out = tmp_path / "frozen.md"
    code = tool.main([str(draft), "--engine-sha", SHA, "--image-digest", DIGEST, "--out", str(out)])
    assert code == 2 and not out.exists()
    assert "still unfilled for: ['sentinel_generator_seed']" in capsys.readouterr().err


def test_cli_check_mode_reports_without_writing(draft: Path, clean_engine: None, capsys) -> None:
    assert tool.main([str(draft), "--check"]) == 2  # tokens remain -> not executable
    text = capsys.readouterr().out
    assert "TBD-FREEZE lines: ['engine_sha', 'image_digest', 'sentinel_generator_seed']" in text
    assert "format: FAIL" in text
    frozen = draft.with_name("frozen.md")
    frozen.write_text(
        tool.fill_tokens(
            DRAFT, {"engine_sha": SHA, "image_digest": DIGEST, "sentinel_generator_seed": "1"}
        ),
        encoding="utf-8",
    )
    assert tool.main([str(frozen), "--check"]) == 0
    text = capsys.readouterr().out
    assert "TBD-FREEZE lines: none" in text and "format: OK" in text


def test_cli_set_fills_other_token_lines(tmp_path: Path, clean_engine: None) -> None:
    draft = tmp_path / "exp3.md"
    draft.write_text(
        DRAFT.replace(
            "sentinel_count = 3\n",
            "sentinel_count = 3\nexposure_ledger_sha256 = TBD-FREEZE\nexposure_ledger = x.md\n",
        ),
        encoding="utf-8",
    )
    out = tmp_path / "frozen.md"
    args = [
        str(draft),
        "--engine-sha",
        SHA,
        "--image-digest",
        DIGEST,
        "--sentinel-generator-seed",
        "1",
        "--out",
        str(out),
    ]
    assert tool.main(args) == 2  # exposure_ledger_sha256 still a token
    assert tool.main([*args, "--set", "exposure_ledger_sha256=" + "c" * 64]) == 0
    assert parse_preregistration(out.read_text()).exposure_ledger_sha256 == "c" * 64
