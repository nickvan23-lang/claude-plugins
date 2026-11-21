#!/usr/bin/env python3
"""Export saved Seek X search/scrape results to Markdown without network calls.

Input: {"query": "...", "captured_at": "ISO-8601 with timezone",
        "results": [structured_result_or_MCP_envelope, ...]}.
Only source content and its provenance are exported; account, usage, request,
session, and screen metadata are not copied. Unknown result shapes fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class ExportError(ValueError):
    """The saved evidence cannot be safely assembled."""


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def plain(text: Any) -> str:
    """Escape exporter-generated single-line Markdown, not source Markdown."""
    if not isinstance(text, str):
        return ""
    text = " ".join(text.split())
    return re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", text)


def http_url(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ExportError("A source is missing its HTTP(S) URL.")
    if any(ord(c) < 32 or c in "<>" for c in value):
        raise ExportError("A source URL contains unsafe characters.")
    try:
        p = urlsplit(value)
        if p.scheme.lower() not in ("http", "https") or not p.hostname:
            raise ValueError()
        if p.username or p.password:
            raise ValueError()
        # Accessing port validates malformed ports without emitting the URL.
        _ = p.port
    except ValueError:
        raise ExportError("A source URL is invalid or contains credentials.") from None
    return value


def url_key(value: str) -> str:
    p = urlsplit(value)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))


def integer(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ExportError(f"Pagination {name} must be a nonnegative integer.")
    return value


def warnings_from(obj: dict[str, Any]) -> list[str]:
    values = obj.get("warnings", [])
    if isinstance(values, (str, dict)):
        values = [values]
    if not isinstance(values, list):
        raise ExportError("Warnings must be text or a list of warning records.")
    values = [*values, obj.get("warning")]
    out = []
    for item in values:
        if isinstance(item, str) and item:
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get("message"), str):
            out.append(item["message"])
    return out


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def unwrap(value: Any) -> dict[str, Any]:
    for _ in range(8):
        if not isinstance(value, dict):
            raise ExportError("Each result must be a JSON object.")
        if value.get("isError") is True or value.get("success") is False:
            raise ExportError("A result reports an error; it cannot be exported as source content.")
        if value.get("jsonrpc") == "2.0":
            if "error" in value or not isinstance(value.get("result"), dict):
                raise ExportError("The JSON-RPC response has no successful object result.")
            value = value["result"]
            continue
        if isinstance(value.get("structuredContent"), dict):
            value = value["structuredContent"]
            continue
        if isinstance(value.get("content"), list):
            blocks = [c.get("text") for c in value["content"]
                      if isinstance(c, dict) and c.get("type") == "text"]
            if len(blocks) != 1 or not isinstance(blocks[0], str):
                raise ExportError("The MCP envelope has no unambiguous JSON text result.")
            try:
                value = json.loads(blocks[0])
            except (ValueError, TypeError):
                raise ExportError("The MCP text result is not valid JSON.") from None
            continue
        return value
    raise ExportError("Result envelopes are nested too deeply.")


@dataclass
class Chunk:
    offset: int
    end: int
    total: int
    digest: str
    text: str


@dataclass
class Source:
    url: str
    title: str = ""
    aliases: list[str] = field(default_factory=list)
    snippets: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    timestamps: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    unpaginated: str | None = None


class Exporter:
    def __init__(self, allow_partial: bool = False):
        self.allow_partial = allow_partial
        self.sources: list[Source] = []
        self.by_url: dict[str, Source] = {}
        self.warnings: list[str] = []
        self.limitations: list[str] = []
        self.search_seen = False

    def source(self, row: dict[str, Any]) -> Source:
        meta = row.get("metadata", {})
        if not isinstance(meta, dict):
            raise ExportError("Source metadata must be an object.")
        candidates = [v for v in (meta.get("url"), row.get("url"), meta.get("sourceURL")) if v]
        if not candidates:
            raise ExportError("A source is missing its HTTP(S) URL.")
        urls = [http_url(v) for v in candidates]
        matches = {id(self.by_url[url_key(u)]): self.by_url[url_key(u)]
                   for u in urls if url_key(u) in self.by_url}
        if len(matches) > 1:
            raise ExportError("Conflicting source aliases need separate, unambiguous captures.")
        src = next(iter(matches.values())) if matches else Source(url=urls[0])
        if not matches:
            self.sources.append(src)
        for url in urls:
            self.by_url[url_key(url)] = src
            if url not in src.aliases:
                src.aliases.append(url)
        title = meta.get("title") or row.get("title")
        if title is not None and not isinstance(title, str):
            raise ExportError("Source title must be text.")
        if not src.title:
            src.title = title or urls[0]
        src.warnings.extend(warnings_from(row))
        src.warnings.extend(warnings_from(meta))
        status = meta.get("statusCode")
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            raise ExportError("HTTP source status must be a valid integer status code.")
        if status is not None and not 200 <= status < 300:
            src.limitations.append(f"HTTP {status} capture; the text may be an error or access-challenge page.")
        if meta.get("renderingFallback"):
            src.limitations.append("Rendering fallback was reported; the requested rendered content may be incomplete.")
        for obj in (row, meta):
            for key in ("truncated", "contentTruncated", "markdownTruncated", "sourceTruncated", "partial"):
                if obj.get(key) is True:
                    src.limitations.append(f"Source reports {key}=true.")
            for key in ("coverage", "contentCoverage", "textCoverage", "markdownCoverage", "imageCoverage", "linkCoverage"):
                coverage = obj.get(key)
                if isinstance(coverage, dict):
                    if coverage.get("truncated") is True or coverage.get("complete") is False:
                        src.limitations.append(f"Source {key} is incomplete.")
                    for sub in ("text", "markdown", "content", "images", "links"):
                        inner = coverage.get(sub)
                        if isinstance(inner, dict) and (inner.get("truncated") is True or inner.get("complete") is False):
                            src.limitations.append(f"Source {key}.{sub} is incomplete.")
            for key in ("capturedAt", "captured_at", "scrapedAt"):
                if isinstance(obj.get(key), str):
                    src.timestamps.append(obj[key])
        return src

    def page(self, row: dict[str, Any]) -> None:
        text = row.get("markdown")
        if not isinstance(text, str):
            raise ExportError("A page result is missing its Markdown text.")
        src = self.source(row)
        p = row.get("pagination")
        if p is None:
            if src.chunks or (src.unpaginated is not None and src.unpaginated != text):
                raise ExportError("Incompatible captures of the same source cannot be combined.")
            src.unpaginated = text
            return
        if not isinstance(p, dict) or src.unpaginated is not None:
            raise ExportError("Page pagination is invalid or mixed with an unpaginated capture.")
        offset = integer(p.get("offset"), "offset")
        returned = integer(p.get("returnedChars"), "returnedChars")
        total = integer(p.get("totalChars"), "totalChars")
        digest = p.get("contentHash")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            raise ExportError("Paginated content requires a SHA-256 contentHash.")
        digest = digest.lower()
        if returned != utf16_length(text) or offset + returned > total:
            raise ExportError("Chunk text does not match its UTF-16 pagination bounds.")
        end = offset + returned
        has_more = p.get("hasMore")
        if type(has_more) is not bool or has_more != (end < total):
            raise ExportError("Pagination hasMore disagrees with the advertised total.")
        if has_more and p.get("nextOffset") != end:
            raise ExportError("Pagination nextOffset does not follow this chunk.")
        if not has_more and p.get("nextOffset") is not None:
            raise ExportError("A final chunk cannot advertise a next offset.")
        continuation = p.get("continuation")
        if continuation is not None:
            if not isinstance(continuation, dict):
                raise ExportError("Pagination continuation must be an object.")
            args = continuation.get("arguments", continuation)
            if not isinstance(args, dict):
                raise ExportError("Pagination continuation arguments must be an object.")
            if "offset" in args and args["offset"] != end:
                raise ExportError("Continuation offset does not follow this chunk.")
            expected_hash = args.get("expectedHash", args.get("contentHash"))
            if expected_hash is not None and (not isinstance(expected_hash, str) or expected_hash.lower() != digest):
                raise ExportError("Continuation hash differs from its page contentHash.")
        chunk = Chunk(offset, end, total, digest, text)
        for old in src.chunks:
            if old.digest != digest or old.total != total:
                raise ExportError("Mixed content hashes or totals for one source; restart the capture.")
            if old.offset == offset and old.end == end and old.text == text:
                return
            if max(old.offset, offset) < min(old.end, end) or old.offset == offset:
                raise ExportError("Overlapping or conflicting chunks cannot be combined.")
        src.chunks.append(chunk)

    def collect(self, raw: Any) -> None:
        obj = unwrap(raw)
        self.warnings.extend(warnings_from(obj))
        activity = obj.get("activity")
        if obj.get("kind") == "search_activity" or activity is not None:
            if not isinstance(activity, dict) or activity.get("status") != "completed":
                raise ExportError("Search activity must be completed before exporting its results.")
            self.collect(activity.get("result"))
            return
        data = obj.get("data", obj)
        if isinstance(data, dict) and isinstance(data.get("web"), list):
            self.search_seen = True
            search = obj.get("search", {})
            if not isinstance(search, dict):
                raise ExportError("Search metadata must be an object.")
            self.warnings.extend(warnings_from(search))
            for row in data["web"]:
                if not isinstance(row, dict):
                    raise ExportError("Each search result must be an object.")
                src = self.source(row)
                snippet = row.get("description", row.get("snippet", ""))
                if not isinstance(snippet, str):
                    raise ExportError("Search snippets must be text.")
                if snippet:
                    src.snippets.append(snippet)
                if "markdown" in row:
                    self.page(row)
            return
        if isinstance(data, dict) and "markdown" in data:
            self.page(data)
            return
        if isinstance(data, list):
            raise ExportError("Batch/crawl job envelopes are not supported; this exporter accepts completed search results and scrape captures.")
        raise ExportError("Unsupported result shape; expected a completed search or a Markdown page capture.")

    def assemble(self, src: Source) -> tuple[list[tuple[int, int, str]], str, bool]:
        if not src.chunks:
            if src.unpaginated is None:
                return [], "Search snippet only; source page text was not supplied.", bool(src.limitations)
            try:
                src.unpaginated.encode("utf-8")
            except UnicodeError:
                raise ExportError("Unpaginated text contains an unpaired Unicode surrogate.") from None
            return [(0, utf16_length(src.unpaginated), src.unpaginated)], "Page Markdown supplied without pagination; full-page coverage is unverified.", bool(src.limitations)
        chunks = sorted(src.chunks, key=lambda c: c.offset)
        total, digest = chunks[0].total, chunks[0].digest
        groups: list[list[Chunk]] = []
        for c in chunks:
            if groups and groups[-1][-1].end == c.offset:
                groups[-1].append(c)
            else:
                groups.append([c])
        complete = len(groups) == 1 and groups[0][0].offset == 0 and groups[0][-1].end == total
        segments = []
        for group in groups:
            raw = b"".join(c.text.encode("utf-16-le", "surrogatepass") for c in group)
            try:
                text = raw.decode("utf-16-le")
            except UnicodeError:
                raise ExportError("A captured segment splits a Unicode character; supply its adjacent chunk.") from None
            segments.append((group[0].offset, group[-1].end, text))
        if complete:
            if hashlib.sha256(segments[0][2].encode("utf-8")).hexdigest() != digest:
                raise ExportError("Assembled page text does not match its SHA-256 contentHash.")
            coverage = f"All {total} UTF-16 code units of the captured text are present; SHA-256 verified. This does not establish whole-page capture completeness."
        else:
            saved = sum(c.end - c.offset for c in chunks)
            coverage = f"PARTIAL: {saved} of {total} UTF-16 code units supplied; missing chunks were not fetched. The full-text hash cannot be verified."
        return segments, coverage, (not complete or bool(src.limitations))

    def render(self, capture: dict[str, Any]) -> str:
        if not isinstance(capture, dict) or not isinstance(capture.get("results"), list):
            raise ExportError("Input must contain a results array.")
        stamp = capture.get("captured_at")
        if stamp is not None:
            try:
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError()
            except (ValueError, AttributeError, TypeError):
                raise ExportError("captured_at must be an ISO-8601 timestamp with a timezone.") from None
        query = capture.get("query", "")
        if not isinstance(query, str):
            raise ExportError("query must be text.")
        for item in capture["results"]:
            self.collect(item)
        if not self.sources and not self.search_seen:
            raise ExportError("No exportable source results were supplied.")
        assembled = [(s, *self.assemble(s)) for s in self.sources]
        partial = bool(self.limitations) or any(item[3] for item in assembled)
        if partial and not self.allow_partial:
            raise ExportError("The capture is incomplete or has source limitations. Supply the missing evidence, or use --allow-partial for an explicitly labelled export.")
        out = ["# Seek X results\n\n", f"Capture recorded: {plain(stamp)}\n\n" if stamp else "Capture timestamp not supplied.\n\n"]
        if query:
            out.append(f"Query: {plain(query)}\n\n")
        out.append(f"Sources: {len(self.sources)}\n\n")
        if partial:
            out.append("> **PARTIAL EXPORT.** Some source content or job results are incomplete. Read the coverage notes below.\n\n")
        for note in unique(self.limitations + self.warnings):
            out.append(f"> {plain(note)}\n\n")
        if not self.sources:
            out.append("The completed search returned no source results.\n")
        for number, (src, segments, coverage, _) in enumerate(assembled, 1):
            out.append(f"## {number}. {plain(src.title)}\n\n")
            out.append(f"Source: <{src.url}>\n\n")
            for alias in src.aliases:
                if url_key(alias) != url_key(src.url):
                    out.append(f"Requested source: <{alias}>\n\n")
            for timestamp in unique(src.timestamps):
                out.append(f"Source capture timestamp: {plain(timestamp)}\n\n")
            out.append(f"Coverage: {coverage}\n\n")
            for note in unique(src.limitations + src.warnings):
                out.append(f"> {plain(note)}\n\n")
            if src.snippets:
                out.append("### Search snippets\n\n")
                for snippet in unique(src.snippets):
                    out.append(snippet + ("\n\n" if not snippet.endswith("\n\n") else ""))
            if segments:
                out.append("### Captured page Markdown\n\n")
                for start, end, text in segments:
                    if len(segments) > 1 or start != 0:
                        out.append(f"#### Captured segment: UTF-16 offsets {start}–{end}\n\n")
                    # Preserve original source text, including code fences/tables.
                    out.append(text)
                    out.append("\n\n" if not text.endswith("\n\n") else "")
            out.append("---\n\n")
        return "".join(out)


def export_markdown(capture: dict[str, Any], allow_partial: bool = False) -> str:
    return Exporter(allow_partial=allow_partial).render(capture)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Saved JSON capture, or - for stdin")
    parser.add_argument("--output", required=True, type=Path, help="Destination .md file")
    parser.add_argument("--allow-partial", action="store_true", help="Label and export incomplete evidence; never repair conflicting chunks")
    args = parser.parse_args(argv)
    temporary = None
    try:
        if args.output.suffix.lower() != ".md":
            raise ExportError("The output filename must end in .md.")
        if args.input != "-" and Path(args.input).resolve() == args.output.resolve():
            raise ExportError("Input and output paths must be different.")
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        try:
            capture = json.loads(raw)
        except ValueError:
            raise ExportError("The input file is not valid JSON.") from None
        text = export_markdown(capture, allow_partial=args.allow_partial)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=args.output.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        os.replace(temporary, args.output)
        print(f"Wrote {args.output}")
        return 0
    except (ExportError, OSError, UnicodeError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 2
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
