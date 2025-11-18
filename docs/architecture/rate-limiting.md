# Rate Limiting Architecture Analysis

## Executive Summary

**Current State:** Rate limiting setup is duplicated across CLI command handlers. Token bucket is already shared across all extractors via JobberClient dependency injection.

**Recommendation:** **Centralize rate limiting setup in ServiceFactory** - eliminates duplication while maintaining current architecture benefits. Do NOT move into BaseMigrationCoordinator.

**Impact:** Removes ~30 lines of duplicate code per command, improves maintainability, preserves separation of concerns.

---

## Current Architecture

### Setup Locations

Rate limiting is currently set up in **two main locations** with identical code:

1. **`src/cli/migrate.py:368-399`** - Full migration command
2. **`src/cli/services/entity_extraction.py:83-110`** - Individual entity extraction

Both follow this pattern:

```python
# 1. Get rate configuration from ConfigManager
rate_config = config_manager.get_rate_limit_config(optimization_level)
capacity = rate_config["capacity"]
refill_rate = rate_config["refill_rate"]
initial_tokens = rate_config["initial_tokens"]

# 2. Create token bucket rate limiter
rate_limiter = TokenBucketRateLimiter(
    capacity=capacity,
    refill_rate=refill_rate,
    initial_tokens=initial_tokens
)

# 3. Create exponential backoff strategy
backoff_config = config_manager.get_backoff_config()
backoff_strategy = ExponentialBackoffStrategy(
    initial_delay=backoff_config["initial_delay"],
    max_delay=backoff_config["max_delay"],
    multiplier=backoff_config["multiplier"],
    jitter_factor=backoff_config["jitter_factor"],
)

# 4. Create metrics collector (optional)
metrics_collector = MetricsCollector(repository=repository)

# 5. Wrap HttpClient with rate limiting
rate_limited_client = RateLimitedHttpClient(
    HttpClient(),
    rate_limiter,
    backoff_strategy,
    max_retries=15,
    metrics_collector=metrics_collector,
    auth_provider=auth_provider,
)

# 6. Inject into JobberClient
jobber_client.set_http_client(rate_limited_client)
```

### How Token Bucket is Shared

**Critical insight:** Token bucket is **already globally shared** across all extractors!

**Flow:**
1. CLI creates ONE `RateLimitedHttpClient` instance with ONE `TokenBucketRateLimiter`
2. This `RateLimitedHttpClient` is injected into `JobberClient` via `set_http_client()`
3. `JobberClient` instance is passed to `BaseMigrationCoordinator`
4. Coordinator passes same `JobberClient` to ALL extractors
5. All extractors share the **same token bucket** through shared `JobberClient`

**Reference:**
- `migrate.py:471-476`: Creates coordinator with pre-configured `JobberClient`
- `base_migration_coordinator.py:87`: Stores `JobberClient` as `self._jobber_client`
- All extractors receive this shared instance

### Current Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **CLI Commands** (`migrate.py`, `entity_extraction.py`) | Rate limiting setup, dependency wiring |
| **BaseMigrationCoordinator** | Orchestrates migration workflow, manages extractors |
| **JobberClient** | API communication, receives rate-limited HTTP client |
| **RateLimitedHttpClient** | Transparent rate limiting wrapper, retry logic |
| **TokenBucketRateLimiter** | Token bucket algorithm, request throttling |
| **Extractors** | Entity-specific extraction logic |

---

## Problem Statement

### Code Duplication

**30+ lines duplicated** across:
- `migrate.py:368-399` (32 lines)
- `entity_extraction.py:83-110` (28 lines)

**Issues:**
1. Changes to rate limiting setup must be synchronized across multiple files
2. Risk of inconsistency if one location is updated but not others
3. Violates DRY principle
4. Harder to maintain and test

### No Functional Issues

**Important:** The current architecture works correctly:
- ✅ Token bucket is properly shared across all extractors
- ✅ Rate limiting is transparent to business logic
- ✅ Separation of concerns is maintained
- ✅ Configuration is centralized via `ConfigManager`

The problem is purely **code organization and maintainability**.

---

## Proposed Solutions

### Solution 1: ServiceFactory Pattern (RECOMMENDED)

**Create centralized factory method in `ServiceFactory` class**

#### Implementation

Add to `src/cli/services/factories.py`:

```python
@staticmethod
def create_rate_limited_jobber_client(
    auth_provider: AuthProvider,
    repository: Repository,
    config_manager: ConfigManagerImpl,
    optimization_level: str = "moderate",
    enable_cost_monitoring: bool = True,
) -> JobberClient:
    """Create JobberClient with rate limiting and cost monitoring configured.

    Args:
        auth_provider: Authentication provider for API access
        repository: Repository for metrics storage
        config_manager: Configuration manager for rate limit settings
        optimization_level: Rate limiting optimization level
                          ('conservative', 'moderate', 'aggressive')
        enable_cost_monitoring: Whether to enable GraphQL cost tracking

    Returns:
        JobberClient: Fully configured client with rate limiting
    """
    # Create base JobberClient
    metrics_collector = MetricsCollector(repository=repository) if enable_cost_monitoring else None
    jobber_client = JobberClient(
        auth_provider,
        metrics_collector=metrics_collector,
        config_manager=config_manager,
    )

    # Setup rate limiting components
    rate_config = config_manager.get_rate_limit_config(optimization_level)
    rate_limiter = TokenBucketRateLimiter(
        capacity=rate_config["capacity"],
        refill_rate=rate_config["refill_rate"],
        initial_tokens=rate_config["initial_tokens"]
    )

    backoff_config = config_manager.get_backoff_config()
    backoff_strategy = ExponentialBackoffStrategy(
        initial_delay=backoff_config["initial_delay"],
        max_delay=backoff_config["max_delay"],
        multiplier=backoff_config["multiplier"],
        jitter_factor=backoff_config["jitter_factor"],
    )

    # Wrap HTTP client with rate limiting
    rate_limited_client = RateLimitedHttpClient(
        HttpClient(),
        rate_limiter,
        backoff_strategy,
        max_retries=15,
        metrics_collector=metrics_collector,
        auth_provider=auth_provider,
    )

    # Inject into JobberClient
    jobber_client.set_http_client(rate_limited_client)

    return jobber_client
```

#### Usage

**Before:**
```python
# 30+ lines of rate limiting setup code
# (duplicated in migrate.py and entity_extraction.py)
```

**After:**
```python
# In migrate.py and entity_extraction.py
jobber_client = ServiceFactory.create_rate_limited_jobber_client(
    auth_provider=auth_provider,
    repository=repository,
    config_manager=config_manager,
    optimization_level=actual_optimization_level,
    enable_cost_monitoring=actual_enable_cost_monitoring,
)
```

#### Benefits

✅ **Eliminates duplication**: Single source of truth for rate limiting setup
✅ **Maintains current architecture**: No changes to coordinator or extractors
✅ **Preserves separation of concerns**: Setup remains in CLI/service layer
✅ **Testable**: Factory method can be easily unit tested
✅ **Flexible**: Easy to add new rate limiting features
✅ **Backwards compatible**: Existing code continues to work

#### Drawbacks

⚠️ Minimal - slightly more indirection, but improved maintainability outweighs this

---

### Solution 2: Coordinator-Managed Rate Limiting (NOT RECOMMENDED)

**Move rate limiting setup into `BaseMigrationCoordinator.__init__()`**

#### Why This is NOT Recommended

❌ **Violates separation of concerns**: Coordinator should orchestrate, not configure infrastructure
❌ **Breaks dependency injection**: Coordinator would need to create its own dependencies
❌ **Harder to test**: Would need to mock rate limiting in all coordinator tests
❌ **Less flexible**: Different commands couldn't configure rate limiting differently
❌ **Increases coordinator complexity**: Adds 30+ lines to already large class
❌ **Poor cohesion**: Rate limiting is cross-cutting concern, not migration-specific

#### When This Might Make Sense

Only if we needed:
- Dynamic rate limit adjustment during migration (we don't)
- Different rate limits per entity type (we don't - shared is better)
- Coordinator-specific rate limiting logic (we don't)

**Verdict:** Stick with dependency injection pattern. Coordinator receives configured client.

---

### Solution 3: Rate Limiting Module (ALTERNATIVE)

**Create dedicated module: `src/cli/services/rate_limiting_setup.py`**

#### Implementation

```python
def setup_rate_limited_jobber_client(
    jobber_client: JobberClient,
    config_manager: ConfigManagerImpl,
    optimization_level: str,
    repository: Repository,
    auth_provider: AuthProvider,
    enable_cost_monitoring: bool = True,
) -> JobberClient:
    """Configure JobberClient with rate limiting.

    Wraps JobberClient's HTTP client with rate limiting and retry logic.
    Returns the same JobberClient instance after configuration.
    """
    # ... rate limiting setup code ...
    return jobber_client
```

#### Benefits

✅ Dedicated module for rate limiting concerns
✅ Clear naming indicates purpose
✅ Still eliminates duplication

#### Drawbacks

⚠️ More files to maintain vs factory pattern
⚠️ Less discoverable than ServiceFactory (where other factories live)

**Verdict:** Workable, but ServiceFactory pattern is more consistent with existing codebase.

---

## Recommended Approach

### Implementation Plan

**Phase 1: Add Factory Method**

1. Add `create_rate_limited_jobber_client()` to `ServiceFactory` class
2. Include comprehensive docstring with parameter explanations
3. Add logging for rate limiting configuration (capacity, refill rate, optimization level)

**Phase 2: Refactor CLI Commands**

1. Update `migrate.py:368-399` to use factory method
2. Update `entity_extraction.py:83-110` to use factory method
3. Remove duplicated rate limiting setup code
4. Preserve any command-specific logging

**Phase 3: Testing**

1. Add unit tests for factory method
2. Verify integration tests still pass
3. Test with different optimization levels

**Phase 4: Documentation**

1. Update `docs/CONFIGURATION.md` to reference factory method
2. Document factory method in architecture docs
3. Add migration guide for any custom CLI commands

### Code Changes Required

**Files to modify:**
- `src/cli/services/factories.py` - Add factory method (~60 lines)
- `src/cli/migrate.py` - Replace setup with factory call (~25 lines removed, 5 added)
- `src/cli/services/entity_extraction.py` - Replace setup with factory call (~25 lines removed, 5 added)
- `tests/cli/test_service_factory.py` - Add factory method tests (~50 lines)

**Net change:** ~40 lines removed, ~120 lines added (mostly tests and docs)

### Migration Example

**Before (migrate.py:368-399):**
```python
# Initialize rate limiting components with dynamic optimization settings
rate_config = config_manager.get_rate_limit_config(actual_optimization_level)
capacity = rate_config["capacity"]
refill_rate = rate_config["refill_rate"]
initial_tokens = rate_config["initial_tokens"]
requests_per_second = refill_rate / 60

logger.info(
    f"Setting up {actual_optimization_level.upper()} rate limiting "
    f"({capacity} tokens, {refill_rate}/minute, ~{requests_per_second:.0f} req/sec)"
)

# Dynamic optimization for Jobber GraphQL API based on user selection
rate_limiter = TokenBucketRateLimiter(capacity=capacity, refill_rate=refill_rate, initial_tokens=initial_tokens)

# Use backoff strategy from configuration for GraphQL throttling
backoff_config = config_manager.get_backoff_config()
backoff_strategy = ExponentialBackoffStrategy(
    initial_delay=backoff_config["initial_delay"],
    max_delay=backoff_config["max_delay"],
    multiplier=backoff_config["multiplier"],
    jitter_factor=backoff_config["jitter_factor"],
)

# Wrap HTTP client with rate limiting - maximum retries for Jobber GraphQL API
http_client = HttpClient()
rate_limited_client = RateLimitedHttpClient(
    http_client,
    rate_limiter,
    backoff_strategy,
    max_retries=15,  # Maximum retries for GraphQL throttling
    metrics_collector=metrics_collector,
    auth_provider=auth_provider,  # Enable reactive OAuth token refresh on 401 errors
)
jobber_client.set_http_client(rate_limited_client)

# Verify rate limiting is properly configured
logger.info(
    f"Rate limiter configured: {rate_limiter.get_capacity()} tokens, "
    f"{rate_limiter.get_refill_rate()}/min, "
    f"{rate_limiter.get_available_tokens():.1f} available"
)
```

**After:**
```python
# Setup JobberClient with rate limiting via ServiceFactory
jobber_client = ServiceFactory.create_rate_limited_jobber_client(
    auth_provider=auth_provider,
    repository=repository,
    config_manager=config_manager,
    optimization_level=actual_optimization_level,
    enable_cost_monitoring=actual_enable_cost_monitoring,
)

logger.info(
    f"Rate limiting configured: {actual_optimization_level.upper()} optimization level"
)
```

**Reduction:** 32 lines → 8 lines (75% reduction)

---

## Decision Matrix

| Criteria | Factory Pattern | Coordinator-Managed | Dedicated Module |
|----------|----------------|---------------------|------------------|
| **Eliminates duplication** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Separation of concerns** | ✅ Excellent | ❌ Poor | ✅ Good |
| **Testability** | ✅ Easy | ⚠️ Moderate | ✅ Easy |
| **Maintainability** | ✅ High | ⚠️ Moderate | ✅ High |
| **Consistency with codebase** | ✅ High | ❌ Low | ⚠️ Moderate |
| **Implementation complexity** | ✅ Low | ⚠️ Moderate | ✅ Low |
| **Backwards compatibility** | ✅ Perfect | ❌ Breaking | ✅ Perfect |
| **Flexibility** | ✅ High | ⚠️ Low | ✅ High |

**Winner:** **Factory Pattern (Solution 1)**

---

## Conclusion

### Recommendation

**Implement ServiceFactory pattern (Solution 1)**

**Rationale:**
1. Eliminates code duplication while preserving architecture
2. Maintains separation of concerns (setup in CLI layer, not business logic)
3. Consistent with existing `ServiceFactory` usage in codebase
4. Improves testability and maintainability
5. Zero breaking changes - fully backwards compatible

### Key Architectural Principles Preserved

✅ **Dependency Injection**: Coordinator receives configured dependencies
✅ **Single Responsibility**: Each component has one clear purpose
✅ **Shared State**: Token bucket shared via JobberClient instance
✅ **Transparency**: Rate limiting transparent to extractors
✅ **Configurability**: CLI controls optimization level

### DO NOT Move to Coordinator

The coordinator should **orchestrate migration workflow**, not **configure infrastructure**. Rate limiting is a cross-cutting concern that belongs in the service/CLI layer.

**Think of it this way:**
- ❌ Coordinator shouldn't know about token buckets, backoff strategies, or HTTP wrappers
- ✅ Coordinator should know about clients, invoices, quotes, and migration flow

### Next Steps

1. Create task to implement ServiceFactory.create_rate_limited_jobber_client()
2. Refactor migrate.py to use factory
3. Refactor entity_extraction.py to use factory
4. Add comprehensive tests
5. Update documentation

---

## References

- Current implementation: `src/cli/migrate.py:368-399`
- Duplication: `src/cli/services/entity_extraction.py:83-110`
- ServiceFactory: `src/cli/services/factories.py`
- RateLimitedHttpClient: `src/rate_limiting/rate_limited_http_client.py`
- TokenBucketRateLimiter: `src/rate_limiting/token_bucket.py`
- BaseMigrationCoordinator: `src/coordinators/base_migration_coordinator.py`
