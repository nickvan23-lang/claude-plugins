# Wayloom 0.2.5

Released November 21, 2026.

## What changed

- The workflow opens the existing task screen promptly after a run starts, when the connected host supports it. Screen refreshes remain read-only.
- Known page reads use direct extraction; observed workflows can use explicit actions. The instructions reserve goal planning for work that needs navigation or control selection.
- Large results are recovered from the same run through every continuation page. The guidance distinguishes response delivery, page capture limits, readiness sampling, and verified outcomes.
- Failed or uncertain tasks retain their original evidence. The workflow does not automatically repeat website changes to obtain a better result or screen.
- A local Python helper exports saved result objects and complete result chunks to Markdown, preserving source content and evidence limitations. It validates run identity and UTF-16 continuation bounds, refuses incomplete results by default, and supports clearly labeled partial reports.
- The instruction package includes current observed-record, declared-source, and optional current-text readback guidance.

## Scope

This release updates the plugin instructions and adds an offline export helper. Browser execution, model configuration, hosting, and account allowances continue to come from the connected Wayloom service. Screens are periodic captured images rather than continuous video. Markdown conversion requires a host with Python 3 and file-writing support; it is not a new server tool.

## Validation

Validation covered a rendered page workflow, task-screen availability during and after execution, and a large completed result recovered across four continuation pages. Offline checks cover Unicode split across chunk boundaries, missing or inconsistent chunks, failed and incomplete reports, source limitations, untrusted Markdown content, and atomic file output. These checks do not establish that every goal-driven website workflow will succeed.
