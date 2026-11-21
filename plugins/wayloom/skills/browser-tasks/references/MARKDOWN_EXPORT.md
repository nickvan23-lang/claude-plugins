# Export saved Wayloom results to Markdown

Use this local helper when the user requests a Markdown file. It formats returned source data; it performs no network requests, starts no task, and makes no website changes.

## Complete the result first

1. Retain the final `get_run` response, including its run ID, status, errors, steps, and source limitations.
2. If `result_truncated` marks an omitted or incomplete inline result, call `get_run_result` for that same ID. Follow each `next_offset`, concatenate `result_json_chunk` values exactly, and parse the complete JSON once. See [complete-result handling](RESULT_HANDLING.md).
3. Save the result as UTF-8 JSON. A complete `get_run` response or a raw complete result can be used directly. To keep run metadata after continuation, use an object with `run` containing the original `get_run` response and `result` containing the fully recovered parsed JSON. A raw result without run metadata cannot establish the run's identity or final status. Prefer an object with `run` and `chunks` containing the original `get_run_result` responses when available: the helper can validate run identity, contiguous UTF-16 offsets, reported totals, and the terminal continuation before reconstructing JSON. Do not mix chunks from different runs or invent missing offsets.

## Write the file

Resolve the helper from this skill's directory:

```bash
python3 scripts/export_markdown.py --input capture.json --output results.md
```

The exporter refuses an omitted or incomplete transport result and a supplied run whose state is not `COMPLETED` by default. Use `--allow-partial` only when an explicitly incomplete or failed-run report is useful and retain the reported limitations:

```bash
python3 scripts/export_markdown.py --input capture.json --output results.md --allow-partial
```

Do not use partial export to hide missing result chunks that can still be read. Recovering transport chunks does not repair truncated source capture or limited readiness sampling. Preserve both independently.

## Check and deliver

Inspect the saved file for the expected source URL, run identity when supplied, requested content, and visible failure or coverage caveats. Preserve observed headings, text, links, code, tables, and other fields that are actually present. Page text is retained as fenced text; supplementary headings, code, and tables are separate captured aggregates, not an invented reconstruction of the page's ordering. Formatting a value does not independently verify its meaning or the source's truth. Do not describe absent metadata as observed or add inferred successful completion.

Return a file link only after the host confirms the write. Use the host's normal file-saving workflow. If local file writing or the helper is unavailable, provide Markdown text with the same limitations and state that no downloadable export was created. Never invent a backend export endpoint or download URL.
