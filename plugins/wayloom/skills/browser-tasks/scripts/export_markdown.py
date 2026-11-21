#!/usr/bin/env python3
"""Convert saved Wayloom evidence to Markdown; never contact or replay a browser.

Accept a complete get_run response (raw/MCP), a raw result object, or
{"run": <get_run>, "result": <recovered object>} / {"run": <get_run>,
"chunks": [<get_run_result>, ...]}. Chunk offsets count UTF-16 code units.
A recovered object is caller supplied; only chunks establish transport bounds.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.parse import urlsplit


class ExportError(ValueError):
    """The saved input cannot be exported without misrepresenting its evidence."""


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def inline(value: Any) -> str:
    text = " ".join(str(value).split())
    text = html.escape(text, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#|~])", r"\\\1", text)


def fenced(value: Any, language: str = "text") -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    width = max([2, *(len(m.group()) for m in re.finditer(r"`+", text))]) + 1
    fence = "`" * width
    return f"{fence}{language}\n{text}" + ("" if text.endswith("\n") else "\n") + fence


def link(value: Any, label: str | None = None) -> str:
    """Only emit noncredentialed HTTP(S) destinations as active Markdown links."""
    if not isinstance(value, str) or not value:
        return "Not available"
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]*@", value):
        return "[Credentialed URL redacted]"
    try:
        if any(c.isspace() or ord(c) < 32 or c in "<>\\" for c in value):
            raise ValueError()
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError()
        if parts.username is not None or parts.password is not None:
            return "[Credentialed URL redacted]"
        _ = parts.port
    except ValueError:
        quoted = json.dumps(value, ensure_ascii=False)
        width = max([0, *(len(m.group()) for m in re.finditer(r"`+", quoted))]) + 1
        fence = "`" * width
        return f"Unsupported URL (inactive): {fence} {quoted} {fence}"
    return f"[{inline(label or value)}](<{value}>)"


def unwrap(value: Any) -> dict[str, Any]:
    """Read supported envelopes, not an arbitrary nested field named result."""
    for _ in range(8):
        if not isinstance(value, dict):
            raise ExportError("Expected a JSON object or a Wayloom MCP response.")
        if value.get("isError") is True:
            raise ExportError("The MCP response reports an error; save a get_run result instead.")
        if value.get("jsonrpc") == "2.0":
            if "error" in value or not isinstance(value.get("result"), dict):
                raise ExportError("The JSON-RPC response has no successful result.")
            value = value["result"]
        elif isinstance(value.get("structuredContent"), dict):
            value = value["structuredContent"]
        elif isinstance(value.get("content"), list) and all(
            isinstance(x, dict) and "type" in x for x in value["content"]
        ):
            texts = [x.get("text") for x in value["content"] if x.get("type") == "text"]
            if len(texts) != 1 or not isinstance(texts[0], str):
                raise ExportError("MCP text content does not contain one unambiguous JSON result.")
            try:
                value = json.loads(texts[0])
            except (ValueError, TypeError):
                raise ExportError("MCP text content is not valid JSON.") from None
        else:
            return value
    raise ExportError("Response envelopes are nested too deeply.")


def nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ExportError(f"Chunk {label} must be a nonnegative integer.")
    return value


def assemble_chunks(raw: Any, run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, list) or not raw:
        raise ExportError("Supply every get_run_result response in a nonempty chunks array.")
    chunks = [unwrap(item) for item in raw]
    run_id = chunks[0].get("run_id")
    total = nonnegative_int(chunks[0].get("total_characters"), "total_characters")
    if not isinstance(run_id, str) or not run_id:
        raise ExportError("Result chunks must identify their run_id.")
    if run and (run.get("run_id") != run_id or run.get("status") != "COMPLETED"):
        raise ExportError("Result chunks do not match the completed get_run response.")
    if run and "result_characters" in run:
        if nonnegative_int(run["result_characters"], "get_run.result_characters") != total:
            raise ExportError("Result chunk total does not match get_run.result_characters.")
    for chunk in chunks:
        nonnegative_int(chunk.get("offset"), "offset")
    chunks.sort(key=lambda item: item["offset"])
    end = 0
    buffers = []
    for chunk in chunks:
        if chunk.get("run_id") != run_id or chunk.get("status") != "COMPLETED":
            raise ExportError("Every chunk must belong to the same completed run.")
        if nonnegative_int(chunk.get("total_characters"), "total_characters") != total:
            raise ExportError("Result chunks disagree about the total character count.")
        text = chunk.get("result_json_chunk")
        if not isinstance(text, str) or not text:
            raise ExportError("Every result chunk must contain JSON text.")
        if chunk["offset"] != end:
            raise ExportError("Result chunks contain a gap, duplicate, or overlap; recover the missing continuation.")
        end += utf16_length(text)
        if end > total:
            raise ExportError("Result chunk text exceeds the declared UTF-16 bounds.")
        expected_next = end if end < total else None
        if "next_offset" not in chunk or chunk["next_offset"] != expected_next:
            raise ExportError("Result chunk next_offset disagrees with its UTF-16 bounds.")
        if expected_next is not None:
            nonnegative_int(chunk["next_offset"], "next_offset")
        buffers.append(text.encode("utf-16-le", "surrogatepass"))
    if end != total:
        raise ExportError("Result chunks are incomplete; follow next_offset for this same run.")
    try:
        # Decoding the joined UTF-16 bytes also rejoins a split surrogate pair.
        result = json.loads(b"".join(buffers).decode("utf-16-le"))
    except (ValueError, UnicodeError):
        raise ExportError("The assembled result is not valid complete Unicode JSON.") from None
    if not isinstance(result, dict):
        raise ExportError("The recovered Wayloom result must be a JSON object.")
    return result


def looks_like_run(obj: dict) -> bool:
    if not isinstance(obj.get("run_id"), str) or not isinstance(obj.get("status"), str):
        return False
    # User-defined records may legitimately have run_id and status fields.
    # Actual run and submission responses also carry transport/lifecycle data.
    return (
        type(obj.get("result_truncated")) is bool
        or isinstance(obj.get("steps"), list)
        or ("result" in obj and (obj["result"] is None or isinstance(obj["result"], dict)))
        or obj.get("next_tool") in ("get_run", "get_run_result")
        or (isinstance(obj.get("queue"), dict) and isinstance(obj.get("request_key"), str))
    )


def prepare(raw: Any, allow_partial: bool) -> tuple[dict | None, dict | None, str, list[str]]:
    obj = unwrap(raw)
    warnings: list[str] = []
    run: dict | None = None
    result: dict | None = None
    transport = "Original transport completeness is not established from a raw result object."
    is_bundle = isinstance(obj.get("run"), dict) and ("result" in obj or "chunks" in obj)
    if is_bundle:
        run = unwrap(obj["run"])
        if not isinstance(run.get("run_id"), str) or not isinstance(run.get("status"), str):
            raise ExportError("The run wrapper must contain a get_run response with run_id and status.")
        if "result" in obj and "chunks" in obj:
            raise ExportError("Supply either a recovered result or chunks, not both.")
        if "chunks" in obj:
            result = assemble_chunks(obj["chunks"], run)
            transport = f"Complete result reconstructed from {len(obj['chunks'])} chunks with validated UTF-16 bounds."
        else:
            if not isinstance(obj["result"], dict):
                raise ExportError("The recovered result must be a JSON object.")
            result = obj["result"]
            transport = "Caller-supplied recovered result; original chunk boundaries were not supplied."
        if run.get("result") is not None and run["result"] != result:
            raise ExportError("Recovered result conflicts with get_run's inline result.")
    elif looks_like_run(obj):
        run = obj
        if obj.get("result_truncated") is True:
            warnings.append("Transport is incomplete: get_run omitted or shortened the result. Recover get_run_result for the same run; never rerun browser actions for pagination.")
        else:
            transport = "Saved inline get_run result; no transport truncation was reported."
        if isinstance(obj.get("result"), dict):
            result = obj["result"]
        elif obj.get("result") is not None:
            raise ExportError("The inline Wayloom result must be a JSON object.")
    else:
        if "result_json_chunk" in obj or obj.get("result_truncated") is True:
            raise ExportError("Supply the get_run response and every get_run_result chunk in a run/chunks bundle; this is incomplete transport, not a source result.")
        result = obj
    if run:
        status = run.get("status")
        if not isinstance(status, str):
            raise ExportError("The run status must be a string.")
        if status != "COMPLETED":
            warnings.append(f"Execution status is {status}; this is a run report, not a completed-result claim.")
        if run.get("error") is not None:
            warnings.append("The run reports an error. Inspect the saved failure evidence below.")
        if result is None:
            warnings.append("No result object was returned. An absent result does not establish an empty page or a successful task.")
    if warnings and not allow_partial:
        raise ExportError(" ".join(warnings) + " Use --allow-partial only for a clearly labeled incomplete or failed report.")
    return run, result, transport, warnings


def evidence_steps(run: dict | None) -> list[dict]:
    # Exclude filled values, raw model prompts, credits and session metadata.
    allowed = {"page_readiness", "document_response", "result_audit", "result_readback", "result_selection", "completion", "completion_check", "completion_gate"}
    if not run:
        return []
    steps = run.get("steps", [])
    if not isinstance(steps, list):
        raise ExportError("Saved run steps must be an array.")
    return [step for step in steps if isinstance(step, dict) and step.get("action") in allowed]


def limitations(value: Any, path: str = "") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{path}.{key}" if path else key
            if key in {"truncated", "text_limited", "traversal_limited", "sources_truncated", "potentially_incomplete"} and child is True:
                found.append(f"{here}=true")
            elif key in {"ready", "result_complete", "source_complete_within_capture_limits", "capture_matches_readback", "all_fields_observed", "verified"} and child is False:
                found.append(f"{here}=false")
            elif key == "ready" and child is None:
                found.append(f"{here}=null (readiness was not established)")
            elif key == "http_error" and child is True:
                found.append(f"{here}=true")
            elif key == "http_status" and type(child) is int and not 200 <= child < 300:
                found.append(f"{here}={child} (the captured document may be an error, redirect, or access challenge)")
            elif key == "semantic_verification" and isinstance(child, str):
                found.append(f"{here}={child}")
            elif key in {"limitation", "limitations"}:
                if isinstance(child, str):
                    found.append(child)
                elif isinstance(child, list):
                    found.extend(x for x in child if isinstance(x, str))
            if isinstance(child, (dict, list)):
                found.extend(limitations(child, here))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(limitations(child, f"{path}[{index}]"))
    return found


def render_result(result: dict) -> list[str]:
    page_keys = {"title", "url", "text", "links", "headings", "codeBlocks", "tables", "coverage"}
    is_page = isinstance(result.get("text"), str) and isinstance(result.get("url"), str)
    if not is_page:
        out = ["## Returned fields", "The values below are saved output, not an independent factual verification."]
        for name, value in result.items():
            out.extend([f"### {inline(name)}", fenced(value, "text" if isinstance(value, str) else "json")])
        return out
    out = ["## Captured page", f"**Title:** {inline(result.get('title', 'Not available'))}", f"**Source:** {link(result['url'])}", "### Captured text", fenced(result["text"])]
    if any(result.get(name) for name in ("headings", "codeBlocks", "tables", "links")):
        out.extend(["## Additional captured structure", "These are separate extraction aggregates. Their positions in the original page have not been reconstructed."])
    headings = result.get("headings")
    if headings:
        out.extend(["### Headings", fenced(headings, "json")])
    blocks = result.get("codeBlocks")
    if blocks:
        if not isinstance(blocks, list):
            raise ExportError("Page codeBlocks must be an array.")
        out.append("### Code blocks")
        for index, block in enumerate(blocks, 1):
            out.append(f"#### Code block {index}")
            if isinstance(block, dict) and isinstance(block.get("text"), str) and set(block) == {"text"}:
                out.append(fenced(block["text"]))
            else:
                out.append(fenced(block, "json"))
    if result.get("tables"):
        out.extend(["### Tables", "Original cells, row/column spans and nesting metadata are retained as JSON.", fenced(result["tables"], "json")])
    if result.get("links"):
        if not isinstance(result["links"], list):
            raise ExportError("Page links must be an array.")
        out.append("### Links")
        for item in result["links"]:
            if isinstance(item, dict) and isinstance(item.get("url"), str) and set(item) <= {"text", "url"}:
                out.append(f"- {link(item['url'], str(item.get('text') or item['url']))}")
            else:
                out.append(fenced(item, "json"))
    if "coverage" in result:
        out.extend(["## Capture diagnostics", "Capture limits and source completeness are separate from complete result transport.", fenced(result["coverage"], "json")])
    remainder = {key: value for key, value in result.items() if key not in page_keys}
    if remainder:
        out.extend(["## Additional returned fields", fenced(remainder, "json")])
    return out


def export_markdown(raw: Any, allow_partial: bool = False) -> str:
    run, result, transport, warnings = prepare(raw, allow_partial)
    steps = evidence_steps(run)
    evidence_limits = limitations(steps, "steps")
    if result is not None and "coverage" in result:
        evidence_limits.extend(limitations(result["coverage"], "capture.coverage"))
    title = "# Wayloom run report" if warnings else "# Wayloom result"
    out = [title]
    if warnings:
        out.extend(["**INCOMPLETE OR FAILED RUN REPORT — no successful task outcome is claimed.**", *[f"- {inline(w)}" for w in warnings]])
    if run:
        out.extend([f"**Run:** {inline(run['run_id'])}", f"**Execution status:** {inline(run['status'])}"])
        if isinstance(run.get("url"), str):
            out.append(f"**Requested URL:** {link(run['url'])}")
        for key in ("created_at", "started_at", "finished_at"):
            if isinstance(run.get(key), str):
                out.append(f"**{key.replace('_', ' ').capitalize()}:** {inline(run[key])}")
    else:
        out.append("**Run and execution status:** Not supplied with this raw result.")
    out.extend(["## Evidence and limitations", f"**Result transport:** {inline(transport)}", "Execution completion, a matching readback, and a schema-valid result do not establish source truth, relevance, or a successful saved action. This offline export performs no additional verification."])
    if evidence_limits:
        out.extend(f"- {inline(item)}" for item in dict.fromkeys(evidence_limits))
    else:
        out.append("No specific limitation flags were found in the supplied evidence. Unreported readiness, coverage, and semantic checks remain unknown.")
    if result is not None:
        out.extend(render_result(result))
    if run and run.get("error") is not None:
        out.extend(["## Reported failure", fenced(run["error"], "json")])
    if steps:
        out.extend(["## Source evidence", "Saved readiness, document-response, readback, selection and completion records are retained below. Other browser action values and account/session metadata are excluded.", fenced(steps, "json")])
    return "\n\n".join(out) + "\n"


def write_atomic(path: Path, text: str) -> None:
    parent = path.parent
    if not parent.is_dir():
        raise ExportError("The output directory does not exist.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=parent, prefix=".wayloom-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Saved JSON result, run response, or run/chunks bundle")
    parser.add_argument("--output", required=True, type=Path, help="Destination .md file")
    parser.add_argument("--allow-partial", action="store_true", help="Allow a clearly labeled incomplete/failed run report; never invent missing results")
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve():
            raise ExportError("Input and output must be different files.")
        if args.output.suffix.lower() != ".md":
            raise ExportError("The output filename must end in .md.")
        with args.input.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        text = export_markdown(raw, args.allow_partial)
        write_atomic(args.output, text)
    except (ExportError, OSError, ValueError, UnicodeError, RecursionError) as exc:
        print(f"Wayloom export failed: {exc}", file=sys.stderr)
        return 2
    print(f"Saved Markdown: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
