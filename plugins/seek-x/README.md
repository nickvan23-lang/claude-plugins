# Seek X for Claude Code

Search, read, map, batch, crawl and extract web information with your Seek X account.

```
/plugin install seek-x --marketplace nickvan23-lang/claude-plugins
```

The plugin connects to the hosted Seek X MCP server at `https://getseekx.com/mcp`. It works right away as a free guest trial with no signup. Each connection gets its own separate jobs and results.

## Search screens and Markdown files

Seek X uses its native activity screen to show search progress in hosts that support it. When Seek X supplies browser frames, the screen shows those captured views. Interactive source inspections can show the corresponding browser session through `browser_screen`. These are periodic screenshots, not continuous video; a text activity event alone does not establish that a screenshot was captured.

The skill saves completed research as a `.md` file by default using the host's file-writing capability. The file includes source links, available capture timestamps, retrieved text, and any source coverage warnings. Search snippets stay labeled as snippets. This is a host-assisted export; the hosted server does not gain a new export endpoint from this package update.

The bundled converter at `skills/seek-x/scripts/export_markdown.py` writes UTF-8 Markdown from saved tool-result JSON without making network requests:

```bash
python3 skills/seek-x/scripts/export_markdown.py --input capture.json --output results.md
```

Use an input object containing `query`, an optional observed `captured_at`, and `results` with the actual Seek X tool responses. Complete pagination first; `--allow-partial` permits an explicitly labeled partial export when complete source content is unavailable.

Try: "Search for the official Playwright auto-waiting documentation, show the search screen, and save what you find as Markdown."

- Website: https://getseekx.com
- Support: https://getseekx.com/support.html
- Privacy: https://getseekx.com/privacy.html
- Terms: https://getseekx.com/terms.html
