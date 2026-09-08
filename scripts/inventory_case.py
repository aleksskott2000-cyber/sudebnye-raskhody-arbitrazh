#!/usr/bin/env python3
"""Create a machine-readable inventory of every material in a case folder."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
EXCLUDED_DIRS = {".git", "__pycache__", "work", "qa", ".qa", ".rendered"}
TEMPLATE_MARKERS = (
    "исходное заявление и акт оказанных услуг",
    "исходное заявление",
    "исходный акт",
    "исходник",
    "образец заявления",
    "образец акта",
    "шаблон заявления",
    "шаблон акта",
)
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_text(path: Path, limit: int) -> tuple[str, str]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "utf-16"):
        try:
            return data.decode(encoding)[:limit], encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")[:limit], "utf-8-replace"


def docx_details(path: Path, limit: int) -> dict:
    result: dict = {"format": "docx", "paragraphs": 0, "tables": 0, "text": ""}
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        result["has_headers"] = any(name.startswith("word/header") for name in names)
        result["has_footers"] = any(name.startswith("word/footer") for name in names)
        result["media_files"] = sorted(name for name in names if name.startswith("word/media/"))
        root = ET.fromstring(package.read("word/document.xml"))
    result["paragraphs"] = len(root.findall(f".//{{{W_NS}}}p"))
    result["tables"] = len(root.findall(f".//{{{W_NS}}}tbl"))
    fragments = [node.text or "" for node in root.findall(f".//{{{W_NS}}}t")]
    result["text"] = "\n".join(fragment for fragment in fragments if fragment).strip()[:limit]
    return result


def pdf_details(path: Path, limit: int) -> dict:
    result: dict = {"format": "pdf", "page_count": None, "text": "", "needs_visual_review": True}
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        pages = []
        weak_pages = []
        for index, page in enumerate(reader.pages, start=1):
            extracted = (page.extract_text() or "").strip()
            pages.append(extracted)
            if len(extracted) < 40:
                weak_pages.append(index)
        result["page_count"] = len(reader.pages)
        result["text"] = "\n\n".join(pages)[:limit]
        result["weak_text_pages"] = weak_pages
        result["needs_visual_review"] = bool(weak_pages)
    except Exception as exc:  # PDF still remains in inventory for manual review.
        result["extraction_error"] = f"{type(exc).__name__}: {exc}"
    return result


def image_details(path: Path) -> dict:
    result: dict = {"format": "image", "needs_visual_review": True}
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            result.update({"width": image.width, "height": image.height, "mode": image.mode})
    except Exception as exc:
        result["inspection_error"] = f"{type(exc).__name__}: {exc}"
    return result


def inspect_file(path: Path, root: Path, limit: int) -> dict:
    relative = path.relative_to(root).as_posix()
    lowered = relative.casefold()
    item: dict = {
        "path": relative,
        "extension": path.suffix.casefold(),
        "size": path.stat().st_size,
        "sha256": sha256(path),
        "template_candidate": any(marker in lowered for marker in TEMPLATE_MARKERS),
    }
    try:
        if path.suffix.casefold() == ".docx":
            item.update(docx_details(path, limit))
        elif path.suffix.casefold() == ".pdf":
            item.update(pdf_details(path, limit))
        elif path.suffix.casefold() in IMAGE_EXTENSIONS:
            item.update(image_details(path))
        elif path.suffix.casefold() in TEXT_EXTENSIONS:
            text, encoding = read_text(path, limit)
            item.update({"format": "text", "encoding": encoding, "text": text})
        else:
            item["format"] = "binary-or-unsupported"
    except Exception as exc:
        item["inspection_error"] = f"{type(exc).__name__}: {exc}"
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="case folder")
    parser.add_argument("--out", type=Path, help="JSON output path; stdout if omitted")
    parser.add_argument("--max-text-chars", type=int, default=200_000)
    args = parser.parse_args()

    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"Folder does not exist: {root}")
    output_path = args.out.expanduser().resolve() if args.out else None

    files = []
    for path in sorted(root.rglob("*"), key=lambda value: value.as_posix().casefold()):
        if not path.is_file() or any(part.casefold() in EXCLUDED_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        if output_path and path.resolve() == output_path:
            continue
        files.append(inspect_file(path, root, args.max_text_chars))

    report = {
        "schema_version": 1,
        "root": str(root),
        "file_count": len(files),
        "template_candidates": [item["path"] for item in files if item["template_candidate"]],
        "visual_review_required": [item["path"] for item in files if item.get("needs_visual_review")],
        "files": files,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"Inventory written: {output_path}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
