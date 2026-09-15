#!/usr/bin/env python3
"""Normalize a LinkedIn data export ZIP/directory (plus local writing files).

Stdlib only. Produces workspace-local evidence under <output>/raw/ and a manifest.
The script intentionally does not call LinkedIn, scrape pages, or publish anything.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

TEXT_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".txt", ".md"}
MAX_TEXT_CHARS = 200_000
DEFAULT_MAX_FILE_BYTES = 25_000_000
DEFAULT_MAX_TOTAL_BYTES = 250_000_000
DEFAULT_MAX_FILES = 2_000
DEFAULT_MAX_RECORDS = 500_000
SENSITIVE_CATEGORIES = {"messages", "connections"}

CATEGORY_HINTS = {
    "profile": ["profile", "perfil"],
    "positions": ["position", "positions", "experience", "experiences", "employment", "cargo", "puestos"],
    "posts": ["share", "shares", "post", "posts", "ugc", "publicaciones"],
    "comments": ["comment", "comments", "comentarios"],
    "replies": ["reply", "replies", "respuesta", "respuestas"],
    "reactions": ["reaction", "reactions", "likes", "like", "reacciones"],
    "messages": ["message", "messages", "mensajes"],
    "skills": ["skill", "skills", "aptitudes"],
    "education": ["education", "educacion", "education_history"],
    "certifications": ["certification", "certifications", "certificados"],
    "connections": ["connection", "connections", "contacts", "contactos"],
}

FIELD_HINTS = {
    "date": ["date", "time", "timestamp", "created", "fecha"],
    "text": ["comment", "text", "content", "sharecommentary", "description", "message", "body", "comentario", "texto", "contenido"],
    "url": ["url", "link", "permalink", "enlace"],
    "reaction": ["reaction", "type", "like", "reaccion"],
    "title": ["title", "headline", "position", "titulo", "cargo"],
    "company": ["company", "organization", "employer", "empresa", "organizacion"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ").strip()
    text = re.sub(r"[ \t]+", " ", text)
    return text


def normalize_date(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    iso_candidate = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_candidate).isoformat()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def classify_filename(name: str) -> str:
    stem = Path(name).stem.lower()
    for category, hints in CATEGORY_HINTS.items():
        if any(h in stem for h in hints):
            return category
    return "other"


def classify_headers(headers: List[str]) -> str:
    keys = {norm_key(header) for header in headers if header}
    joined = " ".join(keys)
    if any(token in joined for token in ("sharecommentary", "sharelink", "posturl")):
        return "posts"
    if any(token in joined for token in ("commentary", "commenturl")):
        return "comments"
    if "reactiontype" in joined or ({"type", "link"} <= keys and "reaction" in joined):
        return "reactions"
    if any(token in joined for token in ("companyname", "employername", "positiontitle")):
        return "positions"
    return "other"


def find_field(row: Dict[str, str], kind: str) -> str:
    hints = FIELD_HINTS[kind]
    normalized = {norm_key(k): v for k, v in row.items()}
    # exact-ish first
    for hint in hints:
        h = norm_key(hint)
        if h in normalized and clean_text(normalized[h]):
            return clean_text(normalized[h])
    # substring fallback
    for key, value in normalized.items():
        if any(norm_key(h) in key for h in hints) and clean_text(value):
            return clean_text(value)
    return ""


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def parse_csv(path: Path, category: str) -> Iterator[dict]:
    text = read_text_file(path)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if category == "other":
        category = classify_headers(reader.fieldnames or [])
    for idx, raw_row in enumerate(reader, start=2):
        row = {clean_text(k): clean_text(v) for k, v in (raw_row or {}).items() if k is not None}
        if not any(row.values()):
            continue
        yield normalize_record(row, category, path.name, idx)


def normalize_record(row: Dict[str, str], category: str, source_file: str, source_row: int) -> dict:
    text = find_field(row, "text")
    raw_date = find_field(row, "date")
    date = normalize_date(raw_date)
    url = find_field(row, "url")
    reaction = find_field(row, "reaction") if category == "reactions" else ""
    title = find_field(row, "title")
    company = find_field(row, "company")

    if not text and category in {"profile", "positions", "education", "skills", "certifications"}:
        # Keep a compact, readable rendering of structured profile rows.
        parts = [f"{k}: {v}" for k, v in row.items() if v]
        text = " | ".join(parts)

    authored = category in {"posts", "comments", "replies"}
    authorship = "user_export_semantics" if authored else "unknown"

    return {
        "category": category,
        "source_file": source_file,
        "source_row": source_row,
        "date": date,
        "date_raw": raw_date,
        "text": text,
        "url": url,
        "reaction": reaction,
        "title": title,
        "company": company,
        "authored_voice_candidate": authored and bool(text),
        "authorship": authorship,
        "authorship_reason": "LinkedIn activity export category" if authored else "Not established by category",
        "fields": row,
    }


def parse_json(path: Path, category: str) -> Iterator[dict]:
    text = read_text_file(path)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if path.suffix.lower() == ".jsonl":
            for idx, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    row = {str(k): clean_text(v) for k, v in item.items()}
                    yield normalize_record(row, category, path.name, idx)
        return

    items = payload if isinstance(payload, list) else [payload]
    for idx, item in enumerate(items, start=1):
        if isinstance(item, dict):
            row = {str(k): clean_text(v) for k, v in item.items()}
            yield normalize_record(row, category, path.name, idx)
        else:
            yield {
                "category": category,
                "source_file": path.name,
                "source_row": idx,
                "date": "",
                "text": clean_text(item),
                "url": "",
                "reaction": "",
                "title": "",
                "company": "",
                "authored_voice_candidate": False,
                "authorship": "unknown",
                "authorship_reason": "Unstructured JSON value",
                "fields": {"value": clean_text(item)},
            }


def parse_plain(path: Path, category: str) -> Iterator[dict]:
    text = read_text_file(path)[:MAX_TEXT_CHARS]
    if not text.strip():
        return
    yield {
        "category": category if category != "other" else "writing_sample",
        "source_file": path.name,
        "source_row": 1,
        "date": "",
        "text": text.strip(),
        "url": "",
        "reaction": "",
        "title": "",
        "company": "",
        "authored_voice_candidate": True,
        "authorship": "user_supplied",
        "authorship_reason": "Local writing sample explicitly supplied for ingestion",
        "fields": {"text": text.strip()},
    }


def extract_input(input_path: Path, max_files: int, max_total_bytes: int, max_file_bytes: int) -> Tuple[Path, tempfile.TemporaryDirectory | None]:
    if input_path.is_dir():
        return input_path, None
    if input_path.suffix.lower() == ".zip":
        temp = tempfile.TemporaryDirectory(prefix="linkedin-export-")
        try:
            with zipfile.ZipFile(input_path, "r") as zf:
                members = [m for m in zf.infolist() if not m.is_dir()]
                if len(members) > max_files:
                    raise ValueError(f"ZIP contains {len(members)} files; limit is {max_files}")
                total = sum(m.file_size for m in members)
                if total > max_total_bytes:
                    raise ValueError(f"ZIP expands to {total} bytes; limit is {max_total_bytes}")
                root = Path(temp.name).resolve()
                for member in members:
                    if member.file_size > max_file_bytes:
                        raise ValueError(f"ZIP member exceeds size limit: {member.filename}")
                    target = (root / member.filename).resolve()
                    if root != target and root not in target.parents:
                        raise ValueError(f"Unsafe ZIP path: {member.filename}")
                    unix_mode = member.external_attr >> 16
                    if (unix_mode & 0o170000) == 0o120000:
                        raise ValueError(f"ZIP symbolic links are not allowed: {member.filename}")
                zf.extractall(temp.name, members)
        except Exception:
            temp.cleanup()
            raise
        return Path(temp.name), temp
    return input_path.parent, None


def iter_input_files(input_path: Path, max_files: int, max_total_bytes: int, max_file_bytes: int) -> Tuple[List[Path], tempfile.TemporaryDirectory | None]:
    if input_path.is_file() and input_path.suffix.lower() in TEXT_EXTENSIONS:
        if input_path.stat().st_size > max_file_bytes:
            raise ValueError(f"File exceeds size limit: {input_path}")
        return [input_path], None
    root, temp = extract_input(input_path, max_files, max_total_bytes, max_file_bytes)
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS]
    if len(files) > max_files:
        raise ValueError(f"Input contains {len(files)} supported files; limit is {max_files}")
    oversized = [p for p in files if p.stat().st_size > max_file_bytes]
    if oversized:
        raise ValueError(f"File exceeds size limit: {oversized[0]}")
    total = sum(p.stat().st_size for p in files)
    if total > max_total_bytes:
        raise ValueError(f"Input contains {total} supported bytes; limit is {max_total_bytes}")
    return sorted(files), temp


def dedupe_key(record: dict) -> str:
    basis = "\n".join([
        record.get("category", ""),
        record.get("date", ""),
        record.get("text", ""),
        record.get("url", ""),
    ])
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()


def load_existing(jsonl_path: Path) -> Tuple[List[dict], set[str]]:
    records, keys = [], set()
    if not jsonl_path.exists():
        return records, keys
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        canonical = dedupe_key(rec)
        rec["record_id"] = canonical
        records.append(rec)
        keys.add(canonical)
    return records, keys


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def dataset_hash(records: List[dict]) -> str:
    digest = hashlib.sha256()
    for record_id in sorted(r.get("record_id", dedupe_key(r)) for r in records):
        digest.update(record_id.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_summary(records: List[dict], files: List[Path], raw_dir: Path) -> None:
    counts = Counter(r.get("category", "other") for r in records)
    voice = [r for r in records if r.get("authored_voice_candidate") and r.get("text")]
    dated = [r.get("date") for r in records if r.get("date")]

    lines = [
        "# LinkedIn ingestion summary",
        "",
        f"Generated: {utc_now()}",
        f"Records: {len(records)}",
        f"Voice candidates: {len(voice)}",
        f"Source files observed this run: {len(files)}",
        "",
        "## Record categories",
        "",
    ]
    for cat, count in counts.most_common():
        lines.append(f"- {cat}: {count}")
    if dated:
        lines += ["", "## Date strings observed", "", f"- first lexical value: {min(dated)}", f"- last lexical value: {max(dated)}"]

    lines += ["", "## Source files", ""]
    for path in files:
        lines.append(f"- {path.name} → {classify_filename(path.name)}")

    lines += [
        "",
        "## Interpretation guardrails",
        "",
        "- Posts/comments are voice candidates only when the export semantics indicate user-authored text.",
        "- Reactions indicate attention/interest, not agreement.",
        "- Profile/position rows are candidates for factual verification, not automatically approved claims.",
        "- Messages are retained only as raw context and are not treated as voice evidence by default.",
    ]
    atomic_write_text(raw_dir / "summary.md", "\n".join(lines) + "\n")


def write_voice_corpus(records: List[dict], raw_dir: Path) -> None:
    lines = ["# User-authored voice corpus", ""]
    for rec in records:
        if not rec.get("authored_voice_candidate") or not rec.get("text"):
            continue
        meta = " | ".join(x for x in [rec.get("category", ""), rec.get("date", ""), rec.get("source_file", "")] if x)
        lines += [f"## {meta}", "", rec["text"].strip(), ""]
    atomic_write_text(raw_dir / "voice-corpus.md", "\n".join(lines))


def ensure_identity_templates(output: Path) -> None:
    identity = output / "identity"
    identity.mkdir(parents=True, exist_ok=True)
    templates = {
        "voice-profile.md": "# Voice Profile\n\nStatus: not built yet. Analyze `.linkedin-content-engine/raw/voice-corpus.md` using the skill instructions.\n",
        "proof-library.md": "# Proof Library\n\nStatus: not built yet. Verify facts from normalized profile/position evidence before use.\n",
        "interest-map.md": "# Interest Map\n\nStatus: not built yet. Derive recurring topics with confidence and signal types.\n",
        "opinion-map.md": "# Opinion Map\n\nStatus: not built yet. Use only user-authored statements as opinion evidence.\n",
    }
    for name, content in templates.items():
        path = identity / name
        if not path.exists():
            atomic_write_text(path, content)

    content_dir = output / "content"
    content_templates = {
        "backlog.md": "# Content Backlog\n\n",
        "published-log.md": "# Published Log\n\n",
    }
    for name, content in content_templates.items():
        path = content_dir / name
        if not path.exists():
            atomic_write_text(path, content)

    research_dir = output / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    sources = research_dir / "sources.jsonl"
    if not sources.exists():
        atomic_write_text(sources, "")

    ignore = output / ".gitignore"
    if not ignore.exists():
        atomic_write_text(ignore, "*\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize LinkedIn export/local activity files for LinkedIn Content Engine.")
    parser.add_argument("input", help="LinkedIn export .zip, extracted directory, or local .csv/.json/.txt/.md file")
    parser.add_argument("--output", default=".linkedin-content-engine", help="Workspace state directory (default: .linkedin-content-engine)")
    parser.add_argument("--append", action="store_true", help="Append/dedupe against existing normalized records")
    parser.add_argument("--include-sensitive", action="store_true", help="Include messages and connections (requires explicit informed user request)")
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--max-records", type=int, default=DEFAULT_MAX_RECORDS)
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 2

    raw_dir = output / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (output / "content").mkdir(parents=True, exist_ok=True)

    try:
        files, temp = iter_input_files(input_path, args.max_files, args.max_total_bytes, args.max_file_bytes)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Input rejected: {exc}", file=sys.stderr)
        return 2
    try:
        existing, keys = load_existing(raw_dir / "normalized.jsonl") if args.append else ([], set())
        records = list(existing)
        run_files = []
        errors = []
        added = 0

        for path in files:
            category = classify_filename(path.name)
            if category in SENSITIVE_CATEGORIES and not args.include_sensitive:
                continue
            run_files.append(path)
            try:
                if path.suffix.lower() in {".csv", ".tsv"}:
                    iterator = parse_csv(path, category)
                elif path.suffix.lower() in {".json", ".jsonl"}:
                    iterator = parse_json(path, category)
                else:
                    iterator = parse_plain(path, category)
                for rec in iterator:
                    if len(records) >= args.max_records:
                        raise ValueError(f"Record limit reached: {args.max_records}")
                    if rec.get("category") in SENSITIVE_CATEGORIES and not args.include_sensitive:
                        continue
                    rid = dedupe_key(rec)
                    if rid in keys:
                        continue
                    rec["record_id"] = rid
                    records.append(rec)
                    keys.add(rid)
                    added += 1
            except Exception as exc:  # retain progress and report malformed files
                errors.append({"file": str(path), "error": f"{type(exc).__name__}: {exc}"})

        normalized = "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in records)
        atomic_write_text(raw_dir / "normalized.jsonl", normalized)

        write_summary(records, run_files, raw_dir)
        write_voice_corpus(records, raw_dir)
        ensure_identity_templates(output)

        manifest = {
            "schema_version": 1,
            "updated_at": utc_now(),
            "input": str(input_path),
            "append": bool(args.append),
            "records_total": len(records),
            "records_added_this_run": added,
            "dataset_hash": dataset_hash(records),
            "sensitive_categories_included": bool(args.include_sensitive),
            "source_files_this_run": [p.name for p in run_files],
            "errors": errors,
        }
        atomic_write_text(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0 if not errors else 1
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
