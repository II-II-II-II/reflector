"""
Step 1 of ingestion: figure out the real shape of your Journey export
before we commit to a parser. Journey's JSON schema has drifted across
app versions, so we verify against your actual data rather than guessing.

Privacy note: this script is intentionally content-blind. It reports
field names, types, and lengths — never actual text, dates, coordinates,
or file paths. Safe to run and share the output anywhere, including in
this chat, since no journal content ever appears in stdout.

Usage:
    python -m reflector.inspect_export
    (drop your Journey export .zip, or its unzipped contents, into data/raw/ first)
"""

import json
import sys
import zipfile
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
EXTRACT_DIR = RAW_DIR / "extracted"


def extract_zips() -> None:
    zips = list(RAW_DIR.glob("*.zip"))
    if not zips:
        return
    EXTRACT_DIR.mkdir(exist_ok=True)
    for z in zips:
        print(f"Extracting {z.name} -> {EXTRACT_DIR}")
        with zipfile.ZipFile(z) as f:
            f.extractall(EXTRACT_DIR)


def find_json_files() -> list[Path]:
    search_root = EXTRACT_DIR if EXTRACT_DIR.exists() else RAW_DIR
    return sorted(search_root.rglob("*.json"))


def scalar_shape(value) -> str:
    """Describe a leaf value's type/shape without ever revealing the value itself."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        digits = len(str(abs(value)))
        if digits >= 12:
            return "int (epoch-ms timestamp range)"
        if digits == 10:
            return "int (epoch-seconds timestamp range)"
        return f"int ({digits} digits)"
    if isinstance(value, float):
        if abs(value) <= 180:
            return "float (lat/lon coordinate range)"
        return "float"
    if isinstance(value, str):
        looks_html = "<" in value and ">" in value
        return f"str (len={len(value)}{', html-tagged' if looks_html else ''})"
    return type(value).__name__


def describe(value, depth=0, max_depth=3) -> str:
    indent = "  " * depth
    if isinstance(value, dict):
        lines = [f"{indent}dict, keys: {list(value.keys())}"]
        if depth < max_depth:
            for k, v in value.items():
                child = describe(v, depth + 1, max_depth)
                lines.append(f"{indent}  .{k}: {child.strip()}")
        return "\n".join(lines)
    if isinstance(value, list):
        head = f"list of {len(value)}"
        if value:
            head += f", each: {describe(value[0], depth, max_depth).strip()}"
        else:
            head += " (empty)"
        return head
    return scalar_shape(value)


def main() -> None:
    extract_zips()
    json_files = find_json_files()

    if not json_files:
        print(f"No .json files found under {RAW_DIR}.")
        print("Drop your Journey export .zip (or its unzipped contents) into data/raw/ and re-run.")
        sys.exit(1)

    print(f"Found {len(json_files)} JSON file(s) total.\n")

    # Union of top-level keys seen across a sample, to catch schema drift
    # across entries without printing any entry's actual content.
    sample = json_files[:: max(1, len(json_files) // 25)][:25]
    all_keys: dict[str, int] = {}
    for jf in sample:
        try:
            data = json.loads(jf.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            for k in data.keys():
                all_keys[k] = all_keys.get(k, 0) + 1

    print(f"Top-level keys seen across {len(sample)} sampled files (key: occurrence count):")
    for k, count in sorted(all_keys.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {count}/{len(sample)}")
    print()

    print("Full structural shape of one representative entry:\n")
    first = json.loads(json_files[0].read_text())
    print(describe(first))


if __name__ == "__main__":
    main()
