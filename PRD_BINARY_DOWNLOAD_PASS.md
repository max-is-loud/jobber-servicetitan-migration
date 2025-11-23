# PRD: Binary Download Pass for Multi-Pass Migration

## Overview

Add a dedicated binary download pass to the multi-pass migration system, separating attachment metadata extraction from binary file downloads. This enables better resumability, selective downloading, and independent control over network-intensive operations.

## Problem Statement

Currently, the extract pass performs both entity metadata extraction and binary attachment downloads in a single operation. This creates several issues:

1. **Mixed Concerns**: GraphQL API calls (fast) and S3 downloads (slow, network-dependent) are interleaved
2. **Poor Resumability**: Network interruptions require re-extracting entities to retry downloads
3. **All-or-Nothing**: Cannot extract metadata without committing to downloading all binaries
4. **Resource Constraints**: Cannot pause downloads to manage bandwidth or storage
5. **Data Loss**: Attachments beyond `pagination.nested_notes` limit are silently skipped

## Goals

### Primary Goals
1. Separate attachment metadata extraction from binary downloads
2. Enable pause/resume for binary downloads without re-extraction
3. Support selective downloading (by entity type, file type, size, etc.)
4. Provide clear progress tracking for download operations
5. Eliminate data loss from pagination limits

### Secondary Goals
1. Maintain backward compatibility with current extract behavior
2. Optimize API costs by decoupling GraphQL queries from S3 bandwidth
3. Enable download prioritization strategies
4. Support partial downloads for testing or previews

## Non-Goals

- Real-time streaming of attachments during extraction
- Attachment content transformation or processing
- CDN caching or asset optimization
- Attachment deduplication across entities

## Solution Architecture

### High-Level Design

Transform the 3-pass system into a 4-pass system:

```
Pass 1: Map (Discovery)
  └─> Entity IDs + relation counts + density analysis

Pass 2: Extract (Metadata)
  └─> Full entity data + notes + attachment URLs
  └─> Populate attachment_queue (status: pending)
  └─> NO binary downloads

Pass 3: Download (Binaries) ← NEW
  └─> Process attachment_queue entries
  └─> Download binaries with retry logic
  └─> Update status: pending → in_progress → done/failed
  └─> Support pause/resume

Pass 4: Reconcile (Gap Closure)
  └─> Delta detection + retry failed attachments
  └─> Final completeness validation
```

### Database Schema

**Existing** - `attachment_queue` table (already implemented):

```sql
CREATE TABLE attachment_queue_item (
    attachment_id TEXT PRIMARY KEY,
    parent_type TEXT NOT NULL,
    parent_id TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending/in_progress/done/failed
    map_snapshot_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_error TEXT,
    attempt_count INTEGER DEFAULT 0,
    FOREIGN KEY (map_snapshot_id) REFERENCES map_snapshot(id)
)
```

**No schema changes needed** - existing table supports all requirements.

### CLI Commands

#### Extract Command (Modified)

```bash
# Extract metadata only (default behavior - NEW)
tightbeam migrate extract --snapshot-id <id>

# Legacy mode: extract + download in one pass (backward compatible)
tightbeam migrate extract --snapshot-id <id> --download-attachments
```

#### Download Command (NEW)

```bash
# Download all queued attachments for a snapshot
tightbeam migrate download --snapshot-id <id>

# Resume failed/interrupted downloads
tightbeam migrate download --snapshot-id <id> --resume

# Download attachments for specific entity types
tightbeam migrate download --snapshot-id <id> --entity clients --entity invoices

# Filter by file characteristics
tightbeam migrate download --snapshot-id <id> --file-type jpeg,pdf
tightbeam migrate download --snapshot-id <id> --min-size 100KB --max-size 10MB

# Dry run to preview download queue
tightbeam migrate download --snapshot-id <id> --dry-run

# Custom download directory
tightbeam migrate download --snapshot-id <id> --output-dir /path/to/attachments
```

#### Reconcile Command (Updated)

```bash
# Reconcile includes attachment retry by default
tightbeam migrate reconcile --snapshot-id <id>

# Skip attachment retry (metadata only)
tightbeam migrate reconcile --snapshot-id <id> --skip-attachments
```

## Technical Implementation

### Component Architecture

```
src/coordinators/
  └─ download_mode_coordinator.py (NEW)
     ├─ DownloadModeCoordinator
     ├─ run_download_pass()
     ├─ _process_download_queue()
     ├─ _filter_queue_items()
     └─ _generate_download_report()

src/cli/migrate.py
  └─ @migrate_app.command("download") (NEW)

src/reports/
  └─ download_report_generator.py (NEW)
     ├─ DownloadReportGenerator
     └─ generate_report()
```

### Existing Components to Reuse

- ✅ `AttachmentDownloader` (src/extractors/attachment_downloader.py)
- ✅ `Repository.get_attachment_queue()`
- ✅ `Repository.update_attachment_queue_status()`
- ✅ `Repository.create_attachment_queue()`
- ✅ Retry logic and error handling

### Key Implementation Details

#### 1. Extract Pass Modification

```python
# Current behavior:
ExtractModeCoordinator.run_extract_pass(
    queue_attachments=False  # Current default
)

# New behavior:
ExtractModeCoordinator.run_extract_pass(
    queue_attachments=True   # New default
)
```

#### 2. Download Coordinator

```python
class DownloadModeCoordinator:
    def run_download_pass(
        self,
        snapshot_id: str,
        entity_types: Optional[List[str]] = None,
        resume: bool = False,
        filters: Optional[DownloadFilters] = None,
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute binary download pass."""

        # 1. Get queue items
        queue_items = self._get_filtered_queue_items(
            snapshot_id, entity_types, resume, filters
        )

        # 2. Process downloads with progress tracking
        results = self._process_downloads(queue_items, output_dir)

        # 3. Generate download report
        report = self._generate_download_report(snapshot_id, results)

        return {
            "snapshot_id": snapshot_id,
            "total_attachments": len(queue_items),
            "downloaded": results["success_count"],
            "failed": results["failed_count"],
            "skipped": results["skipped_count"],
            "report_path": report["markdown_path"],
        }
```

#### 3. Download Filters

```python
@dataclass
class DownloadFilters:
    file_types: Optional[List[str]] = None  # ["jpeg", "pdf", "png"]
    min_size: Optional[int] = None          # Bytes
    max_size: Optional[int] = None          # Bytes
    parent_entity_types: Optional[List[str]] = None  # ["clients", "jobs"]
```

#### 4. Progress Reporting

```python
# Rich progress bar with download metrics
with Progress(
    TextColumn("[bold blue]{task.description}"),
    BarColumn(),
    DownloadColumn(),  # Shows downloaded size
    TransferSpeedColumn(),
    TimeRemainingColumn(),
) as progress:
    task = progress.add_task(
        f"Downloading {len(queue_items)} attachments...",
        total=len(queue_items)
    )
    # Process downloads...
```

## User Experience

### Workflow Example

```bash
# Step 1: Map entities
$ tightbeam migrate map --snapshot-label "prod-2025"
SUCCESS: Created map snapshot: abc123...
💡 Discovered 9,807 clients with 45,231 total attachments

# Step 2: Extract metadata (fast - no downloads)
$ tightbeam migrate extract --snapshot-id abc123
INFO: Extracting entity metadata only (attachments queued)...
SUCCESS: Extracted 9,807 entities in 15 minutes
💡 Queued 45,231 attachments for download
💡 Run 'tightbeam migrate download --snapshot-id abc123' to download binaries

# Step 3: Download binaries (can pause/resume)
$ tightbeam migrate download --snapshot-id abc123
Downloading attachments... ━━━━━━━━━━━━━━━ 45% (20,454/45,231) 125 MB/s 0:08:32
# User interrupts (Ctrl+C)

# Resume later
$ tightbeam migrate download --snapshot-id abc123 --resume
INFO: Resuming download... Skipping 20,454 completed attachments
Downloading attachments... ━━━━━━━━━━━━━━━ 100% (45,231/45,231)
SUCCESS: Downloaded 24,777 attachments, 0 failed

# Step 4: Reconcile
$ tightbeam migrate reconcile --snapshot-id abc123
SUCCESS: Reconciliation complete, 100% completeness
```

## Success Metrics

### Performance Targets

- Extract pass completes 50%+ faster (no download overhead)
- Download pass handles 100,000+ attachments without memory issues
- Resume operation adds <5 seconds overhead
- Download throughput: 50+ MB/s on modern connections

### Quality Targets

- Zero data loss from pagination limits
- 100% resumability for interrupted downloads
- <1% failure rate for valid attachment URLs
- Comprehensive error reporting for all failures

## Testing Strategy

### Unit Tests

- `test_download_coordinator.py` - Core coordinator logic
- `test_download_filters.py` - Filtering functionality
- `test_download_report_generator.py` - Report generation

### Integration Tests

- `test_download_mode_integration.py` - End-to-end download pass
- `test_download_resume.py` - Pause/resume scenarios
- `test_download_filtering.py` - Filter combinations

### CLI Tests

- `test_cli_download_command.py` - All CLI flag combinations
- `test_cli_download_backward_compat.py` - Legacy behavior preserved

### Manual Testing Scenarios

1. Extract 1000 entities, interrupt download at 50%, resume successfully
2. Filter downloads by file type, verify only matching files downloaded
3. Run legacy `extract --download-attachments`, verify same behavior as before
4. Download with network disconnected, verify graceful failure and retry

## Documentation

### Files to Update

1. `MULTI_PASS_MIGRATION.md` - Add download pass documentation
2. `README.md` - Update workflow examples
3. `DATABASE_SCHEMA.md` - Document attachment_queue usage patterns
4. New: `docs/attachment-download-strategies.md` - Best practices guide

### Example Documentation Sections

```markdown
## Download Pass

The download pass processes queued attachment downloads separately from
entity extraction, providing better control and resumability.

### Basic Usage

```bash
# Download all queued attachments
tightbeam migrate download --snapshot-id <id>
```

### Advanced Usage

```bash
# Resume interrupted downloads
tightbeam migrate download --snapshot-id <id> --resume

# Download specific entity types
tightbeam migrate download --snapshot-id <id> --entity clients

# Filter by file characteristics
tightbeam migrate download --snapshot-id <id> --file-type jpeg,pdf --max-size 10MB
```

### Download Strategies

**For large migrations:**
1. Extract all metadata first (fast)
2. Download critical attachments (invoices, quotes)
3. Download remaining attachments in batches
4. Use reconcile to verify completeness

**For bandwidth-constrained environments:**
- Use `--max-size` to download small files first
- Schedule large downloads during off-peak hours
- Use `--resume` if connection is interrupted
```
```

## Migration Path

### Backward Compatibility

**Current behavior preserved:**
```bash
# This continues to work exactly as before
tightbeam migrate extract --snapshot-id <id> --download-attachments
```

**New behavior is opt-in:**
```bash
# Users can adopt new workflow gradually
tightbeam migrate extract --snapshot-id <id>  # Metadata only
tightbeam migrate download --snapshot-id <id>  # Then download
```

### Deprecation Plan

No deprecation needed - both modes coexist:
- Legacy mode: `extract` with `--download-attachments` flag
- Modern mode: `extract` (metadata) + `download` (binaries)

## Future Enhancements

### Phase 2 Features (Not in Initial Implementation)

1. **Parallel Downloads**: Multi-threaded download with connection pooling
2. **Smart Retry**: Exponential backoff with jitter for S3 rate limits
3. **Checksum Validation**: Verify downloaded files against API checksums
4. **Incremental Downloads**: Resume partial file downloads (HTTP range requests)
5. **Download Prioritization**: User-defined priority queues
6. **Bandwidth Throttling**: Rate limit downloads to preserve network capacity
7. **Storage Management**: Auto-cleanup of old attachments, compression

### Integration Opportunities

1. **External Storage**: Upload to S3, GCS, Azure Blob after download
2. **CDN Integration**: Populate CDN caches during download
3. **Asset Processing**: Image optimization, thumbnail generation
4. **Virus Scanning**: Integrate with AV scanners during download
5. **Deduplication**: Detect and skip duplicate files by hash

## Open Questions

1. **Default Behavior**: Should `extract` default to queuing or downloading attachments?
   - **Recommendation**: Queue by default (safer, more flexible)

2. **Download Directory Structure**: How should attachments be organized on disk?
   - **Recommendation**: `attachments/{entity_type}/{entity_id}/{attachment_id}-{filename}`

3. **Concurrent Downloads**: Should we support parallel downloads in initial version?
   - **Recommendation**: No, add in Phase 2 (keep initial implementation simple)

4. **Download Report Format**: What metrics are most valuable?
   - **Recommendation**: Total downloaded, file sizes, failures, top errors

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Users confused by new workflow | Medium | Low | Clear docs, backward compatibility |
| Breaking change for existing scripts | High | Low | Preserve legacy flag, announce change |
| Download failures hard to debug | Medium | Medium | Comprehensive error logging, report generation |
| Disk space exhaustion during download | High | Medium | Pre-flight check, progress monitoring |
| Network interruptions lose progress | Medium | High | Resume support, status tracking |

## Success Criteria

This feature is considered successful when:

1. ✅ Users can extract 100,000+ entities without downloading attachments
2. ✅ Download pass can be paused and resumed without data loss
3. ✅ 95% of test scenarios pass on first implementation
4. ✅ Documentation covers all common use cases
5. ✅ Zero regression in existing extract behavior
6. ✅ Performance improvement: extract pass 50%+ faster without downloads
7. ✅ User feedback: "This makes large migrations much easier"

## Timeline Estimate

| Phase | Duration | Deliverables |
|-------|----------|-------------|
| Implementation | 4-6 hours | Core download coordinator, CLI command, filters |
| Testing | 2-3 hours | Unit tests, integration tests, manual testing |
| Documentation | 1-2 hours | Update guides, add examples, API reference |
| Code Review | 1 hour | PR review, address feedback |
| **Total** | **8-12 hours** | Feature complete, tested, documented |

## Appendix

### Related Documents

- `PRPs/multi-pass-jobber-extraction.md` - Original multi-pass system PRD
- `MULTI_PASS_MIGRATION.md` - Multi-pass user guide
- `DATABASE_SCHEMA.md` - Database schema documentation

### Key Stakeholders

- **Users**: Simplified workflow, better control
- **Operations**: More resilient migrations, better monitoring
- **Development**: Cleaner separation of concerns, easier testing

---

**Document Status**: Draft
**Created**: 2025-11-21
**Author**: Claude Code
**Version**: 1.0
