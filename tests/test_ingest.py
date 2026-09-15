import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "ingest_linkedin_export.py"


def run_parser(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class IngestionTests(unittest.TestCase):
    def test_ingests_activity_excludes_sensitive_and_creates_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "export"
            source.mkdir()
            (source / "Shares.csv").write_text(
                "Date,ShareCommentary,ShareLink\n2026-09-01,Mi aprendizaje,https://example.test/post\n",
                encoding="utf-8",
            )
            (source / "Messages.csv").write_text(
                "Date,Message\n2026-09-01,private text\n", encoding="utf-8"
            )
            output = root / "state"
            result = run_parser(source, "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(line) for line in (output / "raw" / "normalized.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([record["category"] for record in records], ["posts"])
            self.assertEqual(records[0]["authorship"], "user_export_semantics")
            self.assertEqual(records[0]["date"], "2026-09-01T00:00:00")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["dataset_hash"]), 64)
            self.assertFalse(manifest["sensitive_categories_included"])
            self.assertTrue((output / "content" / "backlog.md").exists())
            self.assertTrue((output / "research" / "sources.jsonl").exists())
            self.assertEqual((output / ".gitignore").read_text(encoding="utf-8"), "*\n")

    def test_header_semantics_classify_generic_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "activity.csv"
            source.write_text("Date,ShareCommentary,ShareLink\n09/01/2026,Texto,https://example.test\n", encoding="utf-8")
            output = root / "state"
            result = run_parser(source, "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((output / "raw" / "normalized.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["category"], "posts")

    def test_append_dedupes_renamed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "Posts.csv"
            second = root / "Posts-copy.csv"
            body = "Date,Content\n2026-09-01,Same post\n"
            first.write_text(body, encoding="utf-8")
            second.write_text(body, encoding="utf-8")
            output = root / "state"
            self.assertEqual(run_parser(first, "--output", output).returncode, 0)
            result = run_parser(second, "--output", output, "--append")
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["records_total"], 1)
            self.assertEqual(manifest["records_added_this_run"], 0)

    def test_rejects_unsafe_zip_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escape.csv", "Date,Content\n2026-01-01,nope\n")
            result = run_parser(archive, "--output", root / "state")
            self.assertEqual(result.returncode, 2)
            self.assertIn("Unsafe ZIP path", result.stderr)

    def test_rejects_oversized_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Posts.csv"
            source.write_text("Date,Content\n2026-01-01,too-large\n", encoding="utf-8")
            result = run_parser(source, "--output", root / "state", "--max-file-bytes", "10")
            self.assertEqual(result.returncode, 2)
            self.assertIn("File exceeds size limit", result.stderr)

    def test_sensitive_data_requires_explicit_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Messages.csv"
            source.write_text("Date,Message\n2026-01-01,private\n", encoding="utf-8")
            output = root / "state"
            result = run_parser(source, "--output", output, "--include-sensitive")
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((output / "raw" / "normalized.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["category"], "messages")
            self.assertFalse(record["authored_voice_candidate"])


if __name__ == "__main__":
    unittest.main()
