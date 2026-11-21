/* Offline widget behavior tests using a simulated DOM/MCP host and image decoder.
 * They exercise the actual inline widget script, not a duplicate implementation.
 * These do not establish browser layout, CSP integration, or real JPEG decoding.
 * Run: node --test tests/test_search_screen.cjs
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const html = fs.readFileSync(path.join(__dirname, '../integrations/mcp/search-screen.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const GOOD_IMAGE = '/9j/TESTIMAGEDATA';
const NOW = Date.parse('2026-11-21T17:00:10.000Z');

class Element {
  constructor(tagName = 'div') { this.tagName = tagName; this.attributes = {}; this.children = []; this._text = ''; this.value = ''; this.hidden = false; this.disabled = false; this.open = false; this.dataset = {}; this.scrollTop = 0; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => typeof child === 'string' ? child : child.textContent).join(''); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { if (['hidden', 'disabled', 'open'].includes(name)) return this[name] ? '' : null; return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  get scrollHeight() { return this.children.length * 24; }
  set src(value) { this.setAttribute('src', value); }
  get src() { return this.getAttribute('src') || ''; }
  set href(value) { this.setAttribute('href', value); }
  get href() { return this.getAttribute('href') || ''; }
  set dateTime(value) { this.setAttribute('datetime', value); }
}

async function createHarness({ capabilities = { serverTools: {}, downloadFile: {} }, initial = null, downloadResult = {} } = {}) {
  const elements = new Map();
  for (const match of html.matchAll(/<([a-z][a-z0-9-]*)\b([^>]*\bid="([^"]+)"[^>]*)>/gi)) {
    const element = new Element(match[1]);
    for (const attr of ['hidden', 'disabled', 'open']) element[attr] = new RegExp('\\b' + attr + '\\b').test(match[2]);
    elements.set(match[3], element);
  }
  const listeners = {}, calls = [], timers = new Map();
  let nextTimer = 1;
  const flush = async () => { await new Promise(setImmediate); await new Promise(setImmediate); };
  const clone = value => JSON.parse(JSON.stringify(value));
  const on = (name, callback) => { (listeners[name] ||= []).push(callback); };
  const window = { addEventListener: on };
  const dispatch = message => { for (const listener of listeners.message || []) listener({ source: parent, data: message }); };
  const respond = (id, result) => dispatch({ jsonrpc: '2.0', id, result });
  const send = params => dispatch({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params });
  const parent = { postMessage(message) {
    calls.push(clone(message));
    queueMicrotask(() => {
      if (message.method === 'ui/initialize') {
        if (initial) send(initial);
        respond(message.id, { protocolVersion: '2026-01-26', hostCapabilities: capabilities });
      } else if (message.method === 'ui/download-file') respond(message.id, downloadResult);
    });
  } };
  class ClockDate extends Date { constructor(...args) { super(...(args.length ? args : [NOW])); } static now() { return NOW; } }
  class Image {
    set src(value) { this._src = value; queueMicrotask(() => { if (value === 'data:image/jpeg;base64,' + GOOD_IMAGE) this.onload?.(); else this.onerror?.(); }); }
    get src() { return this._src; }
  }
  const document = { getElementById: id => elements.get(id), createElement: tag => new Element(tag), hidden: false, documentElement: { clientWidth: 1100 }, addEventListener: on };
  const addTimer = (callback, delay, repeat = false) => { const id = nextTimer++; timers.set(id, { callback, delay, repeat }); return id; };
  vm.runInNewContext(script, { window, parent, document, Image, URL, Date: ClockDate, setTimeout: addTimer, clearTimeout: id => timers.delete(id), setInterval: (callback, delay) => addTimer(callback, delay, true), clearInterval: id => timers.delete(id), ResizeObserver: undefined }, { filename: 'search-screen.html' });
  await flush();
  return {
    elements, calls, timers,
    element: id => elements.get(id),
    async send(value) { send(value); await flush(); },
    async input(query) { dispatch({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: { query } } }); await flush(); },
    async respond(id, value) { respond(id, value); await flush(); },
    async click(id) { const element = elements.get(id); if (!element.disabled) element.onclick?.(); await flush(); },
    async close() { dispatch({ jsonrpc: '2.0', id: 'teardown', method: 'ui/resource-teardown', params: {} }); await flush(); },
  };
}

function result(id, { status = 'running', query = 'Sample search', preview = null, rows, updatedAt = '2026-11-21T17:00:01.000Z' } = {}) {
  const activity = { id, query, status, createdAt: '2026-11-21T17:00:00.000Z', updatedAt, events: [{ stage: 'Opening search results in browser', url: 'https://example.org/search?q=sample' }] };
  if (status === 'completed') activity.result = { success: true, data: { web: rows || [{ title: 'Example source', url: 'https://example.org/source', description: 'A returned search snippet.' }] }, search: { warnings: [] } };
  if (status === 'failed') activity.error = 'Controlled failure';
  return { structuredContent: { success: true, kind: 'search_activity', activity }, ...(preview ? { _meta: { preview } } : {}) };
}
function preview(url = 'https://example.org/search?q=sample') { return { image: GOOD_IMAGE, url, capturedAt: new Date(NOW).toISOString() }; }

test('same-search updates retain the last successfully decoded frame with actual provenance and stale labels', async () => {
  const h = await createHarness();
  try {
    const capture = preview();
    await h.send(result('search-a', { preview: capture }));
    const src = h.element('frame').src;
    assert.equal(h.element('capture').hidden, false);
    assert.equal(h.element('frame-url').href, capture.url);
    assert.equal(h.element('capture-time').getAttribute('datetime'), capture.capturedAt);
    assert.equal(h.element('activity').open, false);
    await h.send(result('search-a', { updatedAt: '2026-11-21T17:00:02.000Z' }));
    assert.equal(h.element('frame').src, src);
    assert.match(h.element('frame-state').textContent, /no new frame/);
    assert.equal(h.element('frame-state').dataset.stale, 'true');
    await h.send(result('search-a', { preview: { ...capture, image: '/9j/AAAA' }, updatedAt: '2026-11-21T17:00:03.000Z' }));
    assert.equal(h.element('frame').src, src, 'decoder rejection must retain the valid older image');
    await h.send(result('search-a', { status: 'completed', preview: { ...capture, url: 'javascript:alert(1)' }, updatedAt: '2026-11-21T17:00:04.000Z' }));
    assert.equal(h.element('frame').src, src);
    assert.equal(h.element('frame-url').href, capture.url);
    assert.equal(h.element('results-section').open, false);
    assert.match(h.element('frame-state').textContent, /Last captured view/);
  } finally { await h.close(); }
});

test('new searches, errors and teardown clear prior content and an old pending poll cannot overwrite a new search', async () => {
  const h = await createHarness();
  try {
    await h.send(result('search-old', { query: 'Old query', preview: preview() }));
    await h.click('refresh');
    const oldCall = h.calls.find(call => call.method === 'tools/call');
    assert.deepEqual(oldCall.params, { name: 'search_status', arguments: { id: 'search-old' } });
    await h.input('New query');
    assert.equal(h.element('frame').getAttribute('src'), null);
    assert.equal(h.element('markdown-preview').value, '');
    assert.equal(h.element('results').children.length, 0);
    await h.send(result('search-new', { status: 'completed', query: 'New query', preview: preview('https://example.net/new') }));
    await h.respond(oldCall.id, result('search-old', { status: 'completed', query: 'Old query', preview: preview() }));
    assert.equal(h.element('query').textContent, 'New query');
    assert.equal(h.element('frame-url').href, 'https://example.net/new');
    assert.match(h.element('markdown-preview').value, /New query/);
    await h.send({ isError: true, content: [{ type: 'text', text: 'Controlled tool error' }] });
    assert.equal(h.element('status').textContent, 'Unavailable');
    assert.equal(h.element('frame').getAttribute('src'), null);
    assert.equal(h.element('markdown-preview').value, '');
    assert.match(h.element('footer').textContent, /No browser image/);
    await h.send(result('search-new', { status: 'completed', query: 'New query', preview: preview() }));
    assert.equal(h.element('capture').hidden, false);
    await h.close();
    assert.equal(h.element('frame').getAttribute('src'), null);
    assert.equal(h.element('download').disabled, true);
    assert.equal(h.timers.size, 0);
  } finally { await h.close(); }
});

test('a host without serverTools renders its early snapshot and prepares Markdown without polling or downloads', async () => {
  const h = await createHarness({ capabilities: {}, initial: result('snapshot-only', { status: 'completed', query: 'Read-only host' }) });
  try {
    assert.equal(h.element('status').textContent, 'Completed');
    assert.equal(h.element('query').textContent, 'Read-only host');
    assert.equal(h.element('refresh').disabled, true);
    assert.equal(h.element('pause').disabled, true);
    assert.equal(h.element('download').disabled, true);
    assert.match(h.element('markdown-preview').value, /Search-result snippets/);
    assert.match(h.element('export-status').textContent, /does not offer downloads/);
    await h.click('download');
    assert.equal(h.calls.filter(call => ['tools/call', 'ui/download-file'].includes(call.method)).length, 0);
  } finally { await h.close(); }
});

test('completion prepares deterministic UTF-8 snippet Markdown with warnings and uses the advertised host download API', async () => {
  const h = await createHarness();
  try {
    const completed = result('internal-id-not-for-export', { status: 'completed', query: 'Café results', rows: [{ title: 'Café source', url: 'https://example.org/article', description: 'First line.\nUnicode: café 東京. <script>not executable</script>', warning: 'Provider warning', metadata: { statusCode: 403, renderingFallback: true, truncated: true } }] });
    await h.send(completed);
    const markdown = h.element('markdown-preview').value;
    assert.match(markdown, /Search-result snippets/);
    assert.match(markdown, /https:\/\/example\.org\/article/);
    assert.match(markdown, /café 東京/);
    assert.match(markdown, /HTTP status 403/);
    assert.match(markdown, /Rendering fallback/);
    assert.match(markdown, /reported truncated/);
    assert.doesNotMatch(markdown, /internal-id-not-for-export/);
    assert.equal(Buffer.from(markdown, 'utf8').toString('utf8'), markdown);
    await h.send(completed);
    assert.equal(h.element('markdown-preview').value, markdown);
    await h.click('download');
    const call = h.calls.find(call => call.method === 'ui/download-file');
    assert.deepEqual(call.params.contents, [{ type: 'resource', resource: { uri: 'file:///seek-x-cafe-results.md', mimeType: 'text/markdown', text: markdown } }]);
    assert.match(h.element('export-status').textContent, /host accepted/);
    assert.equal(h.calls.filter(call => call.method === 'tools/call').length, 0);
  } finally { await h.close(); }
});

test('declined or unconfirmed downloads preserve the preview and never claim a saved file', async () => {
  for (const downloadResult of [{ isError: true }, null]) {
    const h = await createHarness({ downloadResult });
    try {
      await h.send(result('download-declined', { status: 'completed' }));
      await h.click('download');
      assert.match(h.element('export-status').textContent, /did not confirm/);
      assert.equal(h.element('markdown-section').open, true);
      assert.match(h.element('markdown-preview').value, /A returned search snippet/);
      assert.doesNotMatch(h.element('export-status').textContent, /saved|succeeded/i);
    } finally { await h.close(); }
  }
});
