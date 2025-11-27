# PRD – Tightbeam v2: Jobber “Max Extract” Refactor

**Working title:** `jobber-max-extract`
**Owner:** Max / Tightbeam-v2
**Branch:** `feature/jobber-max-extract-refactor` (placeholder)
**Status:** Draft
**Date:** 2025-11-24

---

## 1. Problem Statement

The current Jobber export implementation is a first iteration: it works, but it’s not systematically designed to:

* Reliably extract *all* Jobber data at scale.
* Respect Jobber’s GraphQL cost & rate limits in a predictable, tunable way.
* Preserve Jobber’s relational structure in a local, queryable store.
* Capture all notes and noteAttachments (including URLs for binary files) in a structured manner.
* Cleanly separate metadata extraction from binary file download.

For serious ServiceTitan (and other) migrations, we need something much more robust: a professional-grade ETL pipeline that can **suck out every last bit of data** from a Jobber account, while retaining relationships and staying within Jobber’s constraints.

---

## 2. Goals & Non-Goals

### 2.1 Goals

1. **Complete data coverage (Jobber → SQLite)**

   * Extract *all* accessible entities (within the app’s OAuth scopes) from a Jobber account via GraphQL.
   * Preserve relationships between entities (foreign keys) to mirror Jobber’s logical model as closely as is practical.
   * Include **notes** and **noteAttachments** metadata for all supported parent entities.

2. **Separation of concerns: metadata vs binaries**

   * **Pass 1 – GraphQL ETL:** Extract entities + notes + noteAttachments metadata.
   * **Pass 2 – Binary downloader:** Store files to a flat folder with hash-based naming and update SQLite.

3. **Jobber-optimized, cost-aware extraction**

   * Use cursor-based pagination for all large lists.
   * Tune per-entity page sizes.
   * Apply rate limiting based on Jobber’s published limits.

4. **Resumable, idempotent extraction**

   * Restart-safe at any point.
   * Track progress via cursors and per-entity state.

5. **ServiceTitan-friendly staging**

   * Maintain Jobber-like relational structure.
   * No transform to ST schema here.

6. **Observability & debugging**

   * Structured logs.
   * Optional dry-run / schema-only modes.

### 2.2 Non-Goals

* ServiceTitan data mapping.
* Rewriting full CLI UX.
* Mutations or write operations.
* Web dashboards.

---

## 3. Context & Constraints

### 3.0 Jobber API Rate Limits & Query Cost Model (Publicly Documented)

**HTTP Request Rate Limits:**

* Jobber applies a **DDoS protection limit of 2,500 requests per 5 minutes**.
* This averages to ~**8.3 requests/second** as a hard ceiling.
* If exceeded, the API returns **HTTP 429** with a `Retry-After` header (when provided).

**GraphQL Query Cost Throttling:**

* Jobber also enforces a **GraphQL complexity / cost limit**, independent of raw request count.
* High‑cost queries (deeply nested fields, large page sizes) may trigger errors even if request rate is low.
* Jobber recommends:

  * Limiting nested relationships.
  * Keeping page sizes modest.
  * Splitting complex queries into multiple simpler ones.

**However, for migration purposes we cannot exclude any fields.** Instead of omitting data, Tightbeam will:

* Request *all* fields required for a full-fidelity export.
* Break large or deeply nested queries into multiple smaller queries.
* Use careful pagination and entity-by-entity extraction to stay under Jobber’s cost limits while still retrieving the full dataset.

**Pagination Best Practices (per Jobber guidance):**

* Always use `pageInfo { hasNextPage endCursor }`.
* Recommended page size: **25–50 items** for heavy objects.
* Larger pages increase cost and may hit complexity throttles.

**Implications for Tightbeam Max Extract:**

* Global rate limiter will target ~**4–6 req/s** to remain safely under the ceiling.
* Page sizes tuned per-entity (10–50 depending on cost weight).
* Backoff on 429 and cost-based errors is mandatory.

#### 3.0.1 Jobber vs Tightbeam: API Usage Philosophy

| Aspect                         | Jobber’s Published Guidance                         | Tightbeam Migration Requirement                                                    |
| ------------------------------ | --------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Fields fetched per query       | Avoid unnecessary fields; fetch only what you need  | Fetch **all fields needed for full-fidelity export**; do not omit migratable data  |
| Query complexity               | Keep queries simple and shallow                     | Split complex graphs into **multiple simpler queries** rather than dropping fields |
| Page size                      | Modest page sizes to avoid cost limits              | Tune page size per entity (10–50) while still iterating over **all** records       |
| Nested relationships           | Limit depth and breadth                             | Use **multiple passes** / follow-up queries instead of deep nests                  |
| Handling rate / cost limits    | Back off or simplify queries when limits hit        | Back off **without losing coverage**; never permanently skip entities or fields    |
| Primary optimization objective | Stability & responsiveness for general integrations | **Completeness and data integrity** for one-time or infrequent bulk migrations     |

---

### 3.1 Jobber API Characteristics

* GraphQL endpoint: `https://api.getjobber.com/api/graphql`.
* Strict rate limits (2500 req / 5 minutes + cost-based throttles).
* Primary entities: clients, properties, requests, quotes, jobs, visits, invoices, line items, payments, etc.
* Notes & attachments appear across many primary entity types.

### 3.2 Existing Tightbeam Architecture

* Python CLI.
* SQLite staging.
* Future-proofing for ServiceTitan transform.
* Desire for structured relational preservation and hashed attachments.

---

## 4. High-Level Solution

A **two-pass ETL pipeline**:

1. **Pass 1 – Metadata Extraction:**

   * Paginated GraphQL queries for all entities.
   * Includes notes and attachments metadata.
   * Saves everything to SQLite with relational links.

2. **Pass 2 – Attachments:**

   * Iterate attachment metadata.
   * Download binaries, store via hashed filename.
   * Update SQLite with final local paths & status.

---

## 5. Detailed Requirements

### 5.1 Entities & Relationships to Capture

**Priority 1 Entities**

* clients
* properties / clientProperties
* requests
* quotes
* jobs
* visits
* invoices
* invoiceLineItems
* payments / paymentCollections
* notes
* noteAttachments

**Priority 2 Entities**

* tasks / reminders
* timesheets / timeEntries
* schedules / events
* users / teamMembers

**Relationship Requirements**

* Use Jobber IDs as primary keys.
* Model relationships with foreign keys.
* Store parent-child relations for notes and attachments.

### 5.2 SQLite Schema Design

**General Principles**

* One table per entity type.
* Jobber IDs as primary key.
* Use constraints where stable.

**Notes Table**

* id
* parent_type
* parent_id
* body
* author_id
* timestamps

**Note Attachments Table**

* id
* note_id
* remote_url
* filename_original
* content_type
* size_bytes
* local_path
* hash
* download_status
* download_error
* downloaded_at

---

## 6. Extraction Strategy (Pass 1)

### 6.1 Orchestration

* CLI: `tight jobber export --account <name> --sqlite-path jobber_export.db --entities all --resume`.
* Per-entity pipelines with progress tracking.
* Sequential by default; future optional concurrency.

### 6.2 Pagination

* Relay-style pagination.
* Per-entity page size tuning.
* Track `endCursor`, `hasNextPage`.
* Persist progress in `entity_sync_state`.

### 6.3 Rate Limiting

* Target 4–6 req/s.
* Handle 429 with exponential backoff.
* Auto-adjust queries if cost limit errors appear.

### 6.4 Query Design

* Named queries per entity.
* Fetch minimal fields required for mapping.
* Notes & attachments strategy (nested or top-level depending on Jobber exposure).

---

## 7. Attachment Downloader (Pass 2)

### 7.1 Inputs & Outputs

* Input: pending/error attachments.
* Output: hashed files + SQLite updates.

### 7.2 File Naming

* Flat directory.
* SHA256-based filename + original extension.

### 7.3 Download Logic

* Batch process (e.g., 100 at a time).
* HTTP GET streaming.
* Validate content.
* Retry failed downloads.
* Limit concurrency.

---

## 8. Resilience & Observability

### 8.1 Logging

* Structured logs with metadata (operation, entity, page size, cursor, etc.).

### 8.2 Metrics

* Use `entity_sync_state` for counts and completion indicators.
* Optional status CLI.

### 8.3 Retry & Resume

* Extraction: resume from last cursor.
* Downloader: only run pending/error attachments.

---

## 9. Non-Functional Requirements

* **Performance:** Hours are acceptable; correctness is priority.
* **Reliability:** No silent data loss.
* **Portability:** SQLite + folders should be relocatable.

---

## 10. Implementation Plan & Milestones

1. **M1 – Schema & Query Definitions**
2. **M2 – Core Extractor** (single entity)
3. **M3 – Multi-Entity Pipelines & Resume Support**
4. **M4 – Notes & Attachment Metadata**
5. **M5 – Rate Limiting & Backoff**
6. **M6 – Attachment Downloader**
7. **M7 – Hardening & Documentation**

---

## 11. Open Questions

1. Field selection & entity exposure.
2. Top-level vs nested notes strategy.
3. Stability / expiry of attachment URLs.
4. Optional parallelism for future optimization.

---

## 12. Jobber Entity Manifest (Canonical Schema Reference)

> **Important:** This PRD is *not* the canonical source of truth for Jobber’s schema. Field names and availability may change over time, and Jobber’s docs are copyrighted. To avoid hallucinations and drift, Tightbeam will rely on **machine-readable schema snapshots** checked into the repo (e.g., an introspected GraphQL schema file and/or hand-maintained markdown reference). This section defines the structure and expectations for that manifest.

### 12.1 Manifest Purpose

* Provide a single, authoritative reference for:

  * Which **entities** Tightbeam supports.
  * Which **fields** are expected on each entity.
  * Which fields are required for **identity**, **relationships**, and **migration**.
* Act as a guardrail for LLM-based tooling:

  * *If a field is **not** listed in the manifest, treat it as **non-existent** unless explicitly verified in live docs or schema.*

### 12.2 Manifest Location & Format (Implementation-Time Detail)

* The real manifest will live in the repo, for example:

  * `docs/jobber_entity_manifest.md` (human-readable), and/or
  * `schema/jobber_schema.graphql` (introspected from the live API).
* Suggested format (per entity):

  * Human-friendly table of fields (name, type, nullable, notes).
  * Machine-friendly block (YAML/JSON) used by tooling.

Example (illustrative only, **not** canonical):

```yaml
entity: Client
jobber_type: Client
primary_key: id
fields:
  - name: id
    type: ID!
    role: primary_key
  - name: createdAt
    type: DateTime!
    role: metadata
  - name: updatedAt
    type: DateTime!
    role: metadata
  - name: name
    type: String!
    role: display
  - name: email
    type: String
    role: contact
  # ... all other fields as discovered from the introspected schema ...
```

During development, the above block must be **generated or verified** against a fresh schema introspection, not invented.

### 12.3 Entity List (To Be Populated from Schema)

At minimum, the manifest will cover the following Jobber entities (names here are conceptual and must be tied to real Jobber GraphQL types when the schema file is generated):

* Client
* Property / ClientProperty
* Request
* Quote
* Job
* Visit
* Invoice
* InvoiceLineItem / LineItem
* Payment / PaymentCollection
* Note
* NoteAttachment
* Task / Reminder
* Timesheet / TimeEntry
* Schedule / Event
* User / TeamMember

For each entity above, the manifest MUST include:

1. **Primary key field(s)** (typically `id`).
2. **Foreign key fields** (e.g., `clientId`, `jobId`, `invoiceId`, etc.) that reflect Jobber relationships.
3. **Timestamps** (created/updated) where present.
4. **Status / enum fields** that materially affect migration logic.
5. Any additional fields required to reproduce the user-visible state in Jobber.

### 12.4 Rules for Using the Manifest (for LLM & Dev Tools)

* When generating queries or migrations:

  * **Only use fields listed** in the manifest *unless* you have the live schema open and explicitly confirm new ones.
  * If you need a field that is not listed, you MUST:

    1. Check the introspected schema or Jobber docs manually.
    2. Update the manifest in the repo.
* Do **not** rename or repurpose fields in code without updating the manifest.
* Treat the manifest as part of the contract between Tightbeam and Jobber.

This approach gives you a **concrete anti-hallucination rail** without attempting to freeze or copy Jobber’s full schema inside the PRD itself.
