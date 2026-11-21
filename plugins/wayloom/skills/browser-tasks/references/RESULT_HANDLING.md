# Complete results and task outcomes

## Read all requested result chunks

When get_run marks result_truncated, recover the same run through get_run_result if that tool is exposed. Start at offset `0`, retain result_json_chunk exactly, then use each returned next_offset until it is null. Offsets count JavaScript UTF-16 code units, not UTF-8 bytes or Unicode code points. Concatenate chunks in order and parse the complete JSON once. Do not parse each chunk as an independent JSON object, skip gaps, or start a second task to obtain missing chunks. If the tool is unavailable, report the result as incomplete rather than inventing missing content.

Pagination recovers the returned result; it cannot restore text clipped by the browser capture itself. Preserve coverage.text.truncated, source limits, result-audit limitations and readiness flags. A retained quote does not establish full-page coverage. Large-result recovery is read-only and must not replay website actions.

## Preserve the run and screen identity

Keep the exact `run_id`, request key, and connection from submission through screen display, polling, result reads, and export. Call `show_run_screen` promptly after receiving a confirmed ID when available, then poll `get_run` for that ID. Screen refresh is read-only and must not replay browser actions. Periodic captured images can expire; an unavailable frame is not a reason to start another task.

A `result_truncated` delivery flag and source capture truncation describe different limits. Recovering all JSON chunks resolves delivery truncation only. A result can be fully retrieved with untruncated page text while readiness sampling is limited; report each condition separately. Keep the original `get_run` envelope alongside any recovered result so status, steps, errors, and metrics are not lost in a downstream export.

## Separate execution from outcome

COMPLETED means execution ended. Inspect returned content and error/source metadata before claiming that the requested page or task succeeded. A completed empty result can be an unavailable page. If a document_response step is present, report its http_status/http_error for the main document; its absence means HTTP status is not established, not HTTP 200. HTTP 403 or a challenge page is not the requested content. Preserve the limitation; do not try to bypass the challenge.

For actions, verify the requested final state and any receipt against the returned source evidence. Exact text requests must use observed text, not a paraphrase. A visible checkbox state does not prove a saved backend state. Mixed/indeterminate state must not be presented as a definite verified boolean when that ambiguity is exposed. Use only completion predicates and source bindings actually advertised by the connection.

Observed mode provides source selection/readback; it does not guarantee that the model will plan or finish correctly. For known source selectors, explicit authorized actions and result contracts can avoid unnecessary inference. Do not guess selectors, declare success from a matching schema alone, or rerun non-idempotent actions after an uncertain response.

If a run stalls or cycles, inspect its existing steps and result. Any continuation is a new, explicitly scoped task for the remaining work; do not replay acknowledged side effects. Keep the original run ID and explain what remains unverified.

## Failed planned runs

Stop automatic execution at a failed terminal state. Read the existing run's error, steps, metrics, and available result before deciding what remains. Cite the observed reason, such as a context limit or invalid action, without guessing that the site failed. Preserve whether the error says that no action executed from that model response; that statement does not erase earlier actions in the run.

Check for acknowledged submissions, saves, or other side effects before any continuation. A timeout or failed planner response does not establish that no change occurred. Never automatically replay a mutating task, switch connections to retry it, or increase the original task's bounds as a recovery strategy. A new task may perform remaining work only within the existing authorization and after its scope excludes completed or uncertain side effects. Read-only result and screen requests can continue on the original ID.

If the error and earlier steps are unavailable, say that the outcome is unverified. Do not report success, fabricate a failure cause, or invent selectors or navigation targets. For a future read-only task with a known URL, a deterministic page read may avoid planning; treat it as a separate requested acquisition rather than recovered evidence for the failed task.

## Optional current-text readback

If the connection advertises `agent_config.live_text_fields`, a caller can opt selected required top-level string fields into current-value readback. For example, merge these fields into an authorized goal-driven request:

```json
{
  "output_schema": {
    "type": "object",
    "properties": {"status": {"type": "string"}},
    "required": ["status"],
    "additionalProperties": false
  },
  "agent_config": {"live_text_fields": ["/status"]}
}
```

This requests a current visible text value. It does not mean the first value seen, an original quotation, a computed result or a generated summary. Do not enable it for those meanings. The server validates the configuration before browser actions and the MCP endpoint rejects invalid configuration before dispatch. Use only fields supported by the actual connection schema.

The server privately binds an exact, unique, complete whole-text match from the decision snapshot and rereads that same source after inference. It does not add another model call or replay website actions. It does not expand a shortened phrase into a longer receipt or guess a source by similarity. Ambiguous, unmatched or limited captures remain unchanged and explicitly unverified. Changed documents, nodes or named context fail rather than being rebound to a different source. This is source readback, not proof of the intended entity, successful persistence or the entire user goal.

In the run steps, inspect `result_readback.live_text`. `observed_current` includes the binding method, source ID, whether the value changed, and value hashes. `unverified` is a limitation; do not describe that field as corrected or verified. Existing explicit page/value references may be marked not applicable to this additional text path.

For repeatable workflows with known, observed selectors and action order, prefer explicit actions plus `result_contract` and an appropriate completion gate. That avoids relying on the local model to choose every control. Do not combine those modes with live_text_fields. Batch size alone is not evidence of better planning or correctness, and increasing it must not be treated as a recovery for an already submitted task.
