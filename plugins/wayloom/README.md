# Wayloom for Claude Code

Read rendered pages, run authorized browser workflows, watch available task screenshots, and recover source-backed results through the hosted Wayloom service.

```text
/plugin install wayloom --marketplace nickvan23-lang/claude-plugins
```

The plugin connects to `https://wayloom.getseekx.com/mcp`. Available guest tools can be used without signup; linked accounts provide access to their own saved work and allowance. The hosted browser runs separately from your browser and does not inherit your sign-ins or local files.

## What to expect

- **A visible task screen:** when the connection and host support it, the skill opens the screen as soon as a task ID is returned. It shows periodic captured images and may briefly keep the last frame after completion. Refreshing the screen does not rerun the task.
- **A direct path for known work:** page reads use `fetch_page`; known workflows can use explicit actions. A goal-driven planner is used when navigation or control selection needs it.
- **Complete result recovery:** large saved results are retrieved through read-only continuations on the same task ID. A missing inline result does not trigger another browser task.
- **Clear evidence:** execution state, retrieved result size, capture coverage, readiness sampling, and source or outcome verification remain separate. Failures include their observed limitations; uncertain website changes are not automatically replayed.
- **Optional Markdown files:** ask to save the result as `.md`. The bundled Python helper formats saved tool-result JSON locally, preserving source URLs and available run and coverage details. File export requires a host that can run Python and write files.

Example requests:

- “Use Wayloom to read this page and show its task screen.”
- “Extract the document title and current page URL from this page.”
- “Recover the complete result for this existing Wayloom run.”
- “Save this completed Wayloom result as Markdown, including its source limitations.”

The task screen is not continuous video or a permanent recording. Completed execution or an exact source readback does not independently establish source truth or that a website change was saved. Tools and allowances vary by connection; the plugin uses the returned status and balance.

## Local Markdown conversion

After retrieving the complete result, save its JSON and run:

```bash
python3 skills/browser-tasks/scripts/export_markdown.py --input capture.json --output results.md
```

A complete run response or raw result is accepted. For a result recovered through continuation, keep the original run response and parsed result together as `{ "run": ..., "result": ... }`. For validated chunk reconstruction, use `{ "run": ..., "chunks": [...] }` with the original continuation responses. The helper makes no network calls or browser changes. It refuses incomplete transport results and supplied runs that are not completed by default; use `--allow-partial` only for an explicitly incomplete or failed-run report with its limitations retained.

- Website: https://wayloom.getseekx.com
- Support: https://wayloom.getseekx.com/support
- Privacy: https://wayloom.getseekx.com/privacy
- Terms: https://wayloom.getseekx.com/terms
