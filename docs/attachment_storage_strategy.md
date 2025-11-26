# Attachment Storage Strategy

## Overview

Phase 6 of the Jobber Max Extract Refactor implements a two-phase ETL pattern for binary attachment downloads:

- **Phase 1 (Metadata)**: Extract attachment metadata during entity extraction
- **Phase 2 (Binaries)**: Download files using hash-based content-addressed storage

This document describes the storage strategy, file naming conventions, and database schema for binary attachments.

---

## Storage Architecture

### Content-Addressed Storage

Attachments use **hash-based file naming** to ensure:
- **Deduplication**: Identical files share the same hash, stored once
- **Integrity verification**: SHA256 hash validates file content
- **Immutability**: Hash-based names prevent accidental overwrites
- **Flat directory structure**: Simple, scalable file organization

### Directory Structure

```
attachments/
├── 5d41402abc4b2a76b9719d911017c592ae3c1e3c.pdf
├── 7b52009b64fd0a2a49e6d8a939753077792b0554.jpg
├── e3b0c44298fc1c149afbf4c8996fb924.png
└── manifest.json (optional)
```

**Key features:**
- Single flat directory (`./attachments/`)
- No subdirectories or note-based organization
- Filename format: `{sha256_hash}.{original_extension}`
- All files stored at root level for simplicity

---

## File Naming Convention

### Format

```
{sha256_hash}.{original_extension}
```

### Examples

| Original Filename | SHA256 Hash | Stored As |
|------------------|-------------|-----------|
| invoice_2024.pdf | 5d41402abc4b2a76b9719d911017c592ae3c1e3c | `5d41402abc4b2a76b9719d911017c592ae3c1e3c.pdf` |
| photo.jpg | 7b52009b64fd0a2a49e6d8a939753077792b0554 | `7b52009b64fd0a2a49e6d8a939753077792b0554.jpg` |
| unknown | e3b0c44298fc1c149afbf4c8996fb924 | `e3b0c44298fc1c149afbf4c8996fb924.bin` |

### Extension Handling

- Preserve original file extension from `file_name` field
- If no extension found, default to `.bin`
- Extension extracted using `Path(file_name).suffix`

---

## Hash Algorithm

### SHA256 Computation

```python
import hashlib

def compute_file_hash(content: bytes) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(content).hexdigest()
```

### Streaming Hash Computation

The AttachmentDownloader computes hash during streaming download:

```python
hash_obj = hashlib.sha256()
chunks = []

for chunk in response.iter_content(chunk_size=8192):
    if chunk:
        chunks.append(chunk)
        hash_obj.update(chunk)  # Incremental hash update

file_hash = hash_obj.hexdigest()  # Get final hash
```

**Benefits:**
- Memory efficient for large files
- Single-pass download and hash computation
- No need to re-read file after download

---

## Database Schema

### Attachments Table

```sql
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,                    -- Jobber attachment ID
    note_id TEXT NOT NULL REFERENCES notes(id),
    file_name TEXT,                         -- Original filename
    content_type TEXT,                      -- MIME type
    original_url TEXT,                      -- Remote download URL
    local_file_path TEXT,                   -- Local path: ./attachments/{hash}.{ext}
    file_size INTEGER,                      -- Size in bytes
    created_at TEXT,                        -- Jobber creation timestamp

    -- Download tracking fields (Phase 2)
    download_status TEXT DEFAULT 'pending', -- pending, completed, failed
    hash TEXT,                              -- SHA256 hash
    downloaded_at TEXT,                     -- ISO timestamp when downloaded
    download_error TEXT                     -- Error message if failed
)
```

### Download Status States

| Status | Description |
|--------|-------------|
| `pending` | Metadata extracted, file not yet downloaded |
| `completed` | File successfully downloaded and verified |
| `failed` | Download failed (see `download_error` field) |

### Field Population Timeline

**Phase 1 (Metadata Extraction):**
- `id`, `note_id`, `file_name`, `content_type`, `original_url`, `file_size`, `created_at`
- `download_status` = `'pending'`
- `local_file_path` = pre-computed path (can be updated in Phase 2)

**Phase 2 (Binary Download):**
- `local_file_path` = actual path to downloaded file
- `hash` = computed SHA256 hash
- `download_status` = `'completed'` or `'failed'`
- `downloaded_at` = ISO timestamp
- `download_error` = error message (if failed)

---

## Download Workflow

### 1. Metadata Extraction (Phase 1)

```python
# During entity extraction (Client, Job, Invoice, etc.)
attachment = Attachment(
    id="att_123",
    note_id="note_456",
    file_name="invoice.pdf",
    content_type="application/pdf",
    original_url="https://jobber.s3.amazonaws.com/...",
    local_file_path="./attachments/pending",  # Placeholder
    file_size=102400,
    created_at="2024-11-25T10:30:00Z",
    download_status="pending",  # Not yet downloaded
)
repository.save_attachments([attachment])
```

### 2. Binary Download (Phase 2)

```python
# Batch download all pending attachments
downloader = AttachmentDownloader(repository, logger)
stats = downloader.download_all_pending(batch_size=100)

# Or download single attachment
result = downloader.download_attachment(attachment)
```

### 3. Database Update After Download

```python
# AttachmentDownloader automatically updates database:
repository.update_attachment_download(
    attachment_id="att_123",
    local_file_path="./attachments/5d41402abc4b2a76b9719d911017c592ae3c1e3c.pdf",
    hash="5d41402abc4b2a76b9719d911017c592ae3c1e3c",
    download_status="completed",
    downloaded_at="2024-11-25T10:35:42Z"
)
```

---

## Repository Methods

### Query Pending Attachments

```python
# Get all pending attachments
pending = repository.get_pending_attachments()

# Get pending attachments for specific entity types
pending_invoices = repository.get_pending_attachments(
    entity_types=["invoice", "quote"]
)
```

### Update Download Status

```python
# Partial update (only provided fields are updated)
repository.update_attachment_download(
    attachment_id="att_123",
    download_status="completed",
    hash="5d41402abc4b2a76b9719d911017c592ae3c1e3c"
)

# Full update after successful download
repository.update_attachment_download(
    attachment_id="att_123",
    local_file_path="./attachments/5d41402abc4b2a76b9719d911017c592ae3c1e3c.pdf",
    hash="5d41402abc4b2a76b9719d911017c592ae3c1e3c",
    download_status="completed",
    downloaded_at="2024-11-25T10:35:42Z"
)

# Record download failure
repository.update_attachment_download(
    attachment_id="att_123",
    download_status="failed",
    download_error="Connection timeout after 3 retries"
)
```

---

## CLI Usage

### Download All Pending Attachments

```bash
# Download with default settings
tightbeam migrate download-attachments

# Specify output directory
tightbeam migrate download-attachments --output-dir ./my-attachments

# Control batch size
tightbeam migrate download-attachments --batch-size 50

# Database location
tightbeam migrate download-attachments --db ./data/jobber_export.db
```

### Expected Output

```
📥 Starting attachment download (batch size: 100)
✓ Downloaded invoice.pdf → 5d41402abc4b2a76b9719d911017c592ae3c1e3c.pdf (102400 bytes)
✓ Downloaded photo.jpg → 7b52009b64fd0a2a49e6d8a939753077792b0554.jpg (256000 bytes)
✗ Failed: document.pdf (Connection timeout)

📊 Download Summary:
   Success: 245 files (125.3 MB)
   Failed: 3 files
   Total time: 4m 32s
```

---

## Manifest File (Optional)

A `manifest.json` file can optionally be generated to map hashes to original metadata:

```json
{
  "version": "1.0",
  "generated_at": "2024-11-25T10:35:42Z",
  "files": [
    {
      "hash": "5d41402abc4b2a76b9719d911017c592ae3c1e3c",
      "filename": "5d41402abc4b2a76b9719d911017c592ae3c1e3c.pdf",
      "original_name": "invoice_2024.pdf",
      "content_type": "application/pdf",
      "size_bytes": 102400,
      "note_id": "note_456",
      "attachment_id": "att_123",
      "downloaded_at": "2024-11-25T10:35:42Z"
    }
  ]
}
```

**Note:** Manifest generation is optional. All metadata is already stored in the SQLite database.

---

## Security Considerations

### SSRF Protection

The AttachmentDownloader implements domain allowlisting to prevent SSRF attacks:

```python
_allowed_domains = {
    "getjobber.com",
    "cdn.getjobber.com",
    "assets.getjobber.com",
    "jobber.s3.amazonaws.com",
    "jobber-attachments.s3.amazonaws.com",
    # ... other verified Jobber domains
}
```

**Validation rules:**
- Only HTTPS URLs allowed (no HTTP, FTP, file://, etc.)
- Domain must match allowlist (exact or subdomain match)
- Rejects malformed URLs and internal network addresses

### File System Safety

- Hash-based naming prevents directory traversal attacks
- No user-controlled path components in file storage
- Flat directory structure limits filesystem complexity
- Extension validation (default to `.bin` if suspicious)

---

## Performance Characteristics

### Storage Efficiency

- **Deduplication**: Identical files stored once (automatic via hash-based naming)
- **Flat structure**: No directory traversal overhead
- **Scalable**: Modern filesystems handle millions of files in single directory

### Download Performance

- **Streaming**: Memory-efficient for large files (8KB chunks)
- **Batch processing**: Query pending attachments in batches (default: 100)
- **Retry logic**: Exponential backoff with 3 retries via requests.Session
- **Parallel potential**: Can be extended for concurrent downloads

### Database Efficiency

- **Indexed queries**: `download_status` column enables fast pending queries
- **Partial updates**: COALESCE-based updates only modify changed fields
- **Batch inserts**: Metadata saved in bulk during Phase 1

---

## Migration from Old Structure

If migrating from previous note-based directory structure:

### Old Structure
```
attachments/
└── note_123/
    ├── invoice.pdf
    └── photo.jpg
```

### New Structure
```
attachments/
├── 5d41402abc4b2a76b9719d911017c592ae3c1e3c.pdf
└── 7b52009b64fd0a2a49e6d8a939753077792b0554.jpg
```

**Migration steps:**
1. Re-download all attachments using Phase 2 process
2. Hash computation will create new filenames
3. Database tracks both old and new paths during transition
4. Old files can be safely deleted after verification

---

## References

- **Implementation**: `src/extractors/attachment_downloader.py`
- **Repository**: `src/repositories/repository.py` (lines 2121-2163)
- **Model**: `src/models/attachment.py`
- **PRP**: `PRPs/jobber-max-extract-refactor.md` (Phase 6)
