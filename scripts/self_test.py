#!/usr/bin/env python3
"""Verify the portable skill package, embedded sources, and guard scripts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def main() -> int:
    failures = []
    manifest_path = ROOT / "assets" / "template-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for item in manifest["templates"]:
        path = ROOT / "assets" / item["file"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            failures.append(f"Template checksum mismatch: {path}")
        preview = ROOT / "assets" / item["preview"]
        if not preview.is_file() or preview.stat().st_size == 0:
            failures.append(f"Template preview missing: {preview}")

    for item in manifest["embedded_instructions"]:
        path = (ROOT / "assets" / item["file"]).resolve()
        if not path.is_file() or sha256(path) != item["sha256"]:
            failures.append(f"Embedded instruction checksum mismatch: {path}")

    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if "TODO" in skill_text or "Пользовательский образец всегда выше встроенного" not in skill_text:
        failures.append("SKILL.md is incomplete or lacks the precedence rule")

    with tempfile.TemporaryDirectory(prefix="sudebnye-raskhody-test-") as temp_dir:
        temp = Path(temp_dir)
        sample = temp / "Исходное заявление и акт оказанных услуг"
        sample.mkdir()
        (sample / "факт.txt").write_text("Проверка материалов дела", encoding="utf-8")
        inventory_path = temp / "inventory.json"
        inventory = run(str(ROOT / "scripts" / "inventory_case.py"), str(temp), "--out", str(inventory_path))
        if inventory.returncode != 0 or not inventory_path.is_file():
            failures.append(f"Inventory test failed: {inventory.stderr or inventory.stdout}")
        else:
            data = json.loads(inventory_path.read_text(encoding="utf-8"))
            if data["file_count"] != 1 or not data["template_candidates"]:
                failures.append("Inventory did not detect all sample files or the user template folder")

    for kind, name in (("statement", "statement-template.docx"), ("act", "act-template.docx")):
        template = ROOT / "assets" / name
        guard = run(
            str(ROOT / "scripts" / "template_guard.py"),
            "--template",
            str(template),
            "--output",
            str(template),
            "--kind",
            kind,
        )
        if guard.returncode != 0:
            failures.append(f"Template guard failed for {name}: {guard.stdout or guard.stderr}")

    if failures:
        print("SELF-TEST FAILED", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("SELF-TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

