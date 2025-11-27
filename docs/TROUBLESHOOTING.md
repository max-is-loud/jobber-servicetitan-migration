# Troubleshooting Guide

Quick reference for diagnosing and fixing common issues when running TightBeam migrations for clients.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [OAuth & Authentication Issues](#oauth--authentication-issues)
- [Rate Limiting & API Throttling](#rate-limiting--api-throttling)
- [Database Issues](#database-issues)
- [Network & Connectivity](#network--connectivity)
- [Data Mapping Errors](#data-mapping-errors)
- [Migration Workflow Issues](#migration-workflow-issues)
- [Debug Logging](#debug-logging)
- [Emergency Recovery](#emergency-recovery)

## Quick Diagnostics

### Health Check Commands

Run these first when encountering issues:

```bash
# Check environment setup
uv run python -c "from src.constants import APP_VERSION; print(f'TightBeam v{APP_VERSION}')"

# Verify OAuth credentials are set
uv run python -c "import os; print('✓ Credentials set' if all([os.getenv('JOBBER_CLIENT_ID'), os.getenv('JOBBER_CLIENT_SECRET'), os.getenv('JOBBER_REDIRECT_URI')]) else '✗ Missing credentials')"

# Check database accessibility
sqlite3 tightbeam.db ".tables"

# Test basic imports
uv run python -c "from src import JobberClient, Repository, EntityMapper; print('✓ Imports OK')"
```

### Common Error Patterns

| Error Type | Quick Fix |
|------------|-----------|
| `ModuleNotFoundError` | Run `uv sync` to install dependencies |
| `PackageNotFoundError` | Run `uv pip install -e .` for editable install |
| `ConfigurationError` | Check `.env` file and environment variables |
| `OAuth2Error` | Re-run `uv run tightbeam oauth init` |
| `RepositoryError` | Check database file permissions and disk space |
| `RateLimitError` | Reduce optimization level or wait for quota reset |

## OAuth & Authentication Issues

### Issue: "OAuth2 configuration error"

**Error Message:**
```
❌ Configuration error in oauth
OAuth2 configuration error: ... Please ensure JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, and JOBBER_REDIRECT_URI are set and run 'tightbeam oauth init' to authorize.
```

**Cause:** Missing or invalid OAuth credentials in environment.

**Fix:**
1. Check `.env` file exists and contains:
   ```bash
   JOBBER_CLIENT_ID=your_client_id
   JOBBER_CLIENT_SECRET=your_client_secret
   JOBBER_REDIRECT_URI=http://localhost:8080/callback
   ```

2. Verify credentials are loaded:
   ```bash
   uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('JOBBER_CLIENT_ID'))"
   ```

3. If missing, create `.env` from template or set manually:
   ```bash
   echo "JOBBER_CLIENT_ID=your_id_here" > .env
   echo "JOBBER_CLIENT_SECRET=your_secret_here" >> .env
   echo "JOBBER_REDIRECT_URI=http://localhost:8080/callback" >> .env
   ```

### Issue: "Access token expired" or "Invalid refresh token"

**Error Message:**
```
❌ OAuth2 authentication error
Access token has expired and refresh failed
```

**Cause:** OAuth tokens expired and refresh token is invalid.

**Fix:**
1. Clear existing tokens:
   ```bash
   rm tightbeam.db  # Or delete oauth_tokens table only
   ```

2. Re-initialize OAuth flow:
   ```bash
   uv run tightbeam oauth init
   ```

3. Follow browser prompts to re-authorize

**Prevention:** Tokens expire after extended periods of inactivity. For long-running client projects, set up regular token refresh or re-authorize before major migration runs.

### Issue: OAuth callback hangs or times out

**Error Message:**
Browser shows "Connection timed out" or terminal shows "Timeout waiting for OAuth callback"

**Cause:** Port 8080 is blocked or already in use, or client's firewall blocks localhost connections.

**Fix:**
1. Check if port 8080 is available:
   ```bash
   lsof -i :8080
   # If occupied, kill the process or change port
   ```

2. Try alternate port by modifying redirect URI (requires re-registering OAuth app):
   ```bash
   # In .env
   JOBBER_REDIRECT_URI=http://localhost:8081/callback
   ```

3. Check firewall rules:
   ```bash
   # For WSL/Linux
   sudo ufw status

   # Allow port if blocked
   sudo ufw allow 8080
   ```

4. If on remote server, use SSH tunnel:
   ```bash
   # On local machine
   ssh -L 8080:localhost:8080 user@remote-server
   ```

## Rate Limiting & API Throttling

### Issue: Excessive throttling during migration

**Symptoms:**
- Migration slows to a crawl
- Logs show many "throttled" requests
- Token bucket repeatedly exhausted

**Diagnosis:**
Check throttle metrics in logs:
```
🔍 Final Token Status:
   • Throttling rate: 45.2% (1,234 throttled)
   🔴 Significant throttling - consider further rate limit tuning
```

**Fix:**

1. **Reduce optimization level** (quickest fix):
   ```bash
   # Instead of aggressive
   uv run tightbeam migrate max-extract --optimization-level conservative
   ```

2. **Adjust rate limit config** in `config/settings.yaml`:
   ```yaml
   rate_limits:
     conservative:
       capacity: 250        # Reduce from 250 to 200
       refill_rate: 240     # Reduce from 240 to 180
       safety_margin: 0.52  # Increase to 0.60
   ```

3. **Check Jobber API status**:
   - Jobber may have reduced rate limits temporarily
   - Check [Jobber status page](https://status.getjobber.com/)

4. **Spread out migration** over multiple sessions:
   ```bash
   # Migrate in batches with pauses
   uv run tightbeam migrate max-extract
   # Wait 5-10 minutes
   uv run tightbeam migrate max-extract --resume
   ```

### Issue: Rate limit errors despite conservative settings

**Error Message:**
```
❌ Jobber API error
Rate limit exceeded: 429 Too Many Requests
```

**Cause:** Multiple TightBeam instances running, or client has other integrations consuming API quota.

**Fix:**
1. Check for other running instances:
   ```bash
   ps aux | grep tightbeam
   # Kill any duplicate processes
   ```

2. Coordinate with client about other API consumers:
   - Zapier integrations
   - Other data sync tools
   - Mobile apps with aggressive sync

3. Request rate limit increase from Jobber (for enterprise clients)

## Database Issues

### Issue: "Database is locked"

**Error Message:**
```
❌ Database error in migrate
database is locked
```

**Cause:** Another process has an open connection to the SQLite database.

**Fix:**
1. Find and close competing connections:
   ```bash
   # Check for open file handles
   lsof | grep tightbeam.db

   # Kill processes if needed
   kill -9 <PID>
   ```

2. If stuck, wait 30 seconds and retry (SQLite has auto-unlock)

3. For persistent issues, enable WAL mode for better concurrency:
   ```bash
   sqlite3 tightbeam.db "PRAGMA journal_mode=WAL;"
   ```

### Issue: "Disk I/O error" or "Disk full"

**Error Message:**
```
❌ Database error
disk I/O error
```

**Cause:** Insufficient disk space for database operations.

**Fix:**
1. Check available space:
   ```bash
   df -h .
   # Ensure at least 5-10GB free for large migrations
   ```

2. Clean up old databases:
   ```bash
   ls -lh *.db
   # Archive or delete old migration databases
   mv old_migration.db ~/archives/
   ```

3. Enable auto-vacuum:
   ```bash
   sqlite3 tightbeam.db "PRAGMA auto_vacuum = FULL;"
   sqlite3 tightbeam.db "VACUUM;"
   ```

### Issue: Database corruption

**Symptoms:**
- Random errors: "malformed database"
- Queries return unexpected results
- Cannot open database file

**Diagnosis:**
```bash
sqlite3 tightbeam.db "PRAGMA integrity_check;"
# Should return "ok"
```

**Fix:**
1. If corruption is minor, try repair:
   ```bash
   sqlite3 tightbeam.db ".recover" | sqlite3 recovered.db
   mv tightbeam.db corrupted_backup.db
   mv recovered.db tightbeam.db
   ```

2. If severe, restore from backup (if available) or restart migration:
   ```bash
   rm tightbeam.db
   uv run tightbeam migrate max-extract
   ```

**Prevention:** Always use `--resume` flag to enable migration state tracking.

## Network & Connectivity

### Issue: "Connection timeout" to Jobber API

**Error Message:**
```
❌ Jobber API error
HTTPSConnectionPool(host='api.getjobber.com', port=443): Read timed out
```

**Cause:** Network connectivity issues, slow connection, or Jobber API downtime.

**Fix:**
1. Test basic connectivity:
   ```bash
   ping api.getjobber.com
   curl -I https://api.getjobber.com/api/graphql
   ```

2. Check Jobber status:
   - https://status.getjobber.com/

3. Increase timeout (if on slow connection):
   ```python
   # In config/settings.yaml (future enhancement)
   # For now, connection timeout is hardcoded at 30s
   ```

4. Run migration from different network:
   - Switch from WiFi to ethernet
   - Try different ISP/VPN
   - Use cloud VM with better connectivity

### Issue: SSL certificate errors

**Error Message:**
```
❌ Jobber API error
SSL: CERTIFICATE_VERIFY_FAILED
```

**Cause:** System SSL certificates outdated or corporate proxy interfering.

**Fix:**
1. Update system certificates:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install ca-certificates
   sudo update-ca-certificates

   # macOS
   brew install openssl
   ```

2. If behind corporate proxy, set certificate bundle:
   ```bash
   export REQUESTS_CA_BUNDLE=/path/to/your/ca-bundle.crt
   ```

3. **TEMPORARY WORKAROUND** (not recommended for production):
   ```bash
   export PYTHONHTTPSVERIFY=0
   # Only use for debugging!
   ```

## Data Mapping Errors

### Issue: "Required field missing" in API response

**Error Message:**
```
❌ Data mapping error
Required field 'email' missing from client data
```

**Cause:** Jobber API schema changed or client data incomplete.

**Fix:**
1. Verify client data in Jobber UI:
   - Log into client's Jobber account
   - Check that entities have required fields populated

2. Update mapper to handle missing fields:
   ```python
   # Note: This would require code changes
   # For now, document which clients have incomplete data
   ```

3. Filter problematic entities:
   ```bash
   # Partial migration excluding problematic entity types
   # Use custom extraction commands
   uv run tightbeam extract quotes --db client_migration.db
   # Skip clients if they cause errors
   ```

### Issue: Date parsing errors

**Error Message:**
```
❌ Data mapping error
Invalid date format: '2024-13-01' is not a valid date
```

**Cause:** Unexpected date format from Jobber API or timezone issues.

**Fix:**
1. Check Jobber account timezone settings
2. Verify date format in raw GraphQL response:
   ```bash
   # Enable debug logging (see Debug Logging section)
   # Review raw API responses
   ```

3. Report to TightBeam maintainer for mapping fix

## Migration Workflow Issues

### Issue: Migration doesn't resume properly

**Symptoms:**
- `--resume` flag doesn't skip already-migrated entities
- Re-downloads same data
- Cursor not being saved

**Diagnosis:**
```bash
sqlite3 tightbeam.db "SELECT * FROM migration_state;"
# Check if migration_state table exists and has entries
```

**Fix:**
1. Verify migration state is being tracked:
   ```bash
   sqlite3 tightbeam.db "SELECT entity_type, last_cursor, entities_count FROM migration_state;"
   ```

2. If no entries, migration state wasn't initialized:
   ```bash
   # Restart migration with --resume from the beginning
   uv run tightbeam migrate max-extract --resume
   ```

3. If state exists but not working, check version compatibility:
   ```bash
   # Schema may have changed between versions
   # May need to drop and recreate migration_state table
   ```

### Issue: Partial migration with missing entities

**Symptoms:**
- Some entity types have 0 records
- Logs show "entities_processed: 0"
- No errors reported

**Cause:** Entity type was skipped or has no data in client's Jobber account.

**Fix:**
1. Check client's Jobber account:
   - Log in and verify entities exist
   - Some clients may not use certain features (e.g., Quotes)

2. Review migration summary:
   ```
   📊 Migration Analysis:
      • Clients: 1,234 ✓
      • Invoices: 5,678 ✓
      • Quotes: 0 ⚠️
      • Jobs: 2,345 ✓
   ```

3. If entities should exist but aren't migrating:
   - Check API permissions (client may have restricted access)
   - Review extraction logs for silent failures
   - Try manual extraction:
     ```bash
     uv run tightbeam extract quotes --db test.db --verbose
     ```

## Debug Logging

### Enable Verbose Logging

For detailed diagnostic output:

```bash
# Enable verbose mode for any command
uv run tightbeam migrate --verbose max-extract
```

### What Verbose Logging Shows

- GraphQL queries sent to Jobber API
- Raw API responses
- Rate limiting decisions (throttle/allow)
- Token bucket state changes
- Entity mapping details
- Database operations

### Save Logs to File

```bash
# Capture all output
uv run tightbeam migrate --verbose max-extract 2>&1 | tee migration.log

# Review later
less migration.log
grep -i "error" migration.log
```

### Analyze Specific Issues

```bash
# Rate limiting analysis
grep -i "throttle" migration.log

# OAuth token refresh events
grep -i "token" migration.log

# Database errors
grep -i "database\|sqlite" migration.log

# API response errors
grep -i "graphql\|api error" migration.log
```

## Emergency Recovery

### Scenario: Migration crashed mid-run

**What to do:**
1. Don't panic - database should have migration_state
2. Check what was completed:
   ```bash
   sqlite3 tightbeam.db "SELECT entity_type, entities_count, last_updated FROM migration_state ORDER BY last_updated;"
   ```

3. Resume from last checkpoint:
   ```bash
   uv run tightbeam migrate max-extract --resume
   ```

4. If resume fails, review error and fix underlying issue first

### Scenario: Client reports incomplete migration

**Investigation steps:**
1. Compare entity counts:
   ```bash
   # TightBeam database
   sqlite3 tightbeam.db "SELECT COUNT(*) FROM clients;"
   sqlite3 tightbeam.db "SELECT COUNT(*) FROM invoices;"

   # Compare with Jobber account (check in UI)
   ```

2. Check for date ranges:
   ```bash
   sqlite3 tightbeam.db "SELECT MIN(created_at), MAX(created_at) FROM invoices;"
   ```

3. Look for migration gaps:
   ```bash
   # Find entity IDs that should exist but don't
   # May need custom SQL queries based on client's requirements
   ```

### Scenario: Need to restart migration from scratch

**Clean slate process:**
1. Backup existing database (if needed):
   ```bash
   cp tightbeam.db backup_$(date +%Y%m%d_%H%M%S).db
   ```

2. Delete database:
   ```bash
   rm tightbeam.db
   ```

3. Clear OAuth tokens (if also re-authenticating):
   ```bash
   # OAuth tokens are in tightbeam.db, so already cleared
   # Verify .env still has correct credentials
   ```

4. Start fresh migration:
   ```bash
   uv run tightbeam oauth init  # If needed
   uv run tightbeam migrate max-extract
   ```

## Performance Optimization Tips

### For Large Client Migrations (10k+ entities)

1. **Use conservative rate limiting** to avoid throttling slowdowns
2. **Run during off-peak hours** (Jobber API is faster at night)
3. **Monitor progress** and use `--resume` if needed for large datasets
4. **Monitor disk space** - large databases grow to several GB
5. **Use SSD storage** for faster SQLite operations

### For Multiple Client Migrations

1. **Use separate databases** per client:
   ```bash
   uv run tightbeam migrate --db client_a_$(date +%Y%m%d).db max-extract
   uv run tightbeam migrate --db client_b_$(date +%Y%m%d).db max-extract
   ```

2. **Don't run concurrent migrations** - rate limits are shared

3. **Document client-specific quirks** in separate notes

## Getting Help

### Self-Service Diagnostics

Before seeking external help, collect:
1. Error message (full traceback if available)
2. Command that failed (with flags used)
3. Verbose log output
4. System info (`uv run python --version`, `uname -a`)
5. TightBeam version (`uv run python -c "from src.constants import APP_VERSION; print(APP_VERSION)"`)

### Known Limitations

- **No parallel migrations**: One migration at a time per Jobber account
- **SQLite locking**: Single writer at a time
- **Rate limits**: Shared across all API consumers for a Jobber account
- **Token expiration**: OAuth tokens expire after inactivity
- **Network dependency**: Cannot run offline

### Future Enhancements Planned

See `docs/architecture/notes-optimization.md` for performance improvements in progress:
- 60-70% reduction in API costs via optimized GraphQL queries
- Bulk note extraction instead of individual fetches
- Improved resume functionality with granular checkpoints

---

**Last Updated:** 2025-01-17
**For Internal Use Only** - TightBeam operator reference guide
