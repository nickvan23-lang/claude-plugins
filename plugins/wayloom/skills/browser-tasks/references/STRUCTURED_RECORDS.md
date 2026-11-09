# Observed records and declared metadata

For an explicit single default `extract` action, observed mode can select sources for 2–8 required string fields in one model decision. Each field can use up to eight sources. The selected sources are read once as a union; all fields are assembled from that one validated observation. Missing or ambiguous required fields fail the task instead of producing a partial record. A stale source permits one bounded recapture, without replaying browser actions.

For metadata whose source is known, declare `x-wayloom-source` on the field. Supported values are `page.title` and `page.url`. These are literal browser properties: a document title is not necessarily a job heading, and the current address is not necessarily an application link. Bindings are interpreted in observed mode. Other fields remain model-selected.

Replace the URL and request key in this example. Use a new request key for a new task; reuse the same key and identical arguments only to recover/retry the same task.

```json
{
  "request_key": "replace-with-a-new-request-key",
  "url": "https://example.com/job",
  "actions": [{"action": "extract"}],
  "goal": "Read the document title, current browser address, and all published pay ranges with original labels and stated units.",
  "output_schema": {
    "$id": "urn:my-app:job-record-v1",
    "type": "object",
    "properties": {
      "title": {"type": "string", "x-wayloom-source": "page.title"},
      "source_url": {"type": "string", "x-wayloom-source": "page.url"},
      "salary": {"type": "string", "description": "All published hiring, annual and hourly ranges, including any midpoint, with their labels and units."}
    },
    "required": ["title", "source_url", "salary"],
    "additionalProperties": false
  },
  "agent_config": {"result_mode": "observed", "max_steps": 4, "max_duration_seconds": 90}
}
```

Known title/URL fields do not need model selection. If `salary` is the only unbound field, the existing focused salary catalog is used. An entirely declared explicit-action result needs no inference or model configuration. A natural-language workflow without explicit actions still needs a model for planning.

The result-selection evidence reports `model_requests`, `source_selected_by`, and a `selection_method` for each field. Declared fields include `declared_source`; inferred fields retain model-selected source IDs and exact readback receipts. Repeated source quotes are omitted only when shared DOM membership proves containment. All field readbacks share an observation; no old field values are cached between tasks.

`$id` identifies a schema, not a task. It can be reused across requests. Validation is cached by the complete JSON definition with isolated compiler namespaces, capped at 32 retained entries and 2 MiB of serialized definitions. Compiled-code overhead is additional. Oversized definitions still validate but are not retained. Definitions are self-contained; they do not register schemas for other requests. Asynchronous validation is awaited before returning a result, including rejection of invalid data and acceptance of valid falsy values.

The shared selection catalog is bounded to 6,500 bytes; the focused salary catalog to 4,500 bytes. Required user instructions and competing retained sources are not silently dropped to fit. Named field selections prevent positional association mistakes, but source meaning remains a model judgment for unbound fields. Readiness, capture limits, source truth and downstream import eligibility remain separate checks. See [SOURCE_CHECKS.md](SOURCE_CHECKS.md).
