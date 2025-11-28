# Performance Baseline Report - Max Extract Pipeline

**Generated**: 2025-11-26 (Baseline Template)
**Purpose**: Establishes performance baselines for Max Extract pipeline

---

## Test Environment

| Parameter | Value |
|-----------|-------|
| Test Account Size | Medium (500-1000 clients, 2000-5000 jobs) |
| Optimization Level | Moderate |
| Network | Stable broadband (50 Mbps+) |
| Hardware | Standard development machine |
| Python Version | 3.10+ |

## Performance Targets

### Primary Metrics

| Metric | Target | Acceptable | Concern Threshold |
|--------|--------|------------|-------------------|
| Requests/Second | 4-6 req/s | 3-8 req/s | <2 or >8 req/s |
| Entities/Second | 50-200 | 20-300 | <10 or >400 |
| Memory Usage | <500 MB | <1000 MB | >1000 MB |
| GraphQL Cost Utilization | 60-80% | 40-90% | <20% or >95% |
| Error Rate | 0% | <1% | >5% |

### Secondary Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| Database Write Throughput | 100+ entities/sec | SQLite INSERT OR REPLACE performance |
| Resume Success Rate | 100% | Checkpoint-based recovery works |
| Cost Efficiency | 70-90% | Actual vs Requested cost ratio |
| Peak Memory Delta | <200 MB | Memory growth during extraction |

## Expected Performance by Entity Type

Based on entity complexity and typical volumes:

| Entity Type | Expected Time (1000 entities) | Notes |
|-------------|-------------------------------|-------|
| users | 20-40s | Simple entity, small volumes |
| clients | 30-60s | Medium complexity, high volume |
| properties | 30-60s | Medium complexity |
| requests | 40-80s | Higher complexity |
| quotes | 60-120s | Complex nested data |
| jobs | 60-120s | Complex nested data |
| visits | 40-80s | Medium complexity |
| invoices | 50-100s | Complex with line items |
| expenses | 30-60s | Simple to medium |
| timesheet_entries | 30-60s | Simple to medium |
| product_services | 20-40s | Simple catalog items |
| tax_rates | 10-20s | Simple configuration |
| notes | 40-80s | Deferred loading, individual queries |

**Total Estimated Time for 10,000 entities**: 15-45 minutes (varies by entity mix)

## Optimization Level Performance Comparison

### Conservative (Slow but Stable)

```yaml
rate_limits:
  conservative:
    capacity: 250
    refill_rate: 240  # 4 req/s
    safety_margin: 0.52
```

**Expected Performance**:
- Requests/Second: 2-3 req/s
- Entities/Second: 30-80
- Runtime (10k entities): 30-60 minutes
- Use Case: Unstable networks, rate limit concerns

### Moderate (Balanced) - DEFAULT

```yaml
rate_limits:
  moderate:
    capacity: 600
    refill_rate: 600  # 10 req/s
    safety_margin: 0.1
```

**Expected Performance**:
- Requests/Second: 4-6 req/s
- Entities/Second: 50-200
- Runtime (10k entities): 15-30 minutes
- Use Case: Standard migrations, stable connections

### Aggressive (Fast)

```yaml
rate_limits:
  aggressive:
    capacity: 500
    refill_rate: 480  # 8 req/s
    safety_margin: 0.04
```

**Expected Performance**:
- Requests/Second: 6-8 req/s
- Entities/Second: 100-300
- Runtime (10k entities): 10-20 minutes
- Use Case: Very stable connections, time-critical

## GraphQL Cost Baseline

### Per-Entity Estimated Costs

| Entity | Fields | Est. Cost (per page of 50) | Notes |
|--------|--------|-----------------------------|-------|
| clients | 15-20 | 750-1000 | With nested notes limit |
| jobs | 20-25 | 1000-1250 | Complex nested structure |
| invoices | 25-30 | 1250-1500 | Line items included |
| notes | 10-15 | 10-15 (individual) | Fetched individually |
| Simple entities | 10-15 | 500-750 | Users, tax_rates, etc. |

### Cost Budget Management

**Available Points**: 10,000 (maximum)
**Restore Rate**: 500 points/sec
**Safe Threshold**: 2,000 points remaining

**Recommended Page Sizes**:
- Simple entities (users, tax_rates): 50-100
- Medium entities (clients, properties): 30-50
- Complex entities (jobs, invoices): 20-30
- Notes: Individual fetches (1 per request)

## Memory Usage Baseline

### Expected Memory Profile

| Phase | Expected Memory | Peak | Notes |
|-------|----------------|------|-------|
| Initialization | 50-100 MB | - | Dependencies loaded |
| Lightweight Extraction | 100-200 MB | 250 MB | Users, tax_rates |
| Heavy Extraction | 200-400 MB | 500 MB | Jobs, invoices with nesting |
| Batch Processing | +50-100 MB | - | Per 1000 entities |
| Attachment Downloads | 100-300 MB | 400 MB | Streaming downloads |

**Leak Detection**: Memory should stabilize after warmup, not grow continuously

## Database Performance Baseline

### Write Throughput

| Operation | Target Throughput | Notes |
|-----------|-------------------|-------|
| Batch INSERT | 500-1000 rows/sec | executemany() with 50-100 rows |
| UPDATE status | 100-500 updates/sec | Individual checkpoint updates |
| SELECT lookups | 1000+ reads/sec | Indexed queries |

### Database Size Estimates

| Entity Count | Database Size | Notes |
|--------------|---------------|-------|
| 1,000 entities | 5-10 MB | All entity types |
| 10,000 entities | 50-100 MB | Typical small business |
| 50,000 entities | 250-500 MB | Medium business |
| 100,000+ entities | 500 MB - 2 GB | Large business |

**Attachment Storage**: Separate from database (filesystem)
**Estimated Attachment Size**: 2-5× database size (varies widely)

## Error Rate Baseline

### Expected Error Rates

| Error Type | Target Rate | Acceptable | Action Threshold |
|-----------|-------------|------------|------------------|
| Network Errors | 0% | <0.1% | >1% |
| Rate Limit Errors | 0% | <0.01% | >0.1% |
| GraphQL Errors | 0% | <0.1% | >0.5% |
| Validation Errors | 0% | 0% | >0% |
| Database Errors | 0% | 0% | >0% |

**Total Error Budget**: <1% of all requests

### Recovery Metrics

| Recovery Type | Success Rate | Time to Recovery |
|---------------|-------------|------------------|
| Network Retry | 99%+ | <10s (exponential backoff) |
| Resume from Checkpoint | 100% | Immediate |
| URL Refresh (Pass 1 re-run) | 100% | Minutes |

## Testing Methodology

### Test Scenarios

1. **Baseline Test**: Full extraction with moderate settings
2. **Stress Test**: Aggressive settings to find limits
3. **Stability Test**: Long-running extraction (>1 hour)
4. **Resume Test**: Interrupt and resume extraction
5. **Error Recovery Test**: Simulate network failures

### Test Execution

```bash
# Baseline test
python scripts/performance_test.py \
  --db test_baseline.db \
  --report baseline_report.md \
  --optimization-level moderate

# Stress test
python scripts/performance_test.py \
  --db test_stress.db \
  --report stress_report.md \
  --optimization-level aggressive

# Custom configuration test
# 1. Edit config/settings.yaml
# 2. Run test
uv run tightbeam migrate max-extract --db test_custom.db
```

### Metrics Collection

**Automated**:
- GraphQL costs (stored in `graphql_costs` table)
- Migration state (stored in `migration_state` table)
- Entity counts (per entity type)

**Manual**:
- Memory usage (via `tracemalloc` or system monitor)
- Runtime (start/end timestamps)
- Error logs (from application logs)

## Performance Tuning Guide

### Improving Throughput

1. **Increase Page Sizes**: Start with default, incrementally increase
2. **Reduce Safety Margins**: Lower `safety_margin` in rate_limits config
3. **Increase Refill Rate**: Higher `refill_rate` for more tokens/sec
4. **Parallel Extraction**: Future enhancement (not yet implemented)

### Reducing Memory Usage

1. **Smaller Batch Sizes**: Process fewer entities per batch
2. **Disable Verbose Logging**: Reduce log buffer memory
3. **Periodic GC**: Force garbage collection between large batches
4. **Streaming Processing**: Already implemented for attachments

### Optimizing GraphQL Costs

1. **Right-Size Pages**: Match page size to cost budget
2. **Limit Nested Queries**: Use deferred loading for expensive nesting
3. **Monitor Cost Trends**: Review `graphql_costs` table regularly
4. **Adaptive Sizing**: Reduce page size when costs spike (manual for now)

## Known Performance Bottlenecks

### 1. Individual Note Fetching

**Issue**: Notes fetched individually due to GraphQL nested query costs
**Impact**: ~10-20× slower than batch extraction
**Mitigation**: Deferred loading strategy, batch database writes
**Future**: Explore top-level notes query if Jobber API supports it

### 2. Large Attachment Downloads

**Issue**: Large files (>100 MB) increase memory and timeout risk
**Impact**: Higher failure rate, longer runtimes
**Mitigation**: Streaming downloads, generous timeouts (300s read timeout)
**Future**: Resume support for partial downloads

### 3. Database Locks

**Issue**: SQLite write locks during high-volume inserts
**Impact**: Occasional timeouts on concurrent access
**Mitigation**: WAL mode enabled, single-process design
**Future**: Consider PostgreSQL for very large migrations

## Recommendations

### Pre-Migration

- ✓ Test with small entity subsets first
- ✓ Verify network stability (ping test, speed test)
- ✓ Ensure sufficient disk space (estimate 2-5 GB)
- ✓ Run during off-peak hours for Jobber API
- ✓ Start with conservative settings, tune up gradually

### During Migration

- ✓ Monitor `graphql_costs` table for throttling
- ✓ Watch memory usage (should stabilize)
- ✓ Check error logs periodically
- ✓ Verify checkpoint progress in `migration_state`
- ✓ Use `--resume` if interrupted

### Post-Migration

- ✓ Run validation script (`scripts/validate_extraction.py`)
- ✓ Review performance report
- ✓ Document actual performance for future reference
- ✓ Tune configuration based on results
- ✓ Report issues or anomalies

## Appendix: Performance Checklist

### Before Running Tests

- [ ] Valid Jobber OAuth credentials configured
- [ ] Test database path specified
- [ ] Sufficient disk space available (2-5 GB)
- [ ] Network connection stable
- [ ] Python dependencies installed (`uv sync`)
- [ ] Configuration reviewed (`config/settings.yaml`)

### During Tests

- [ ] Monitor system resources (CPU, memory, disk I/O)
- [ ] Check for errors in logs
- [ ] Verify checkpoints being saved
- [ ] Watch GraphQL cost utilization
- [ ] Note any anomalies or warnings

### After Tests

- [ ] Review performance report
- [ ] Compare against baselines
- [ ] Validate data integrity
- [ ] Document actual performance
- [ ] Archive test results
- [ ] Update tuning parameters if needed

---

**Last Updated**: 2025-11-26
**Version**: 1.0
**Status**: Baseline Template
**Next Review**: After first production migration
