# Source checks in Wayloom

Built-in rendered page extraction records a private capture receipt, then compares all returned content sections and capture diagnostics against a fresh read of the same extraction root and document. The audit includes SHA-256 hashes, capture/readback observation identifiers, matched sections and explicit capture limits. The private receipt is released after auditing so saved results do not retain browser handles.

`coverage.result_complete` means every returned aggregate was checked. `all_fields_observed` means the capture was intact and all aggregates matched readback in the same document. `source_complete_within_capture_limits` requires intact matching readback, no capture truncation, and settled, untruncated readiness sampling. It is not whole-site coverage. `acquisition.ready` is false for a timeout or sampler limit and null when readiness was not observed; those conditions stay visible even when every returned value matches. A changed page can have complete audit coverage while failing the match check. Clipped content remains marked truncated even when its retained prefix matches. `semantic_verification` remains `not_established`: content equality does not prove relevance, truthful source claims or the task outcome.

Model-selected results retain their own source provenance. For an explicit single `extract` action with observed mode and a closed one-field string schema named `salary`, the local model can choose up to eight sources to cover all requested pay ranges. Every chosen source is checked together before returning any result. A stale source causes one bounded recapture without replaying browser actions. Unknown, repeated or excluded IDs, ambiguity and over-budget requests fail instead of inventing a salary.

Bounded monetary excerpts expose values beyond a group's opening preview. Each excerpt carries exact offsets into the full retained source. They do not replace the original source or reconstruct pay. Candidate contexts remain separate, all plausible candidates must fit the model message budget, and full selected groups are returned with original wording and units. The single-source behavior for other schemas remains in place.

Use `fetch_page` for a page capture. For salary selection, use `start_browser_task` with `actions:[{"action":"extract"}]`, a precise goal, `agent_config.result_mode:"observed"` and an object output schema with only required string field `salary` and `additionalProperties:false`.

Source checks do not authorize imports or notifications. Downstream product/store identity checks, quarantine and email gates remain separate. In particular, a faithfully captured page containing unrelated retailer records remains unsuitable for import.


When several selected salary sources overlap, Wayloom removes a quote only if its exact live DOM nodes and values are contained in another selected source. All selected sources pass atomic readback before compaction. Equal strings in different DOM locations remain separate. Collection provenance records `selected_source_ids`, emitted `source_ids`, `omitted_sources` with their covering IDs, and all original source receipts. This does not merge distinct current/earlier contexts or deduplicate by amount alone.

Readiness checks honor a busy main root, and disclose both DOM traversal and text sampling limits. Exact readback and acquisition readiness are separate evidence; matching a stable loading page cannot establish a complete capture.


Observed multi-field records can now share one selection decision and one atomic source read. Known document metadata can be declared with `x-wayloom-source`, reducing inference work and making the requested source explicit. See [STRUCTURED_RECORDS.md](STRUCTURED_RECORDS.md) for the supported schema and a complete request.
