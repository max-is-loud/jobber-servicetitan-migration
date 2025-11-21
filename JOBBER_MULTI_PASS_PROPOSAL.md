# Multi-Pass Jobber Extraction Proposal

## Objective
Evaluate a staged extraction strategy that separates lightweight discovery from full data retrieval, to improve predictability, completeness checks, and operational control compared to the current single-pass approach.

## Why Consider Multi-Pass
- **Predictable effort**: Get counts and relationship density before committing to a long run.
- **Early risk surfacing**: Identify heavy entities (e.g., clients with many attachments/notes) and adjust rate limits or pagination before deep fetch.
- **Targeted retries**: Re-run only the expensive objects instead of the entire migration.
- **Better monitoring**: Compare expected vs. retrieved counts to flag gaps quickly.

## Proposed Passes

### Pass 1: Discovery & Mapping (lightweight)
Goal: Build an inventory of what exists without fetching full payloads.

- **What to fetch**
  - Per entity type: totalCount, page cursors, minimal identifiers (id, updatedAt/createdAt).
  - Per parent object: counts of related items (notes, attachments, line items, visits, tasks, payments, comments) using `totalCount` where available.
  - Schema/field presence sampling (e.g., a handful of records per type) to detect optional fields worth requesting.
- **Query shape**
  - Use small `first` values (e.g., 20–50) with `pageInfo` only; avoid wide field selection.
  - Prefer `totalCount` or `edges { node { id updatedAt } }` to keep cost low; add `...Count` fields where exposed.
  - No binaries and no large text fields.
- **Outputs**
  - Inventory tables (SQLite) such as `entity_inventory` (type, id, updated_at, estimate_children) and `relation_inventory` (parent_type, parent_id, relation_type, count, cursor_hint).
  - Summary report: per-type totals, top-N heaviest parents by related-item count, estimated API cost/time given current rate limiter settings.
- **Uses**
  - Drive sizing (expected runtime), choose pagination, and decide whether to split work (e.g., chunk clients by updatedAt ranges).

### Pass 2: Full Extract
Goal: Retrieve complete records for each object, guided by the map.

- **What to fetch**
  - All fields for each entity type (clients, invoices, jobs, requests, quotes, etc.).
  - Related collections per object (notes, noteAttachments, line items, visits, tasks, payments).
  - Binary downloads (images/attachments) queued from discovered attachment references.
- **Execution model**
  - Create work queues seeded from Pass 1 inventories; mark per-object statuses (`pending` → `in_progress` → `done`/`failed`).
  - Use adaptive concurrency informed by Pass 1 density (e.g., throttle objects with huge note counts).
  - Resume support: re-use inventory checkpoints; skip already `done` objects.
- **Data integrity**
  - Per-type completeness checks: compare fetched counts vs. map totals; flag deltas.
  - Per-object validation: confirm related-item counts match map; enqueue follow-up fetch if short.
  - Store crawl timestamp to detect drift; optionally revalidate changed objects (updatedAt > pass1_cutoff).
- **Binaries**
  - Attachment queue keyed by parent id; batch downloads with existing downloader.
  - Retry/backoff for failed binaries without reprocessing parent payload.

### Optional Pass 3: Reconciliation & Deltas
Goal: Close gaps and handle drift between passes.

- Re-run discovery for types with discrepancies to produce delta queues.
- Verify attachment download success vs. expected counts.
- Produce final completeness report (map totals vs. extracted rows and binary successes).

## Operational Flow (CLI Sketch)
- `tightbeam migrate map` → run Pass 1, write inventories and a summary report.
- `tightbeam migrate extract [--from-map <timestamp>]` → run Pass 2 using a chosen map snapshot.
- `tightbeam migrate reconcile [--from-map <timestamp>]` → optional Pass 3 to close gaps.

## Expected Benefits
- Early visibility into scale and hotspots before expensive work.
- Reduced rerun scope: retry only failed/heavy objects.
- Better SLAs: ability to estimate runtime and cost from Pass 1.
- Clear completeness accounting: map totals vs. extracted totals vs. binaries.

## Integration Considerations
- **Schema**: Add inventory tables and per-object status tracking; keep them separate from final data tables.
- **Coordinators/Extractors**: Teach extractors to run in “map” mode (counts/ids only) vs. “hydrate” mode (full fields). Coordinators orchestrate mode selection and work queues.
- **Rate limiting**: Pass 1 can run with higher concurrency (cheap queries); Pass 2 reuses existing token bucket/backoff. Use Pass 1 density data to set page sizes and parallelism per entity.
- **Resumability**: Persist map snapshots with timestamps; allow hydrate to pick a snapshot and skip completed objects.
- **Data drift**: Record `pass1_cutoff` timestamp; during hydrate, flag any records with `updatedAt > cutoff` for re-fetch or reconciliation pass.
- **Reporting**: Extend reports to show (a) discovered totals, (b) extracted totals, (c) attachment success rates, (d) failed object list for reruns.

## Risks / Open Questions
- Jobber API coverage for counts: some relations may not expose `totalCount`; may need small-sample edge fetches to estimate density.
- Drift between passes: long gaps could make the map stale; may need to enforce short lag or run reconciliation.
- Storage overhead: inventories add storage but should be small (id + timestamps + counts).
- Complexity: Coordinators gain new modes and queue management; needs careful UX to stay simple.

## Recommendation
Proceed with a spike to prototype Pass 1 on 2–3 entity types (e.g., clients, jobs, invoices). Measure:
1) query costs/time for discovery, 2) accuracy of density estimates vs. actual hydration, 3) operational ergonomics. Use those results to lock the schema and CLI contract before wider rollout.

---

# PRD: Multi-Pass Migration Refactor

## Goals
- Make migrations predictable by separating discovery from full extraction and providing upfront scale estimates.
- Improve completeness and integrity with per-object accounting and reconciliation of counts vs. actual fetches.
- Reduce rerun scope by enabling targeted retries on failed or heavy objects instead of whole-pipeline restarts.
- Keep within API limits while supporting tuned concurrency and cost-aware query shapes per entity type.
- Provide clear operator UX (CLI and reports) to choose a map snapshot, run extraction, and reconcile gaps.

## Non-Goals
- Changing the fundamental target schema for migrated data (final tables stay the same).
- Introducing new destination formats (CSV/XLSX exports are out of scope for this PRD).
- Building a full scheduler/service; this remains a CLI-first workflow.

## Personas
- **Operator**: runs migrations for customers, needs predictable runtime and clear failure surfaces.
- **Developer**: maintains extractors/coordinator, needs observability and testability for new modes.

## User Stories
- As an operator, I can run `tightbeam migrate map` to get counts and hotspots before committing to a long extraction.
- As an operator, I can select a specific map snapshot when running extraction so I know what I’m targeting.
- As an operator, I can see which objects failed and re-run just those without redoing everything else.
- As an operator, I can confirm completeness by comparing discovered totals vs. extracted totals and attachment success.
- As a developer, I can run the extraction in “map” or “extract” mode using the same extractors/coordinator code paths.

## Functional Requirements
- **Modes**
  - Map mode fetches counts/ids/cursors and relation totals with minimal fields; no binaries.
  - Extract mode hydrates full records and binaries using queues seeded from a chosen map snapshot.
  - Optional reconcile mode re-runs discovery for discrepant types and queues deltas.
- **Data collection**
  - Inventory tables store per-entity and per-relation counts, timestamps, and cursor hints.
  - Work queues track per-object status (`pending`, `in_progress`, `done`, `failed`) for extraction.
  - Attachment queue tracks binary download status separate from parent payload status.
- **Completeness checks**
  - Per-type: extracted count must match mapped total (or discrepancy flagged with reason).
  - Per-object: related-item counts should match mapped expectations; shortfalls flagged for retry.
- **CLI UX**
  - `tightbeam migrate map [--entities ...] [--snapshot-label ...]`
  - `tightbeam migrate extract [--from-map <timestamp|label>] [--entities ...] [--resume]`
  - `tightbeam migrate reconcile [--from-map ...]`
  - Reports emitted with map totals, extract totals, attachment success, and failure lists.
- **Resumability**
  - Map snapshots persisted with timestamp/label; extract can resume using the same snapshot.
  - Extraction restarts skip `done` objects and requeue `failed` ones.
- **Performance controls**
  - Page size and concurrency adjustable per entity type; defaults derived from map density.
  - Respect existing rate limiter/backoff; allow safer settings in map mode and tuned settings in extract.

## Non-Functional Requirements
- Extraction and discovery must honor Jobber rate limits; no increase in throttling events vs. current baseline.
- Minimal additional storage overhead (inventory/queue tables should remain small relative to payload tables).
- Backward compatibility: default `tightbeam migrate start` behavior should remain, or be aliased to map+extract with sensible defaults.
- Observability: logs and reports must surface discrepancies, retries, and attachment download status.

## Scope / Out of Scope
- In scope: coordinator/extractor refactor for dual modes; new inventory/queue schema; CLI additions; reporting updates; tests.
- Out of scope: destination schema redesign; new export formats; parallel multi-account orchestration.

## Acceptance Criteria
- Map mode produces a snapshot containing per-entity totals and per-parent relation counts for configured entities.
- Extract mode can target a snapshot and complete with per-object status tracked; rerun processes only pending/failed.
- Reports show mapped vs. extracted counts and attachment success rates; discrepancies are clearly enumerated.
- Attachment downloads are decoupled enough to retry without re-fetching parent payloads.
- Rate limiting settings are respected; no regressions in throttling frequency in test runs vs. current single-pass flow.
- Tests cover map/extract mode wiring, inventory/queue persistence, and report generation for both success and discrepancy cases.

## Data Model Changes (proposed)
- `entity_inventory(entity_type, entity_id, updated_at, discovered_at, estimated_relations_json, map_snapshot_id)`
- `relation_inventory(parent_type, parent_id, relation_type, count, cursor_hint, map_snapshot_id)`
- `map_snapshot(id, label, created_at, entities_included, pass1_cutoff)`
- `extract_queue(entity_type, entity_id, status, last_error, attempt_count, map_snapshot_id, updated_at)`
- `attachment_queue(parent_type, parent_id, attachment_id, status, last_error, attempt_count, map_snapshot_id, updated_at)`
- Lightweight indexes on (map_snapshot_id, status) for queues; (entity_type, entity_id) for joins with final tables.

## API/Query Changes
- Map mode: queries request `totalCount`, `pageInfo`, and minimal identifiers plus relation counts; avoid wide payloads and binaries.
- Extract mode: reuses existing full queries but may tune pagination and nested selection based on map density (e.g., smaller `first` for heavy parents).
- Maintain pagination cursors to allow chunked extraction for very heavy entities.

## CLI/UX
- New commands/subcommands as noted above with clear help text and examples.
- Reports saved to `reports/` with timestamps: `map-<ts>.json`/`.md`, `extract-<ts>.json`/`.md`.
- Verbose logging flags to show queue progress and retry reasons; quiet mode to keep output clean.

## Performance Targets
- Map run should complete in minutes on typical accounts (low field selection, small `first`).
- Extract run throughput should be on par with or better than current single-pass, with fewer full-pipeline reruns on failure.
- Attachment retries isolated so a failed binary does not stall unrelated entities.

## Observability & Monitoring
- Metrics/logging for: throttling events, retries per queue, discrepancy counts, attachment failures, time per entity type.
- Reports include a summary of retries and remaining failures.

## Risks & Mitigations
- **Stale map**: if long lag between map and extract, enforce max age or require reconcile; surface warning in CLI/report.
- **Missing counts**: some relations may not expose `totalCount`; fall back to sampled edges and mark estimates vs. exact.
- **Complex UX**: simplify defaults (e.g., `migrate start` could run map then extract in one go) while exposing advanced flags.
- **Storage growth**: purge old map snapshots or keep a cap; allow `--prune-maps` option.
- **Divergent schemas**: ensure inventory aligns with existing entity identifiers to avoid mismatches.

## Rollout Plan
1) Implement map mode and schema additions; ship behind a feature flag/default-off.
2) Add extract mode consuming snapshots; wire reports; enable resumability.
3) Integrate reconcile/delta option and finalize reports.
4) Flip default so `migrate start` can optionally run map+extract in one flow once stable.
5) Document operator workflow and add tests to CI for both modes.

## Validation Plan
- Unit tests for inventory/queue persistence and CLI argument handling.
- Integration tests using staged fixtures to simulate map → extract → reconcile flows.
- Performance smoke test on a sample account to compare throttling and runtime vs. current behavior.
- Manual dry-run with attachment failures to confirm retry isolation and reporting.
