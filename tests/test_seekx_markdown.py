"""Focused offline export regressions. Run: python3 -m unittest discover -s tests."""

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "plugins/seek-x/skills/seek-x/scripts/export_markdown.py"
SPEC = importlib.util.spec_from_file_location("seekx_export_markdown", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = exporter
SPEC.loader.exec_module(exporter)


def capture(*results):
    return {"query": "fixture query", "captured_at": "2026-11-21T17:08:22.128Z", "results": list(results)}


def pages(text, cuts=(), url="https://example.com/doc"):
    raw = text.encode("utf-16-le")
    total = len(raw) // 2
    digest = hashlib.sha256(text.encode()).hexdigest()
    bounds = [0, *cuts, total]
    rows = []
    for a, b in zip(bounds, bounds[1:]):
        pagination = {"offset": a, "returnedChars": b - a, "totalChars": total,
                      "contentHash": digest, "hasMore": b < total, "nextOffset": b if b < total else None}
        if b < total:
            pagination["continuation"] = {"tool": "scrape", "arguments": {"offset": b, "expectedHash": digest}}
        rows.append({"success": True, "data": {"metadata": {"url": url, "title": "Fixture", "statusCode": 200},
                    "markdown": raw[a * 2:b * 2].decode("utf-16-le", "surrogatepass"), "pagination": pagination}})
    return rows


def search(rows, status="completed"):
    return {"kind": "search_activity", "activity": {"status": status,
            "result": {"success": True, "data": {"web": rows}}}}


class MarkdownExportTests(unittest.TestCase):
    def test_preserves_markdown_and_verifies_out_of_order_chunks(self):
        body = "# A heading\n\n| A | B |\n|---|---|\n| x | y |\n\n```python\nprint('✓')\n```\n"
        chunks = pages(body, (17, 38))
        out = exporter.export_markdown(capture(chunks[2], chunks[0], chunks[1]))
        self.assertIn(body, out)
        self.assertIn("SHA-256 verified", out)
        self.assertIn("does not establish whole-page capture completeness", out)

    def test_utf16_offsets_and_surrogate_split_are_reassembled(self):
        body = "A😀B\n"
        chunks = pages(body, (2, 3))  # Deliberately split the UTF-16 surrogate pair.
        out = exporter.export_markdown(capture(*chunks))
        self.assertIn(body, out)
        self.assertIn("All 5 UTF-16 code units", out)

    def test_deduplicates_search_page_and_exact_chunk_replays(self):
        p = pages("Exact source Markdown\n")[0]
        s = search([{"url": "https://example.com/doc#fragment", "title": "Fixture", "description": "Search snippet"}])
        out = exporter.export_markdown(capture(s, p, copy.deepcopy(p)))
        self.assertIn("Sources: 1", out)
        self.assertEqual(out.count("Exact source Markdown"), 1)
        self.assertIn("### Search snippets", out)
        self.assertIn("### Captured page Markdown", out)

    def test_structured_result_wins_over_duplicate_mcp_text(self):
        p = pages("Structured source text\n")[0]
        envelope = {"structuredContent": p, "content": [{"type": "text", "text": "malformed duplicate text"}],
                    "_meta": {"token": "PRIVATE_TOKEN"}, "usage": {"used": 999}}
        p["usage"] = {"account": "private@example.com", "token": "SECRET_TOKEN"}
        out = exporter.export_markdown(capture(envelope))
        self.assertIn("Structured source text", out)
        self.assertNotIn("PRIVATE_TOKEN", out)
        self.assertNotIn("SECRET_TOKEN", out)
        self.assertNotIn("private@example.com", out)
        self.assertNotIn("usage", out)

    def test_json_text_only_mcp_envelope(self):
        p = pages("Text result\n")[0]
        out = exporter.export_markdown(capture({"content": [{"type": "text", "text": json.dumps(p)}]}))
        self.assertIn("Text result", out)

    def test_json_rpc_envelope_ignores_screen_and_session_metadata(self):
        envelope = {"jsonrpc": "2.0", "id": 1, "result": {
            "_meta": {"screenshot": "data:image/png;base64,PRIVATE_IMAGE", "token": "PRIVATE_TOKEN"},
            "structuredContent": search([{"url": "https://example.com/", "description": "Snippet"}])}}
        out = exporter.export_markdown(capture(envelope))
        self.assertIn("Search snippet only", out)
        self.assertNotIn("PRIVATE_", out)

    def test_missing_timestamp_is_explicit_not_invented(self):
        out = exporter.export_markdown({"results": [search([])]})
        self.assertIn("Capture timestamp not supplied", out)

    def test_missing_chunk_rejected_by_default_and_explicitly_labelled(self):
        chunks = pages("abcdefghij", (4, 7))
        with self.assertRaises(exporter.ExportError):
            exporter.export_markdown(capture(chunks[0], chunks[2]))
        out = exporter.export_markdown(capture(chunks[0], chunks[2]), allow_partial=True)
        self.assertIn("PARTIAL EXPORT", out)
        self.assertIn("7 of 10 UTF-16 code units", out)
        self.assertIn("offsets 0–4", out)
        self.assertIn("offsets 7–10", out)
        self.assertNotIn("abcdefghij", out)
        self.assertNotIn("SHA-256 verified", out)

    def test_metadata_observations_do_not_replace_missing_bodies(self):
        chunks = pages("abcdefghij", (4,))
        data = capture(chunks[0])
        data["continuation_observations"] = [{"pagination": chunks[1]["data"]["pagination"]}]
        out = exporter.export_markdown(data, allow_partial=True)
        self.assertIn("4 of 10 UTF-16 code units", out)
        self.assertNotIn("efghij", out)

    def test_mixed_hashes_rejected_even_when_partial_allowed(self):
        chunks = pages("abcdefghij", (4,))
        chunks[1]["data"]["pagination"]["contentHash"] = "0" * 64
        with self.assertRaisesRegex(exporter.ExportError, "Mixed content hashes"):
            exporter.export_markdown(capture(*chunks), allow_partial=True)

    def test_overlapping_chunks_rejected(self):
        chunks = pages("abcdefghij", (4,))
        overlap = copy.deepcopy(chunks[1])
        overlap["data"]["markdown"] = "defghij"
        overlap["data"]["pagination"].update(offset=3, returnedChars=7)
        with self.assertRaisesRegex(exporter.ExportError, "Overlapping"):
            exporter.export_markdown(capture(chunks[0], overlap), allow_partial=True)

    def test_full_content_hash_is_checked(self):
        p = pages("abc")[0]
        p["data"]["markdown"] = "xyz"
        with self.assertRaisesRegex(exporter.ExportError, "SHA-256 contentHash"):
            exporter.export_markdown(capture(p))

    def test_bad_utf16_counts_and_continuation_hash_are_rejected(self):
        p = pages("😀")[0]
        p["data"]["pagination"]["returnedChars"] = 1
        with self.assertRaisesRegex(exporter.ExportError, "UTF-16"):
            exporter.export_markdown(capture(p))
        p = pages("abcd", (2,))[0]
        p["data"]["pagination"]["continuation"]["arguments"]["expectedHash"] = "0" * 64
        with self.assertRaisesRegex(exporter.ExportError, "Continuation hash"):
            exporter.export_markdown(capture(p), allow_partial=True)

    def test_source_truncation_not_hidden_by_complete_pagination(self):
        p = pages("Captured prefix only")[0]
        p["data"]["coverage"] = {"text": {"truncated": True}}
        with self.assertRaises(exporter.ExportError):
            exporter.export_markdown(capture(p))
        out = exporter.export_markdown(capture(p), allow_partial=True)
        self.assertIn("PARTIAL EXPORT", out)
        self.assertIn("coverage.text is incomplete", out)

    def test_http_and_rendering_fallback_diagnostics_preserved(self):
        p = pages("Forbidden")[0]
        p["data"]["metadata"].update(statusCode=403, renderingFallback=True)
        p["data"]["warnings"] = ["Retained capture: freshness unverified."]
        out = exporter.export_markdown(capture(p), allow_partial=True)
        self.assertIn("HTTP 403", out)
        self.assertIn("Rendering fallback", out)
        self.assertIn("freshness unverified", out)

    def test_snippet_only_and_unpaginated_results_do_not_claim_full_page(self):
        out = exporter.export_markdown(capture(search([{"url": "https://example.com/", "description": "Snippet"}])))
        self.assertIn("Search snippet only", out)
        out = exporter.export_markdown(capture({"data": {"metadata": {"url": "https://example.com/"}, "markdown": "Text"}}))
        self.assertIn("full-page coverage is unverified", out)

    def test_invalid_unknown_or_running_results_fail_cleanly(self):
        bad = [{"usage": {"used": 1}}, search([], status="running"), {"isError": True},
               {"status": "completed", "data": [], "next": None}]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(exporter.ExportError):
                exporter.export_markdown(capture(payload))
        data = capture(search([]))
        data["captured_at"] = "2026-11-21"
        with self.assertRaisesRegex(exporter.ExportError, "timezone"):
            exporter.export_markdown(data)

    def test_cli_failure_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            output = root / "results.md"
            source.write_text(json.dumps(capture(pages("abcdef", (2,))[0])), encoding="utf-8")
            output.write_text("Keep existing", encoding="utf-8")
            p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(output.read_text(), "Keep existing")
            self.assertNotIn("Traceback", p.stderr)
            p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output), "--allow-partial"], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("PARTIAL EXPORT", output.read_text())


if __name__ == "__main__":
    unittest.main()
