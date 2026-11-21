"""Offline regression cases using small synthetic Wayloom captures only."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/wayloom/skills/browser-tasks/scripts/export_markdown.py"
spec = importlib.util.spec_from_file_location("wayloom_export", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def envelope(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}], "structuredContent": value, "isError": False}


def page():
    return {
        "title": "Fixture page",
        "url": "https://example.com/test",
        "text": "A short captured page.\nAn emoji: 🧪\n<script>never execute()</script>\n",
        "headings": [{"level": 1, "text": "Fixture heading"}],
        "codeBlocks": [{"text": "print('example')\n```\n"}],
        "tables": [{"index": 0, "parentTableIndex": None, "caption": "", "rows": [
            {"cells": [{"text": "Label", "header": True, "rowSpan": 2, "colSpan": 1}]}], "truncated": False}],
        "links": [{"text": "Example", "url": "https://example.com/another?a=1&b=2"}],
        "coverage": {"text": {"limit": 100000, "truncated": False}},
    }


def run(result=None, **overrides):
    obj = {"run_id": "fixture-run", "status": "COMPLETED", "url": "https://example.com/test",
           "result": result, "result_truncated": False, "error": None,
           "steps": [{"action": "document_response", "http_status": 200, "http_error": False},
                     {"action": "result_audit", "all_fields_observed": True,
                      "acquisition": {"state": "settled", "ready": False, "text_limited": True},
                      "coverage": {"result_complete": True, "source_complete_within_capture_limits": False},
                      "semantic_verification": "not_established"}]}
    obj.update(overrides)
    return obj


def chunks(result, cut=None):
    wire = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    encoded = wire.encode("utf-16-le")
    total = len(encoded) // 2
    cut = cut or total // 2
    result_chunks = []
    for start, end in ((0, cut), (cut, total)):
        result_chunks.append(envelope({"run_id": "fixture-run", "status": "COMPLETED",
                                      "result_json_chunk": encoded[start*2:end*2].decode("utf-16-le", "surrogatepass"),
                                      "offset": start, "total_characters": total,
                                      "next_offset": end if end < total else None}))
    return result_chunks, total


class ExportTests(unittest.TestCase):
    def test_complete_capture_keeps_actual_text_and_separate_evidence(self):
        data = page()
        markdown = exporter.export_markdown(envelope(run(data)))
        self.assertIn(data["text"], markdown)
        self.assertIn("COMPLETED", markdown)
        self.assertIn("acquisition.ready=false", markdown)
        self.assertIn("source\\_complete\\_within\\_capture\\_limits=false", markdown)
        self.assertIn("schema-valid result do not establish source truth", markdown)
        self.assertIn('"rowSpan": 2', markdown)
        self.assertIn("separate extraction aggregates", markdown)
        self.assertIn("````text\nprint('example')\n```\n````", markdown)

    def test_truncated_inline_is_not_an_empty_success(self):
        data = run(None, result_truncated=True)
        with self.assertRaisesRegex(exporter.ExportError, "get_run_result"):
            exporter.export_markdown(data)
        markdown = exporter.export_markdown(data, allow_partial=True)
        self.assertIn("INCOMPLETE OR FAILED RUN REPORT", markdown)
        self.assertIn("No result object was returned", markdown)
        self.assertNotIn("## Captured page", markdown)

    def test_raw_result_does_not_invent_run_metadata(self):
        markdown = exporter.export_markdown(page())
        self.assertIn("Run and execution status:** Not supplied", markdown)
        self.assertIn("Original transport completeness is not established", markdown)

    def test_recovered_result_preserves_run_limitations(self):
        markdown = exporter.export_markdown({"run": envelope(run(None, result_truncated=True)), "result": page()})
        self.assertIn("Caller-supplied recovered result", markdown)
        self.assertIn("text\\_limited=true", markdown)
        self.assertNotIn("INCOMPLETE OR FAILED RUN REPORT", markdown)

    def test_conflicting_recovered_result_is_refused(self):
        with self.assertRaisesRegex(exporter.ExportError, "conflicts"):
            exporter.export_markdown({"run": run({"title": "Different"}), "result": page()})

    def test_chunks_reconstruct_utf16_split_emoji(self):
        data = page()
        wire = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        cut = exporter.utf16_length(wire[:wire.index("🧪")]) + 1
        records, total = chunks(data, cut)
        bundle = {"run": run(None, result_truncated=True, result_characters=total), "chunks": records}
        markdown = exporter.export_markdown(bundle)
        self.assertIn(data["text"], markdown)
        self.assertIn("validated UTF-16 bounds", markdown)
        self.assertNotIn("\\uddea", markdown)

    def test_chunk_integrity_errors_are_not_overridden_by_allow_partial(self):
        records, total = chunks(page())
        cases = []
        missing = records[:1]
        cases.append(missing)
        wrong_run = copy.deepcopy(records)
        wrong_run[1]["structuredContent"]["run_id"] = "other-run"
        cases.append(wrong_run)
        wrong_total = copy.deepcopy(records)
        wrong_total[1]["structuredContent"]["total_characters"] += 1
        cases.append(wrong_total)
        wrong_next = copy.deepcopy(records)
        wrong_next[0]["structuredContent"]["next_offset"] += 1
        cases.append(wrong_next)
        missing_null = copy.deepcopy(records)
        del missing_null[-1]["structuredContent"]["next_offset"]
        cases.append(missing_null)
        cases.append([records[0], records[0], records[1]])
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(exporter.ExportError):
                    exporter.export_markdown({"run": run(None, result_truncated=True, result_characters=total), "chunks": case}, allow_partial=True)

    def test_failed_and_nonterminal_runs_remain_failed_or_incomplete(self):
        for status in ("RUNNING", "FAILED", "CANCELLED", "PENDING"):
            value = run(page(), status=status, error={"code": "execution_failed"} if status == "FAILED" else None)
            with self.assertRaises(exporter.ExportError):
                exporter.export_markdown(value)
            markdown = exporter.export_markdown(value, allow_partial=True)
            self.assertIn(f"**Execution status:** {status}", markdown)
            self.assertIn("no successful task outcome is claimed", markdown)

    def test_transport_errors_are_not_source_results(self):
        for value in ({"isError": True, "structuredContent": page()},
                      {"jsonrpc": "2.0", "error": {"message": "failed"}},
                      {"content": [{"type": "text", "text": "not JSON"}]}):
            with self.assertRaises(exporter.ExportError):
                exporter.export_markdown(value)

    def test_http_error_and_source_truncation_are_visible(self):
        data = page()
        data["coverage"]["text"]["truncated"] = True
        record = run(data)
        record["steps"][0].update(http_status=403, http_error=True)
        markdown = exporter.export_markdown(record)
        self.assertIn("http\\_status=403", markdown)
        self.assertIn("capture.coverage.text.truncated=true", markdown)
        self.assertIn("error, redirect, or access challenge", markdown)

    def test_untrusted_markdown_cannot_escape_fences_or_create_active_unsafe_links(self):
        data = page()
        data["title"] = "[bad](javascript:alert(1))<img src=x onerror=alert(1)>"
        data["text"] = "`````\n<script>bad()</script>\n[bad](javascript:alert(1))\n"
        data["links"] += [{"text": "bad", "url": "javascript:alert(1)"},
                          {"text": "bad", "url": "https://user:password@example.com/"},
                          {"text": "bad", "url": "https://example.com/\n<script>"}]
        markdown = exporter.export_markdown(run(data))
        self.assertIn("``````text\n" + data["text"] + "``````", markdown)
        self.assertIn("&lt;img", markdown)
        self.assertNotIn("](<javascript:", markdown)
        self.assertNotIn("https://user:password", markdown)
        self.assertEqual(markdown.count("Unsupported URL (inactive)"), 2)
        self.assertIn("Credentialed URL redacted", markdown)

    def test_arbitrary_fields_and_provenance_are_retained(self):
        data = {"salary": "$100,000 annually", "source_url": "https://example.com/job", "provenance": {"selected_source_ids": ["node-1"]}}
        markdown = exporter.export_markdown(run(data))
        self.assertIn("$100,000 annually", markdown)
        self.assertIn('"selected_source_ids": [', markdown)
        self.assertIn("node-1", markdown)

    def test_source_run_status_fields_are_not_transport(self):
        data = {"run_id": "public-reference", "status": "active", "description": "A source record"}
        markdown = exporter.export_markdown(data)
        self.assertIn("public-reference", markdown)
        self.assertIn("active", markdown)
        self.assertIn("A source record", markdown)
        self.assertIn("Run and execution status:** Not supplied", markdown)
        self.assertNotIn("INCOMPLETE OR FAILED RUN REPORT", markdown)

    def test_submission_receipt_is_not_a_completed_result(self):
        receipt = {"run_id": "fixture-run", "status": "RUNNING", "queue": {"waiting": False},
                   "request_key": "unique-test", "next_tool": "get_run", "replayed": False}
        with self.assertRaises(exporter.ExportError):
            exporter.export_markdown(envelope(receipt))
        markdown = exporter.export_markdown(receipt, allow_partial=True)
        self.assertIn("No result object was returned", markdown)
        for incomplete in ({"result_truncated": True, "result": None},
                           {"result_json_chunk": "{", "offset": 0, "next_offset": 1}):
            with self.assertRaises(exporter.ExportError):
                exporter.export_markdown(incomplete)

    def test_cli_is_atomic_on_bad_input_and_preserves_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            src, dst = parent / "capture.json", parent / "output.md"
            src.write_text(json.dumps(run(page())), encoding="utf-8")
            good = subprocess.run([sys.executable, str(SCRIPT), "--input", str(src), "--output", str(dst)], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            before = dst.read_text()
            src.write_text("invalid json", encoding="utf-8")
            bad = subprocess.run([sys.executable, str(SCRIPT), "--input", str(src), "--output", str(dst)], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(dst.read_text(), before)
            self.assertEqual(list(parent.glob(".wayloom-*.tmp")), [])
            same = subprocess.run([sys.executable, str(SCRIPT), "--input", str(src), "--output", str(src)], capture_output=True, text=True)
            self.assertEqual(same.returncode, 2)
            self.assertEqual(src.read_text(), "invalid json")


if __name__ == "__main__":
    unittest.main()
