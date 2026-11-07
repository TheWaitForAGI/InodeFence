"""Fill the capstone report HWP form from the cell-by-cell body, and check a saved form.

The template is copied and never modified. ``cell-map.json`` pins its SHA-256 and the form cells.
Personal header values stay out of the repository and come from ``--header-values``.

Run (host; needs Node and the claw-hwp plugin, no docker):
    python3 paper/deliverables/hwp/fill_form.py fill --template <form.hwp> --out <out.hwp>
    python3 paper/deliverables/hwp/fill_form.py fill --template <form.hwp> --out <out.hwp> \\
        --header-values ~/capstone-work/header-values.json --final
    python3 paper/deliverables/hwp/fill_form.py check <saved.hwp> --dump-text <paragraphs.md>

``fill`` verifies the written cells by reading the output back. ``check`` reports sample terms in
BodyText and PrvText, and form paragraphs still in gray or italic. Neither replaces opening the
file in Hancom.
"""

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BODY = HERE.parent / "capstone-report-form-body.md"
CELL_MAP = HERE / "cell-map.json"
DEFAULT_SCRIPTS = Path.home() / (
    ".claude/plugins/cache/claw-hwp/claw-hwp/1.5.58/skills/hwp/scripts"
)
PLACEHOLDER = re.compile(r"\[(?:사람|대기|갱신)[^\]]*\]")
TAG_PARA_HEADER, TAG_PARA_TEXT, TAG_PARA_CHAR_SHAPE, TAG_LIST_HEADER = 66, 67, 68, 72
TAG_CHAR_SHAPE = 21
RESULT_KEYS = ("R- (Research)", "P- (Product)", "SS- (Social-Service)")
LINKAGE_BLOCK = "■ 산학/지역사회연계 활동 결과보고"


@dataclass(frozen=True)
class Line:
    """One form paragraph: its text and the optional leading part set in bold."""

    text: str
    bold: str = ""


def clean(text: str) -> str:
    return text.replace("`", "").strip()


def parse_line(block: str) -> Line:
    """Turn one body paragraph into a form line, keeping a leading **bold** run."""
    block = " ".join(part.strip() for part in block.splitlines())
    if block.startswith("### "):
        title = clean(block[4:])
        return Line(title, title)
    numbered = re.match(r"^(\d+\.\s)\*\*(.+?)\*\*\s*(.*)$", block)
    if numbered:
        prefix = clean(numbered.group(1) + numbered.group(2))
        return Line(f"{prefix} {clean(numbered.group(3))}".strip(), prefix)
    leading = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", block)
    if leading:
        prefix = clean(leading.group(1))
        return Line(f"{prefix} {clean(leading.group(2))}".strip(), prefix)
    return Line(clean(block))


def table_rows(section: str) -> list[list[str]]:
    rows = [row for row in section.splitlines() if row.startswith("| ")]
    return [[clean(cell) for cell in row.strip("|").split(" | ")] for row in rows[2:]]


def parse_body(path: Path) -> dict[str, str]:
    """Split the submitted part of the body file into sections by level-2 heading."""
    submitted = path.read_text(encoding="utf-8").split("\n---\n", 1)[0]
    sections: dict[str, str] = {}
    for part in re.split(r"^## ", submitted, flags=re.M)[1:]:
        heading, _, text = part.partition("\n")
        heading = re.sub(r"\s*\(방식:.*\)$", "", heading.strip())
        sections[heading] = text
    return sections


def prose_lines(section: str) -> list[Line]:
    """One line per blank-line separated block, and one per item of a numbered list."""
    lines: list[Line] = []
    for block in re.split(r"\n\s*\n", section.strip()):
        items = re.split(r"\n(?=\d+\.\s)", block) if re.match(r"\d+\.\s", block) else [block]
        lines.extend(parse_line(item) for item in items if item.strip())
    return lines


class Plan:
    """Accumulates the edit operations and the text expected in each cell."""

    def __init__(self, cell_map: dict) -> None:
        self.table = cell_map["table"]
        self.cell_ops: list[dict] = []
        self.delete_ops: list[dict] = []
        self.styled: list[Line] = []
        self.written: list[str] = []
        self.expected: dict[tuple[int, int], list[str]] = {}

    def set_text(self, row: int, col: int, text: str, **options: object) -> None:
        self.written.append(text)
        self.cell_ops.append(
            {"type": "set_cell_text", **self.table, "row": row, "col": col, "text": text, **options}
        )

    def cell(self, row: int, col: int, line: Line, restyle: bool = True) -> None:
        self.set_text(row, col, line.text)
        self.expected[(row, col)] = [line.text]
        if line.text and restyle:
            self.styled.append(line)

    def block(self, row: int, paragraphs: int, keep_first: int, lines: list[Line]) -> None:
        if keep_first + len(lines) > paragraphs:
            raise SystemExit(
                f"row {row}: {len(lines)} lines exceed {paragraphs - keep_first} slots"
            )
        for index in range(paragraphs - 1, keep_first + len(lines) - 1, -1):
            self.set_text(row, 0, "", cell_para=index)
        if not lines:
            self.set_text(row, 0, "", cell_para=keep_first, collapse=True)
        for index, line in enumerate(lines):
            last = {"collapse": True} if index == len(lines) - 1 else {}
            self.set_text(row, 0, line.text, cell_para=keep_first + index, **last)
            self.styled.append(line)
        self.expected[(row, 0)] = [line.text for line in lines]


def resolve_project_type(cell_map: dict, value: str | None) -> str | None:
    """Return the form row name. A 비융합/융합 prefix must agree with that row's group.

    Messages omit the entered value, which comes from the personal header file.
    """
    if not value:
        return None
    match = re.match(r"^(비융합|융합)[\s·:/-]*", value)
    name = value[match.end() :] if match else value
    if name not in cell_map["project_type_rows"]:
        raise SystemExit("project type is not a form option name")
    if match and name not in cell_map["project_type_groups"][match.group(1)]:
        raise SystemExit("project type prefix does not match the form group of that option")
    return name


def build_plan(cell_map: dict, sections: dict[str, str], values: dict[str, str]) -> Plan:
    plan = Plan(cell_map)

    header = {row[0]: row[1] for row in table_rows(sections["머리 정보"])}
    for name, (row, col) in cell_map["header"].items():
        # "" means not given yet (keep the placeholder); null means the cell stays empty.
        # Once any result type is filled, the empty result types are simply not applicable.
        given = values.get(name, "")
        if name in RESULT_KEYS and given == "" and any(values.get(key) for key in RESULT_KEYS):
            given = None
        # Only sample-styled header cells need restyling; a short value in a black cell such as
        # the class number could not be a unique style target anyway.
        restyle = name in cell_map["header_gray"]
        plan.cell(row, col, Line("" if given is None else (given or header[name])), restyle)

    project_type = resolve_project_type(cell_map, values.get("프로젝트 유형"))
    for name, row in cell_map["project_type_rows"].items():
        # The mark keeps the form's own shape: "○" also occurs in a label, so it cannot be a target.
        mark = "○" if name == project_type else ""
        plan.set_text(row, cell_map["project_type_col"], mark)

    for title, spec in cell_map["blocks"].items():
        lines = prose_lines(sections[title])
        if title == LINKAGE_BLOCK and project_type in cell_map["linkage_not_required"]:
            lines = []
        plan.block(spec["row"], spec["paragraphs"], spec["keep_first"], lines)

    titles = [row[2] for row in table_rows(sections["■ 결과물 사진"])]
    photo = cell_map["photo"]
    numbered = [f"그림 {number}. {title}" for number, title in enumerate(titles, start=1)]
    # The form cell has two paragraphs: the note line and the photo titles (forced line breaks).
    joined = "\n".join(numbered)
    plan.set_text(photo["row"], 0, "", cell_para=1)
    plan.set_text(photo["row"], 0, joined, collapse=True)
    plan.styled.extend(Line(text) for text in numbered)
    plan.expected[(photo["row"], 0)] = numbered

    delete_rows: list[int] = []
    for key, section in (
        ("ai_table", "■ 생성형 AI 사용 결과"),
        ("schedule_table", "■ 학기 일정과 연계된 활용 결과"),
    ):
        spec = cell_map[key]
        rows = table_rows(sections[section])
        if len(rows) > spec["rows"]:
            raise SystemExit(f"{section}: {len(rows)} rows exceed {spec['rows']}")
        for index, row in enumerate(rows):
            for col, text in zip(spec["cols"], row[1:], strict=True):
                plan.cell(spec["first_row"] + index, col, Line(text))
        delete_rows += range(spec["first_row"] + len(rows), spec["first_row"] + spec["rows"])
    plan.delete_ops = [
        {"type": "delete_table_row", **plan.table, "row": row}
        for row in sorted(delete_rows, reverse=True)
    ]
    return plan


def placeholders_written(plan: Plan) -> list[str]:
    """Placeholders in every text the plan writes, including cells that are not restyled."""
    return sorted({match for text in plan.written for match in PLACEHOLDER.findall(text)})


def reject_markup(plan: Plan) -> None:
    """Hancom shows markup literally, so a leftover marker must stop the build."""
    for index, text in enumerate(plan.written):
        if "**" in text or "`" in text:
            raise SystemExit(f"markdown left in form text: edit {index} ({len(text)} chars)")


def style_ops(plan: Plan) -> list[dict]:
    """Black upright text for every written line, plus bold lead-ins.

    apply_text_style changes the first match in the document, so a target must occur in one line.
    """
    texts = [line.text for line in plan.styled]
    operations: list[dict] = []
    # Messages give positions only: these lines can hold personal header values.
    for index, line in enumerate(plan.styled):
        if sum(line.text in text for text in texts) != 1:
            raise SystemExit(f"style target {index} is not unique ({len(line.text)} chars)")
        operations.append(
            {"type": "apply_text_style", "target": line.text, "color": "#000000", "italic": False}
        )
    for index, line in enumerate(plan.styled):
        if line.bold:
            if sum(line.bold in text for text in texts) != 1:
                raise SystemExit(f"bold target {index} is not unique ({len(line.bold)} chars)")
            operations.append(
                {"type": "apply_text_style", "target": line.bold, "bold": True, "italic": False}
            )
    return operations


def run_create(scripts: Path, path: Path, operations: list[dict]) -> None:
    payload = json.dumps({"path": str(path), "operations": operations}, ensure_ascii=False)
    done = subprocess.run(
        ["node", str(scripts / "create.js")], input=payload, capture_output=True, text=True
    )
    result = json.loads(done.stdout) if done.stdout.strip() else {}
    if result.get("status") != "success":
        raise SystemExit(f"create.js failed: {result or done.stderr}")


def read_cells(scripts: Path, path: Path, table_index: int = 2) -> list[dict]:
    done = subprocess.run(
        ["node", str(scripts / "extract_text.js"), "--inspect", "--with-cell-text", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)["tables"][table_index]["cells"]


def verify_written(scripts: Path, path: Path, plan: Plan) -> list[str]:
    """Compare the output cells with the plan; row deletion only shifts rows below the tables."""
    cells = read_cells(scripts, path)
    texts = {(cell["row"], cell["col"]): cell["text"] for cell in cells}
    problems = []
    for (row, col), lines in plan.expected.items():
        actual = texts.get((row, col))
        if actual is None or not actual.endswith("\n".join(lines)):
            problems.append(f"cell ({row},{col}) differs")
    return problems


def records(data: bytes) -> list[tuple[int, int, bytes]]:
    position = 0
    items = []
    while position < len(data):
        header = struct.unpack("<I", data[position : position + 4])[0]
        position += 4
        tag, level, size = header & 0x3FF, (header >> 10) & 0x3FF, header >> 20
        if size == 0xFFF:
            size = struct.unpack("<I", data[position : position + 4])[0]
            position += 4
        items.append((tag, level, data[position : position + size]))
        position += size
    return items


def paragraph_text(payload: bytes) -> str:
    """Decode PARA_TEXT, skipping the 8-unit inline and extended control characters."""
    units = struct.unpack(f"<{len(payload) // 2}H", payload[: len(payload) // 2 * 2])
    text: list[str] = []
    index = 0
    simple_controls = {10, 13, 24, 25, 26, 27, 28, 29, 30, 31}
    while index < len(units):
        unit = units[index]
        if unit >= 32:
            text.append(chr(unit))
            index += 1
        elif unit in simple_controls:
            text.append("\n" if unit in {10, 13} else " ")
            index += 1
        else:
            index += 8
    return "".join(text)


def check_saved(scripts: Path, path: Path, cell_map: dict, dump_text: Path | None = None) -> int:
    """Report sample terms per stream and leftover sample styling. Returns the problem count."""
    with tempfile.TemporaryDirectory() as temp:
        streams = Path(temp)
        subprocess.run(
            [
                "node",
                str(HERE / "dump_hwp_streams.cjs"),
                str(scripts / "vendor/cfb/cfb.js"),
                str(path),
                temp,
            ],
            check=True,
        )
        header = (streams / "FileHeader").read_bytes()
        compressed = bool(struct.unpack("<I", header[36:40])[0] & 1)

        def stream(name: str) -> bytes:
            raw = (streams / name).read_bytes()
            return zlib.decompress(raw, -15) if compressed else raw

        section = records(stream("Section0"))
        body_text = "\n".join(
            paragraph_text(payload) for tag, _, payload in section if tag == TAG_PARA_TEXT
        )
        preview = (streams / "PrvText").read_bytes().decode("utf-16le", "ignore")
        shapes = [
            payload for tag, _, payload in records(stream("DocInfo")) if tag == TAG_CHAR_SHAPE
        ]

    if dump_text:
        # Paragraph boundaries are real here, unlike the cell-joined markdown extract.
        dump_text.write_text(
            "\n\n".join(line for line in body_text.split("\n") if line.strip()) + "\n",
            encoding="utf-8",
        )

    problems = 0
    for name, text in (("BodyText", body_text), ("PrvText", preview)):
        hits = {term: text.count(term) for term in cell_map["sample_terms"] if term in text}
        print(f"{name}: sample terms {hits or '0건'}")
        problems += len(hits)
    markup = body_text.count("**")
    print(f"BodyText: markdown markers {markup or '0건'}")
    problems += markup
    placeholders = sorted(set(PLACEHOLDER.findall(body_text)))
    print(f"BodyText: placeholders {placeholders or '0건'}")
    problems += len(placeholders)

    styled = 0
    current = b""
    paragraph = 0
    for tag, _, payload in section:
        if tag == TAG_PARA_TEXT:
            current = payload
            paragraph += 1
        elif tag == TAG_PARA_CHAR_SHAPE and current:
            # A run holding only control characters (line break, paragraph mark) shows no glyph.
            units = struct.unpack(f"<{len(current) // 2}H", current[: len(current) // 2 * 2])
            runs = [
                struct.unpack("<II", payload[offset : offset + 8])
                for offset in range(0, len(payload), 8)
            ]
            for index, (start, shape_id) in enumerate(runs):
                end = runs[index + 1][0] if index + 1 < len(runs) else len(units)
                shape = shapes[shape_id]
                italic = bool(struct.unpack("<I", shape[46:50])[0] & 1)
                red, green, blue = shape[52:55]
                gray = red == green == blue and 0x80 <= red < 0xF0
                visible = any(unit >= 32 for unit in units[start:end])
                if visible and (italic or gray):
                    styled += 1
                    print(f"  gray/italic: paragraph record {paragraph}, {len(units)} units")
                    break
            current = b""
    print(f"gray or italic paragraphs: {styled}")
    return problems + styled


def fill(args: argparse.Namespace, cell_map: dict) -> None:
    digest = hashlib.sha256(args.template.read_bytes()).hexdigest()
    if digest != cell_map["template_sha256"]:
        raise SystemExit(f"template hash {digest} does not match cell-map.json")
    values = (
        json.loads(args.header_values.read_text(encoding="utf-8")) if args.header_values else {}
    )
    plan = build_plan(cell_map, parse_body(args.body), values)
    reject_markup(plan)
    leftovers = placeholders_written(plan)
    if args.final and leftovers:
        raise SystemExit(f"--final refuses placeholders: {leftovers}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    styles = style_ops(plan)
    shutil.copyfile(args.template, args.out)
    run_create(args.scripts, args.out, plan.cell_ops)
    run_create(args.scripts, args.out, styles)
    problems = verify_written(args.scripts, args.out, plan)
    run_create(args.scripts, args.out, plan.delete_ops)
    if problems:
        raise SystemExit("read-back failed:\n" + "\n".join(problems))
    print(f"{args.out}: {len(plan.cell_ops)} cell edits, {len(styles)} style edits, read-back OK")
    print(f"placeholders left: {leftovers or '0건'}")
    print(f"sha256 {hashlib.sha256(args.out.read_bytes()).hexdigest()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripts", type=Path, default=DEFAULT_SCRIPTS)
    commands = parser.add_subparsers(dest="command", required=True)
    fill_parser = commands.add_parser("fill")
    fill_parser.add_argument("--template", type=Path, required=True)
    fill_parser.add_argument("--out", type=Path, required=True)
    fill_parser.add_argument("--body", type=Path, default=DEFAULT_BODY)
    fill_parser.add_argument("--header-values", type=Path)
    fill_parser.add_argument("--final", action="store_true")
    check_parser = commands.add_parser("check")
    check_parser.add_argument("path", type=Path)
    check_parser.add_argument("--dump-text", type=Path, help="write BodyText paragraphs to a file")
    args = parser.parse_args()

    cell_map = json.loads(CELL_MAP.read_text(encoding="utf-8"))
    if args.command == "fill":
        fill(args, cell_map)
    elif check_saved(args.scripts, args.path, cell_map, args.dump_text):
        sys.exit(1)


if __name__ == "__main__":
    main()
