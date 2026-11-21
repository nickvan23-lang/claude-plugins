# Seek X search screen replacement

`search-screen.html` is a replacement for the existing MCP App resource
`ui://seek-x/search-screen/v1.html`. It was adapted from the resource served by
`https://getseekx.com/mcp` on November 21, 2026 (MCP server version `0.8.9`).

## Behavior

- Put the actual browser capture first, with its source URL and capture time.
- Retain the last decoded frame for the same search when a later status response
  has no usable image. Mark retained or older captures explicitly.
- Clear the image when the search changes, fails, becomes unavailable, or closes.
- Render the initial snapshot even when the host cannot poll server tools.
- Keep detailed activity and source results collapsed until opened.
- Prepare Markdown from the returned search snippets and source links when the
  search completes. The page text is not inferred from screenshots or snippets.
- Offer `Download .md` only when the host advertises `downloadFile`; otherwise
  keep a readable Markdown preview. A declined download never reports success.

Full source Markdown is exported by the separate offline converter at
`plugins/seek-x/skills/seek-x/scripts/export_markdown.py`. The ChatGPT skill
source at `integrations/chatgpt/seek-x-skill.md` is packaged with that script.
The script supports completed search results and individual scrape captures,
including their complete text continuations. Batch/crawl result envelopes are
outside its current supported input contract.

## Host protocol

The widget uses the existing `ui/initialize`, `ui/notifications/tool-result`, and
`tools/call` bridge. Refresh invokes `search_status` for the accepted search ID.
It never repeats `search` or acquires another page merely to refresh the view.

Markdown download uses the advertised `ui/download-file` capability with an
embedded `text/markdown` resource. Direct iframe downloads are not used.
References:

- <https://apps.extensions.modelcontextprotocol.io/api/interfaces/app.McpUiDownloadFileRequest.html>
- <https://apps.extensions.modelcontextprotocol.io/api/interfaces/app.McpUiHostCapabilities.html>

The existing restrictive content security policy is preserved. Images remain
inline JPEG data; no external image, script, stylesheet, or network domain is
added.

## Local verification

Run the offline checks from the repository root:

```sh
python3 -m unittest discover -s tests
node --test tests/test_search_screen.cjs
```

The Python suite checks Markdown assembly and source integrity. The Node suite
executes the actual widget script with a simulated DOM, image decoder, and MCP
host. It checks frame retention, session transitions, snapshot initialization,
and download capability and denial handling. It does not establish browser
layout, real JPEG decoding, CSP integration, or target-host download support.
Those checks remain part of the live rollout verification below.

## Rollout status

This repository contains plugin packages and this replacement resource, not the
hosted MCP server implementation. Committing or publishing this repository does
not replace the live resource automatically.

To deploy, use the existing backend's resource loader to serve these HTML bytes
at the same resource URI, preserving its registration, application identity,
authentication, resource metadata, and audience. Then read the resource back
from the live server and exercise an actual search in the target host. Confirm
frame retention, snapshot rendering, and the supported download path there.
No server filesystem path or deployment command is assumed here.

A live diagnostic also captured a search-provider screen before results were
visible. This UI change preserves the pixels supplied by the server; improving
capture readiness or adding source-page frames requires the backend's capture
implementation. It does not manufacture or reconstruct missing browser images.
