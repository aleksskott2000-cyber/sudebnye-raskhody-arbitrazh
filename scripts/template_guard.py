#!/usr/bin/env python3
"""Check that a generated DOCX preserves the selected source template in place."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
PROTECTED_EXACT = (
    "word/styles.xml",
    "word/numbering.xml",
    "word/settings.xml",
    "word/fontTable.xml",
    "word/webSettings.xml",
    "word/theme/theme1.xml",
)
DEFAULT_FORBIDDEN = (
    "Истец",
    "Ответчик",
    "Договор",
    "Продавец",
    "Покупатель",
    "Исполнитель",
    "Заказчик",
    "Стороны",
    "Заявитель",
    "Представитель",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def load_package(path: Path) -> dict[str, bytes]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with zipfile.ZipFile(path) as package:
        if package.testzip() is not None:
            raise ValueError(f"Damaged DOCX ZIP: {path}")
        return {name: package.read(name) for name in package.namelist()}


def xml_root(parts: dict[str, bytes], name: str) -> ET.Element:
    return ET.fromstring(parts[name])


def visible_text(parts: dict[str, bytes]) -> str:
    names = ["word/document.xml"]
    names.extend(sorted(name for name in parts if re.fullmatch(r"word/(header|footer)\d+\.xml", name)))
    fragments = []
    for name in names:
        root = xml_root(parts, name)
        fragments.extend(node.text or "" for node in root.findall(f".//{W}t"))
    return "\n".join(fragments)


def structure_fingerprint(data: bytes) -> str:
    root = ET.fromstring(data)
    clone = copy.deepcopy(root)
    for node in clone.iter():
        if node.tag in {f"{W}t", f"{W}instrText", f"{W}delText"}:
            node.text = ""
    return digest(ET.tostring(clone, encoding="utf-8"))


def element_fingerprints(root: ET.Element, xpath: str) -> list[str]:
    return [digest(ET.tostring(node, encoding="utf-8")) for node in root.findall(xpath)]


def compare(template: Path, output: Path, allow_paragraph_change: bool, required: list[str], forbidden: list[str]) -> dict:
    source = load_package(template)
    result = load_package(output)
    failures: list[str] = []
    warnings: list[str] = []

    for name in PROTECTED_EXACT:
        if name in source and name not in result:
            failures.append(f"Protected part was removed: {name}")
        elif name in source and source[name] != result[name]:
            failures.append(f"Protected formatting part changed: {name}")

    source_media = {name: digest(data) for name, data in source.items() if name.startswith("word/media/")}
    result_media = {name: digest(data) for name, data in result.items() if name.startswith("word/media/")}
    for name, checksum in source_media.items():
        if result_media.get(name) != checksum:
            failures.append(f"Template media/signature was removed or changed: {name}")

    structural_parts = sorted(
        name for name in source if re.fullmatch(r"word/(header|footer)\d+\.xml", name)
    )
    for name in structural_parts:
        if name not in result:
            failures.append(f"Header/footer part was removed: {name}")
        elif structure_fingerprint(source[name]) != structure_fingerprint(result[name]):
            failures.append(f"Header/footer structure was rebuilt: {name}")

    source_doc = xml_root(source, "word/document.xml")
    result_doc = xml_root(result, "word/document.xml")

    source_sections = element_fingerprints(source_doc, f".//{W}sectPr")
    result_sections = element_fingerprints(result_doc, f".//{W}sectPr")
    if source_sections != result_sections:
        failures.append("Page sections, margins, orientation, or header/footer links changed")

    source_tables = source_doc.findall(f".//{W}tbl")
    result_tables = result_doc.findall(f".//{W}tbl")
    if len(source_tables) != len(result_tables):
        failures.append(f"Table count changed: {len(source_tables)} -> {len(result_tables)}")
    else:
        for index, (left, right) in enumerate(zip(source_tables, result_tables), start=1):
            left_parts = element_fingerprints(left, f"./{W}tblPr") + element_fingerprints(left, f"./{W}tblGrid")
            right_parts = element_fingerprints(right, f"./{W}tblPr") + element_fingerprints(right, f"./{W}tblGrid")
            if left_parts != right_parts:
                failures.append(f"Table {index} properties or grid changed")

    source_paragraphs = source_doc.findall(f".//{W}p")
    result_paragraphs = result_doc.findall(f".//{W}p")
    if len(source_paragraphs) != len(result_paragraphs):
        message = f"Paragraph count changed: {len(source_paragraphs)} -> {len(result_paragraphs)}"
        (warnings if allow_paragraph_change else failures).append(message)
    else:
        for index, (left, right) in enumerate(zip(source_paragraphs, result_paragraphs), start=1):
            left_props = element_fingerprints(left, f"./{W}pPr")
            right_props = element_fingerprints(right, f"./{W}pPr")
            if left_props != right_props:
                failures.append(f"Paragraph {index} formatting changed")

    text = visible_text(result)
    for phrase in required:
        if phrase not in text:
            failures.append(f"Required text is missing: {phrase}")
    all_forbidden = list(DEFAULT_FORBIDDEN) + forbidden
    for phrase in all_forbidden:
        if re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", text):
            failures.append(f"Forbidden text/capitalization found: {phrase}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "template": str(template.resolve()),
        "output": str(output.resolve()),
        "checks": {
            "protected_formatting_parts": len(PROTECTED_EXACT),
            "template_media": len(source_media),
            "headers_and_footers": len(structural_parts),
            "sections": len(source_sections),
            "tables": len(source_tables),
            "paragraphs_template": len(source_paragraphs),
            "paragraphs_output": len(result_paragraphs),
        },
        "warnings": warnings,
        "failures": failures,
        "visual_comparison_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("statement", "act"), required=True)
    parser.add_argument("--require", action="append", default=[])
    parser.add_argument("--forbid", action="append", default=[])
    parser.add_argument("--allow-paragraph-count-change", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    try:
        report = compare(
            args.template,
            args.output,
            args.allow_paragraph_count_change,
            args.require,
            args.forbid,
        )
    except Exception as exc:
        report = {"status": "FAIL", "failures": [f"{type(exc).__name__}: {exc}"]}

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

