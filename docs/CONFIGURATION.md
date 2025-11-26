# TightBeam v2 Configuration Guide

This document provides comprehensive guidance for configuring TightBeam v2's centralized YAML configuration system.

## Overview

TightBeam v2 uses a centralized configuration system that consolidates all performance-critical settings into YAML files. This approach eliminates hardcoded constants and provides easy environment-specific customization.

## Configuration Files

### Base Configuration

- `config/settings.yaml` - Main configuration file with default values
- `config/settings_dev.yaml` - Development environment overrides
- `config/settings_prod.yaml` - Production environment overrides

### Configuration Loading

The system automatically loads the base configuration and applies environment-specific overrides:

1. Load `config/settings.yaml` (base configuration)
2. If environment specified, merge `config/settings_{env}.yaml` overrides
3. Validate all configuration values
4. Provide validated configuration to all components

## Configuration Sections

### Rate Limiting (`rate_limits`)

Controls API request rate limiting to prevent throttling by Jobber's GraphQL API.

```yaml
rate_limits:
  conservative:
    capacity: 250           # Token bucket capacity
    refill_rate: 240        # Tokens per minute refill rate
    initial_tokens: 40      # Starting tokens
    safety_margin: 0.52     # 52% safety margin
  moderate:
    capacity: 400
    refill_rate: 360
    initial_tokens: 60
    safety_margin: 0.28     # Default optimization level
  aggressive:
    capacity: 500
    refill_rate: 480
    initial_tokens: 100
    safety_margin: 0.04     # High-performance setting
```

**Validation Rules:**

- `capacity`: 1-10,000 (integer)
- `refill_rate`: 1-60,000 tokens/minute (integer)
- `initial_tokens`: 0-capacity (integer)
- `safety_margin`: 0.0-1.0 (float)

**Usage Guidelines:**

- **Conservative**: Use for stable, error-free migrations at slower pace
- **Moderate**: Default setting balancing speed and reliability
- **Aggressive**: Maximum speed, requires valid OAuth tokens and stable connection

### Pagination (`pagination`)

Controls how many items are fetched per GraphQL request.

```yaml
pagination:
  clients: 30             # Client entities per page
  invoices: 30            # Invoice entities per page
  quotes: 30              # Quote entities per page (increased from hardcoded 5)
  jobs: 30                # Job entities per page
  properties: 30          # Property entities per page
  requests: 30            # Request entities per page
  users: 30               # User entities per page
  expenses: 30            # Expense entities per page
  visits: 30              # Visit entities per page
  timesheet_entries: 30   # Timesheet entry entities per page
  product_services: 30    # Product/service entities per page
  tax_rates: 30           # Tax rate entities per page
  notes: 50               # Note entities per page (Pass 1: metadata extraction)
  nested_notes: 10        # Notes nested within other entities
  default: 30             # Default for new entity types
```

**Validation Rules:**

- All values: 1-1,000 (integer)
- Warning for values >100 (may hit API rate limits)

**Performance Impact:**

- Higher values = fewer API requests but higher risk of timeouts
- Lower values = more API requests but more reliable
- Recommended range: 20-50 for most use cases

### Delays (`delays`)

Controls timing delays between API requests and operations.

```yaml
delays:
  page_delay: 1.0         # Seconds between pagination requests
  request_timeout: 30.0   # HTTP request timeout in seconds
  retry_base_delay: 2.0   # Base delay for retry attempts
```

**Validation Rules:**

- `page_delay`: ≥0.0 seconds (float), warning if >30s
- `request_timeout`: >0.0 seconds (float), max 300s
- `retry_base_delay`: >0.0 seconds (float), max 60s

**Tuning Guidelines:**

- Increase `page_delay` if experiencing API throttling
- Decrease `page_delay` for faster migrations (if API allows)
- Adjust `request_timeout` based on network conditions

### Exponential Backoff (`backoff`)

Controls retry behavior for failed API requests.

```yaml
backoff:
  initial_delay: 5.0      # First retry delay in seconds
  max_delay: 300.0        # Maximum retry delay in seconds
  multiplier: 2.0         # Delay multiplier for each retry
  jitter_factor: 0.2      # Randomization factor (0.0-1.0)
```

**Validation Rules:**

- `initial_delay`: >0.0 seconds (float), max 60s
- `max_delay`: >0.0 seconds (float), max 3600s
- `multiplier`: >1.0 (float), max 10.0
- `jitter_factor`: 0.0-1.0 (float)

**Algorithm:**

```
next_delay = min(current_delay * multiplier, max_delay)
actual_delay = next_delay ± (next_delay * jitter_factor * random)
```

### Logging (`logging`)

Controls application logging behavior.

```yaml
logging:
  level: "INFO"           # Log level: DEBUG, INFO, WARNING, ERROR
  format: "detailed"      # Log format: simple, detailed, json
  enable_file_logging: false
  log_file_path: "logs/tightbeam.log"
```

### Database (`database`)

Controls SQLite database settings.

```yaml
database:
  connection_timeout: 30.0
  busy_timeout: 5000      # Milliseconds
  enable_wal_mode: true   # Write-Ahead Logging for performance
  enable_foreign_keys: true
```

## Environment-Specific Configuration

### Development (`config/settings_dev.yaml`)

Conservative settings for development and testing:

```yaml
# Development overrides for safer testing
rate_limits:
  moderate:
    capacity: 100         # Reduced capacity
    refill_rate: 120      # Slower rate
    safety_margin: 0.8    # Higher safety margin

pagination:
  clients: 10             # Smaller pages for testing
  invoices: 10
  quotes: 10
  default: 10

delays:
  page_delay: 2.0         # Longer delays for stability
```

### Production (`config/settings_prod.yaml`)

Optimized settings for production environments:

```yaml
# Production overrides for maximum performance
rate_limits:
  aggressive:
    capacity: 600         # Higher capacity
    refill_rate: 600      # Faster rate
    safety_margin: 0.02   # Minimal safety margin

pagination:
  clients: 50             # Larger pages for efficiency
  invoices: 50
  quotes: 50
  default: 50

delays:
  page_delay: 0.5         # Reduced delays for speed

logging:
  level: "WARNING"        # Reduced logging
  enable_file_logging: true
```

## Migration Guide

### From Hardcoded Values

If migrating from hardcoded constants:

1. **Identify Current Values**: Review existing code for hardcoded values
2. **Add to Configuration**: Add values to appropriate YAML sections
3. **Update Code**: Replace hardcoded values with `config_manager.get_*_config()` calls
4. **Test**: Verify configuration loading and validation work correctly

### Example Migration

**Before (hardcoded):**

```python
time.sleep(1.0)  # Hardcoded delay
rate_limiter = TokenBucketRateLimiter(capacity=400, refill_rate=360)
```

**After (configurable):**

```python
page_delay = config_manager.get_delay_config("page_delay")
time.sleep(page_delay)

rate_config = config_manager.get_rate_limit_config(optimization_level)
rate_limiter = TokenBucketRateLimiter(
    capacity=rate_config["capacity"],
    refill_rate=rate_config["refill_rate"]
)
```

## Configuration Schema

### Complete Schema Reference

```yaml
# Rate limiting for API throttling prevention
rate_limits:
  conservative:
    capacity: int          # 1-10,000
    refill_rate: int       # 1-60,000 per minute
    initial_tokens: int    # 0-capacity
    safety_margin: float   # 0.0-1.0
  moderate: { ... }        # Same structure
  aggressive: { ... }      # Same structure

# Pagination sizes for GraphQL requests
pagination:
  clients: int             # 1-1,000
  invoices: int            # 1-1,000
  quotes: int              # 1-1,000
  jobs: int                # 1-1,000
  properties: int          # 1-1,000
  requests: int            # 1-1,000
  users: int               # 1-1,000
  expenses: int            # 1-1,000
  visits: int              # 1-1,000
  timesheet_entries: int   # 1-1,000
  product_services: int    # 1-1,000
  tax_rates: int           # 1-1,000
  notes: int               # 1-1,000
  nested_notes: int        # 1-100 (nested within parent entities)
  default: int             # 1-1,000

# Timing delays for operations
delays:
  page_delay: float        # ≥0.0 seconds
  request_timeout: float   # >0.0 seconds, ≤300
  retry_base_delay: float  # >0.0 seconds, ≤60

# Exponential backoff for retries
backoff:
  initial_delay: float     # >0.0 seconds, ≤60
  max_delay: float         # >0.0 seconds, ≤3600
  multiplier: float        # >1.0, ≤10.0
  jitter_factor: float     # 0.0-1.0

# Logging configuration
logging:
  level: string            # DEBUG, INFO, WARNING, ERROR
  format: string           # simple, detailed, json
  enable_file_logging: bool
  log_file_path: string

# Database settings
database:
  connection_timeout: float
  busy_timeout: int        # Milliseconds
  enable_wal_mode: bool
  enable_foreign_keys: bool
```

## Troubleshooting

### Common Configuration Errors

#### 1. Invalid YAML Syntax

**Error**: `yaml.scanner.ScannerError: while parsing...`
**Solution**: Validate YAML syntax, check indentation and quotes

#### 2. Type Mismatch

**Error**: `Pagination size for clients must be an integer, got str`
**Solution**: Ensure numeric values are not quoted

```yaml
# Wrong
pagination:
  clients: "30"

# Correct
pagination:
  clients: 30
```

#### 3. Value Out of Range

**Error**: `Rate limit capacity must be positive, got -1`
**Solution**: Check all values are within valid ranges

#### 4. Missing Configuration File

**Error**: `ConfigurationError: Configuration file not found`
**Solution**: Ensure `config/settings.yaml` exists in project root

### Performance Troubleshooting

#### Slow Migrations

1. Check `page_delay` - reduce if too high
2. Increase pagination sizes (if API allows)
3. Use more aggressive rate limiting settings
4. Verify OAuth tokens are valid

#### API Throttling/Rate Limiting

1. Increase `page_delay` between requests
2. Reduce pagination sizes
3. Use more conservative rate limiting
4. Increase `safety_margin` values

#### Configuration Loading Errors

1. Verify YAML file syntax
2. Check file permissions
3. Validate all required sections exist
4. Review validation error messages

### Validation Error Reference

| Error Type | Cause | Solution |
|------------|-------|----------|
| `ValueError: Pagination size...` | Invalid pagination value | Check range 1-1,000 |
| `ValueError: Rate limit capacity...` | Invalid rate limit | Check positive integers |
| `ValueError: Page delay must...` | Invalid delay value | Check non-negative numbers |
| `ConfigurationError: Configuration not loaded` | Missing config file | Ensure YAML files exist |
| `yaml.scanner.ScannerError` | YAML syntax error | Validate YAML formatting |

## Best Practices

### 1. Environment Management

- Use separate override files for each environment
- Keep sensitive values out of version control
- Test configuration changes in development first

### 2. Performance Tuning

- Start with conservative settings
- Gradually increase performance parameters
- Monitor API response times and error rates
- Document changes and their effects

### 3. Validation

- Always validate configuration after changes
- Use appropriate data types (int vs float vs string)
- Stay within recommended value ranges
- Review validation warnings carefully

### 4. Maintenance

- Keep configuration comments up to date
- Document custom settings and their rationale
- Regular review of performance metrics
- Update documentation when adding new settings

## API Reference

### ConfigManager Methods

```python
from src.config import ConfigManagerImpl

config_manager = ConfigManagerImpl()

# Rate limiting configuration
rate_config = config_manager.get_rate_limit_config("moderate")
# Returns: {"capacity": 400, "refill_rate": 360, "initial_tokens": 60, "safety_margin": 0.28}

# Pagination configuration
page_size = config_manager.get_pagination_config("clients")  # Returns: 30
default_size = config_manager.get_pagination_config()        # Returns: 30

# Delay configuration
page_delay = config_manager.get_delay_config("page_delay")   # Returns: 1.0

# Backoff configuration
backoff_config = config_manager.get_backoff_config()
# Returns: {"initial_delay": 5.0, "max_delay": 300.0, "multiplier": 2.0, "jitter_factor": 0.2}

# Reload configuration (useful for testing)
config_manager.reload_config()                              # Reload base config
config_manager.reload_config("dev")                         # Reload with dev overrides
```

### Error Handling

```python
from src.exceptions import ConfigurationError

try:
    config_manager = ConfigManagerImpl()
    rate_config = config_manager.get_rate_limit_config("invalid_level")
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    # Handle gracefully or exit
```

## Support

For configuration issues:

1. Check this documentation
2. Review validation error messages
3. Verify YAML syntax and file structure
4. Test with minimal configuration first
5. Check logs for detailed error information
