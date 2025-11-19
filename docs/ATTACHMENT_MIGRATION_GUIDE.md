# Attachment Extraction Migration Guide

## Overview

This guide explains the changes to attachment handling in TightBeam v2 and provides migration instructions for users upgrading from previous versions.

## What Changed

### Before: Standalone Attachment Extractor

Previously, attachments were extracted using a separate `AttachmentsExtractor` that made dedicated GraphQL queries for attachment data:

- Separate API queries for each entity type's attachments
- Higher API costs (each attachment query counted separately)
- More complex extraction workflow
- No automatic file downloads

### After: Inline Attachment Extraction

Attachments are now fetched **inline** with their parent entities (Clients, Invoices, Quotes, Jobs, Requests):

- Attachments are included in the parent entity's GraphQL query
- **60-70% reduction in API costs** by eliminating separate queries
- Simplified extraction workflow
- **Automatic file downloads** with configurable options
- Integrated into existing extractors via `BaseExtractor`

## Key Benefits

1. **Cost Reduction**: Fetching attachments inline reduces API query costs by 60-70%
2. **Simplified Architecture**: One less extractor to manage
3. **Automatic Downloads**: Files are downloaded automatically during extraction (configurable)
4. **Better Organization**: Files organized by note_id: `./attachments/{note_id}/{filename}`
5. **Security Enhancements**: SSRF protection, HTTPS-only, domain allowlisting

## Configuration

### Attachment Download Settings

Control automatic file downloads in `config/settings.yaml`:

```yaml
attachments:
  # Automatically download attachment files during extraction
  # When enabled: Downloads happen synchronously, blocking pagination
  # When disabled: Only metadata is saved, files must be downloaded manually later
  # Default: true (automatic downloads)
  auto_download: true
```

### Performance Considerations

**Automatic Downloads (auto_download: true)**
- ✅ Convenient: Complete one-pass migration with all files
- ✅ Simple: No manual download step required
- ⚠️  Slower: Downloads block pagination (e.g., 42 clients × 5 attachments = 210 files)

**Metadata-Only Mode (auto_download: false)**
- ✅ Faster: Extraction completes quickly without file downloads
- ✅ Flexible: Download files later in a separate batch process
- ⚠️  Requires manual step: Files must be downloaded separately

**Recommendation**: For large datasets (>100 attachments), consider setting `auto_download: false` for faster initial extraction, then implement a separate download process.

### Pagination Settings

Control how many attachments are fetched inline with parent entities:

```yaml
pagination:
  # Number of notes/attachments fetched inline with parent entities
  # Default: 10 (balances cost reduction with typical note counts)
  nested_notes: 10
```

**Tuning Guide**:
- Reduce to `5` if most entities have few attachments (reduces query cost)
- Increase to `20` if entities have many attachments and you want full batches
- Keep at `10` for optimal cost/performance balance

If an entity has more attachments than `nested_notes`, a warning is logged:
```
WARNING: Client abc123 has additional attachments beyond the 10 fetched.
Increase pagination.nested_notes in settings.yaml to fetch more attachments inline.
```

## Migration Path

### For New Users

No migration needed! The new inline extraction is the default behavior.

### For Existing Users (Upgrading from Previous Versions)

#### Step 1: Update Configuration

The standalone `AttachmentsExtractor` has been **removed**. Remove any references from your code:

**Before:**
```python
from src.extractors import AttachmentsExtractor

attachments_extractor = AttachmentsExtractor(...)
coordinator = BaseMigrationCoordinator(
    ...,
    attachments_extractor=attachments_extractor,
)
```

**After:**
```python
# AttachmentsExtractor removed - attachments now extracted inline
coordinator = BaseMigrationCoordinator(
    ...,
    # No attachments_extractor parameter needed
)
```

#### Step 2: Configure Download Behavior

Add the new `attachments` section to your `config/settings.yaml`:

```yaml
attachments:
  auto_download: true  # or false for metadata-only mode
```

#### Step 3: Update Database Schema (If Needed)

The attachment database schema remains **unchanged**. No migration required.

#### Step 4: Test Extraction

Run a test extraction on a small subset of data:

```bash
# Test with automatic downloads
python -m src.cli.migrate --entities clients --db test.db

# Or test metadata-only mode for faster extraction
# (Edit config/settings.yaml: auto_download: false)
python -m src.cli.migrate --entities clients --db test.db
```

Verify:
- Attachment metadata is saved to database
- Files are downloaded to `./attachments/` (if auto_download: true)
- No errors or warnings in logs

## API Changes

### GraphQL Query Structure

**Before:**
```graphql
# Separate query for attachments
query {
  noteAttachments(first: 50) {
    edges {
      node {
        id
        fileName
        url
        ...
      }
    }
  }
}
```

**After:**
```graphql
# Inline with parent entity
query {
  clients(first: 42) {
    edges {
      node {
        id
        firstName
        lastName
        noteAttachments(first: 10) {  # Nested query
          edges {
            node {
              id
              fileName
              url
              ...
            }
          }
        }
      }
    }
  }
}
```

### Code API Changes

**Extractor Interface**: No changes to public extractor interface. All changes are internal.

**Coordinator Interface**: Removed `attachments_extractor` parameter from `BaseMigrationCoordinator.__init__`.

**Repository Interface**: No changes to repository methods. `save_attachments()` works the same.

## Security Enhancements

### URL Validation

All attachment downloads are validated to prevent SSRF attacks:

- **HTTPS-only**: Only `https://` URLs are allowed
- **Domain allowlist**: Only Jobber domains and CDNs are permitted
- **No redirects**: Redirect following is disabled for security

### Domain Allowlist

Configure allowed domains in `src/extractors/attachment_downloader.py`:

```python
self._allowed_domains = {
    "getjobber.com",
    "cdn.getjobber.com",
    "assets.getjobber.com",
    "jobber-attachments.s3.amazonaws.com",  # Specific S3 bucket
    "jobber-assets.s3.amazonaws.com",
    "d123456abcdef.cloudfront.net",  # Specific CloudFront distribution
}
```

**Note**: Update these with actual Jobber S3 bucket names and CloudFront distribution IDs based on real attachment URLs from your Jobber account.

## Troubleshooting

### Issue: Attachments Not Downloaded

**Symptoms**: Attachment metadata saved but no files in `./attachments/`

**Causes**:
1. `auto_download: false` in config
2. Download failures due to network issues
3. URL validation failures

**Solutions**:
1. Check `config/settings.yaml` - set `auto_download: true`
2. Check logs for download errors
3. Verify attachment URLs are from allowed domains

### Issue: Slow Extraction

**Symptoms**: Extraction takes much longer than expected

**Causes**:
1. Large number of attachments being downloaded synchronously
2. Network latency on file downloads

**Solutions**:
1. Set `auto_download: false` for faster metadata extraction
2. Reduce `pagination.nested_notes` to fetch fewer attachments inline
3. Download files in a separate batch process after extraction

### Issue: Missing Attachments

**Symptoms**: Some attachments not extracted

**Causes**:
1. Entity has more attachments than `pagination.nested_notes` limit
2. Attachment mapping errors

**Solutions**:
1. Increase `pagination.nested_notes` in `config/settings.yaml`
2. Check logs for mapping errors and warnings
3. Review `attachment_mapping_failures` in migration summary

### Issue: URL Validation Errors

**Symptoms**: Logs show "Domain not in allowed domains list"

**Causes**:
1. Jobber uses a CDN not in the default allowlist
2. S3 bucket name doesn't match expected pattern

**Solutions**:
1. Examine actual attachment URLs in logs
2. Update `_allowed_domains` in `attachment_downloader.py`
3. Add specific S3 bucket names and CloudFront distributions

## Metrics and Monitoring

The migration summary now includes attachment-specific metrics:

```
Attachment Download Summary:
  • 210 attachments processed
  • 205 files downloaded (1.2 MB)
  • 5 download failures
  • 2 attachment mapping failures
```

**Key Metrics**:
- `attachments_processed`: Total attachment records processed
- `files_downloaded`: Successfully downloaded files
- `download_failures`: Failed downloads (network errors, invalid URLs)
- `attachment_mapping_failures`: GraphQL → domain model mapping errors

## Best Practices

1. **Start Small**: Test inline extraction on a subset of data first
2. **Monitor Costs**: Track GraphQL query costs - should see 60-70% reduction
3. **Configure Wisely**: Use `auto_download: false` for large datasets
4. **Verify Security**: Update domain allowlist with actual Jobber CDN domains
5. **Review Logs**: Check for pagination warnings and mapping errors
6. **Plan Downloads**: For metadata-only mode, plan a separate download process

## Support

For issues or questions:
1. Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
2. Review logs for error messages
3. File an issue on GitHub with:
   - Configuration settings
   - Error logs
   - Migration summary output

## Related Documentation

- [Configuration Guide](CONFIGURATION.md) - Full config reference
- [Notes Optimization](architecture/notes-optimization.md) - Inline extraction architecture
- [Database Schema](DATABASE_SCHEMA.md) - Database structure
- [API Optimization](JOBBER_API_OPTIMIZATION.md) - Cost reduction analysis
