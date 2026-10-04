"""Validate planning metadata only; no engine imports, target execution or IO outside files.

Implements the JSON Schema keywords used by catalog.schema.json (not a general
JSON Schema evaluator), plus catalog-wide ID, link and qualification checks.
Run from any directory with Python's standard library.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

DIRECTORY = Path(__file__).resolve().parent
OPERATORS = {
    "add_entry",
    "remove_entry",
    "duplicate_entry",
    "reorder_entries",
    "mutate_path",
    "add_hardlink",
    "add_symlink",
    "mutate_link_target",
    "component_recombination_planned",
    "backslash_components_planned",
    "isolated_cwd_planned",
    "configured_root_unresolved",
    "selected_member_cli_unresolved",
    "unsupported_equivalent_names",
    "unsupported_race_control",
    "unsupported_pax_gnu_encoding",
    "unsupported_oci_title_mutation",
    "unsupported_existing_tree_setup",
}


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON object key")
    return result


def read_json(path: Path) -> dict:
    def reject_constant(value: str) -> None:
        raise ValueError(f"nonfinite JSON constant: {value}")

    result = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(result, dict):
        raise ValueError(f"{path}: root must be an object")
    return result


def validate_value(value: object, schema: dict, location: str) -> None:
    """Check the schema's type/enum/shape/string/array constraints recursively."""
    actual_type = {
        dict: "object",
        list: "array",
        str: "string",
        int: "integer",
        bool: "boolean",
        type(None): "null",
    }.get(type(value))
    wanted = schema["type"]
    allowed = wanted if isinstance(wanted, list) else [wanted]
    if actual_type not in allowed:
        raise ValueError(f"{location}: expected {allowed}, got {actual_type}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{location}: unsupported value {value!r}")
    if isinstance(value, dict):
        properties = schema["properties"]
        missing = set(schema["required"]) - value.keys()
        unknown = value.keys() - properties.keys()
        if missing or (unknown and not schema["additionalProperties"]):
            raise ValueError(f"{location}: missing {sorted(missing)}, unknown {sorted(unknown)}")
        for key, item in value.items():
            validate_value(item, properties[key], f"{location}.{key}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{location}: too few items")
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            if len(serialized) != len(set(serialized)):
                raise ValueError(f"{location}: duplicate array item")
        for index, item in enumerate(value):
            validate_value(item, schema["items"], f"{location}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{location}: empty string")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise ValueError(f"{location}: invalid string format")


def validate_catalog(catalog: dict, schema: dict) -> None:
    validate_value(catalog, schema, "catalog")
    identifiers: set[str] = set()
    for record in catalog["benchmarks"]:
        identifier = record["benchmark_id"]
        if identifier in identifiers:
            raise ValueError(f"duplicate benchmark ID: {identifier}")
        identifiers.add(identifier)
        expected_status = {
            "primary": "selected_pending_qualification",
            "secondary": "secondary_pending",
            "excluded": "excluded_v1",
        }[record["selection"]]
        if record["status"] != expected_status:
            raise ValueError(f"{identifier}: selection/status mismatch")
        if not (DIRECTORY / record["analysis_document"]).is_file():
            raise ValueError(f"{identifier}: missing analysis document")
        if set(record["required_mutations"]) - OPERATORS:
            raise ValueError(f"{identifier}: undocumented mutation/setup capability")
        for source in record["sources"]:
            parsed = urlsplit(source["url"])
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError(f"{identifier}: invalid source URL")
        if record["selection"] == "primary":
            if any(
                not isinstance(version, str) or re.fullmatch(r"\d+\.\d+\.\d+", version) is None
                for version in record["selected_pair"].values()
            ):
                raise ValueError(f"{identifier}: primary pair requires exact release versions")
            inspected_kinds = {
                source["source_type"] for source in record["sources"] if source["inspected"]
            }
            if not {"upstream_advisory", "patch"} <= inspected_kinds:
                raise ValueError(f"{identifier}: primary requires inspected advisory and patch")


def main() -> int:
    try:
        catalog = read_json(DIRECTORY / "catalog-v1.json")
        validate_catalog(catalog, read_json(DIRECTORY / "catalog.schema.json"))
    except (OSError, ValueError, KeyError) as error:
        print(f"Catalog check: FAIL: {error}")
        return 1
    print(f"Catalog check: PASS ({len(catalog['benchmarks'])} planning records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
