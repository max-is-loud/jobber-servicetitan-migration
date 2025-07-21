# TightBeam v2 - Jobber Data Migration Tool

A command-line tool for extracting client and invoice data from Jobber GraphQL API and persisting it to SQLite database using object-oriented architecture.

## Features

- 🚀 **Simple CLI Interface** - Easy-to-use command with clear options
- 🔐 **Dual Authentication** - Supports both OAuth2 and environment token authentication
- 🔄 **Automatic Token Refresh** - OAuth2 tokens refresh automatically when expired
- 📊 **Complete Data Migration** - Fetches both clients and invoices with relationships
- 🔄 **Cursor-based Pagination** - Efficiently handles large datasets
- 💾 **SQLite Storage** - Reliable local database persistence  
- 🛡️ **Robust Error Handling** - Comprehensive error management with user-friendly messages
- 📝 **Structured Logging** - Detailed progress tracking and summary reporting
- 🏗️ **Clean Architecture** - Dependency injection and single responsibility patterns
- ⚡ **Intelligent Rate Limiting** - Token bucket algorithm with exponential backoff and metrics

## Requirements

- Valid Jobber API access (either OAuth2 app or API token)

- Internet connection for API access

## Installation

### Using Poetry (Recommended)

```bash
# Clone the repository
git clone https://github.com/maxmorin/tightbeam-v2.git
cd tightbeam-v2

# Install dependencies with Poetry
poetry install

# Activate the virtual environment
poetry shell
```

### Using pip

```bash
# Clone the repository
git clone https://github.com/maxmorin/tightbeam-v2.git
cd tightbeam-v2

# Install dependencies
pip install -r requirements.txt
```

## Authentication Setup

TightBeam v2 supports two authentication methods. Choose the one that best fits your needs:

### Option 1: Environment Token (Simple)

Set your Jobber API token as an environment variable:

```bash
export JOBBER_TOKEN="your_jobber_api_token_here"
```

Or create a `.env` file in the project root:

```env
JOBBER_TOKEN=your_jobber_api_token_here
```

### Option 2: OAuth2 (Recommended for Production)

Set up OAuth2 environment variables:

```bash
export JOBBER_CLIENT_ID="your_oauth2_client_id"
export JOBBER_CLIENT_SECRET="your_oauth2_client_secret"
export JOBBER_REDIRECT_URI="your_redirect_uri"
```

Or add to your `.env` file:

```env
JOBBER_CLIENT_ID=your_oauth2_client_id
JOBBER_CLIENT_SECRET=your_oauth2_client_secret
JOBBER_REDIRECT_URI=your_redirect_uri
```

## Configuration

TightBeam v2 uses a centralized YAML configuration system that allows you to customize rate limiting, pagination, delays, and other performance settings without modifying code.

### Configuration Files

- `config/settings.yaml` - Main configuration with default values
- `config/settings_dev.yaml` - Development environment overrides  
- `config/settings_prod.yaml` - Production environment overrides

### Key Settings

```yaml
# Rate limiting (prevents API throttling)
rate_limits:
  moderate:              # Recommended default
    capacity: 400        # Token bucket capacity
    refill_rate: 360     # ~6 requests/second
    safety_margin: 0.28  # 28% safety buffer

# Pagination (items per GraphQL request)
pagination:
  quotes: 30             # Increased from hardcoded 5
  clients: 30            # Balanced for performance
  invoices: 30           # Configurable per entity

# Delays (prevent API overload)
delays:
  page_delay: 1.0        # Seconds between requests
```

### Performance Tuning

- **Conservative**: Use for unstable connections, slower but reliable
- **Moderate**: Default balanced settings (recommended)
- **Aggressive**: Maximum speed, requires valid OAuth and stable connection

For detailed configuration options, see [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## Quick Start

### Method 1: Environment Token

1. **Set your token**:

   ```bash
   export JOBBER_TOKEN="your_jobber_api_token_here"
   ```

2. **Run migration**:

   ```bash
   tightbeam migrate --db ./jobber_data.sqlite
   ```

### Method 2: OAuth2 Setup

1. **Configure OAuth2 variables**:

   ```bash
   export JOBBER_CLIENT_ID="your_client_id"
   export JOBBER_CLIENT_SECRET="your_client_secret"  
   export JOBBER_REDIRECT_URI="your_redirect_uri"
   ```

2. **Initialize OAuth2 authorization**:

   ```bash
   tightbeam oauth init
   ```

   This opens your browser for authorization.

3. **Complete authorization** by copying the code from the callback URL:

   ```bash
   tightbeam oauth callback --code YOUR_AUTHORIZATION_CODE
   ```

4. **Run migration**:

   ```bash
   tightbeam migrate --db ./jobber_data.sqlite
   ```

## Usage

### Authentication Management

Check your current authentication status:

```bash
# Check authentication status
tightbeam oauth status
```

#### OAuth2 Commands

```bash
# Initialize OAuth2 flow (opens browser)
tightbeam oauth init

# Complete OAuth2 authorization
tightbeam oauth callback --code YOUR_CODE

# Check token status and expiration
tightbeam oauth status

# Clear stored OAuth2 tokens
tightbeam oauth clear
```

### Data Migration

#### Basic Migration

```bash
# Migrate data to SQLite database
tightbeam migrate --db ./jobber_data.sqlite

# Using Poetry
poetry run tightbeam migrate --db ./jobber_data.sqlite
```

#### Verbose Output

```bash
# Enable verbose logging for debugging
tightbeam migrate --db ./jobber_data.sqlite --verbose

# Short form
tightbeam migrate --db ./jobber_data.sqlite -v
```

#### Using Python Module

```bash
# Run as Python module
python -m src.cli migrate --db ./jobber_data.sqlite

# With verbose output
python -m src.cli migrate --db ./jobber_data.sqlite --verbose
```

### Authentication Priority

TightBeam uses the following authentication priority:

1. **JOBBER_TOKEN** environment variable (if set)
2. **OAuth2 tokens** (if configured and authorized)
3. **Error** if neither is available

## Output

The tool will create a SQLite database with two tables:

### `clients` table

- `id` - Unique client identifier
- `first_name` - Client's first name  
- `last_name` - Client's last name
- `email` - Primary email address
- `phone` - Primary phone number
- `created_at` - ISO format creation timestamp

### `invoices` table

- `id` - Unique invoice identifier
- `client_id` - Foreign key to clients table
- `number` - Invoice number
- `total_cents` - Total amount in cents
- `status` - Invoice status (PAID, PENDING, etc.)
- `issued_at` - ISO format issue timestamp

## Example Output

```bash
INFO: Connecting to database: ./jobber_data.sqlite
INFO: Starting migration process
INFO: Starting migration workflow
INFO: Initializing database schema
INFO: Starting client migration
INFO: Processed 50 clients (total: 50)
INFO: Starting invoice migration  
INFO: Processed 125 invoices (total: 125)
INFO: Migration completed: 50 clients, 125 invoices in 1m 23.5s

==================================================
MIGRATION SUMMARY
==================================================
Clients Processed: 50
Invoices Processed: 125
Duration: 1m 23.5s
Errors Count: 0
Status: SUCCESS
==================================================
INFO: Migration completed with exit code 0
```

## Error Handling

The tool provides clear error messages and appropriate exit codes:

| Exit Code | Error Type | Description |
|-----------|------------|-------------|
| 0 | Success | Migration completed successfully |
| 1 | Configuration | Missing authentication or OAuth2 setup issues |
| 2 | API Error | Network or API communication issues |
| 3 | Data Mapping | Data transformation problems |
| 4 | Database | SQLite database operation failures |
| 5 | Unexpected | System or runtime errors |

## Troubleshooting

=======

### Verifying OAuth2 Setup

To verify your OAuth2 authentication configuration is working correctly, use the built-in status command:

```bash
# Check OAuth2 token status
tightbeam oauth status

# Using Poetry
poetry run tightbeam oauth status

# Using Python module
python -m src.cli oauth status
```

This command will:

- ✅ Verify JOBBER_TOKEN environment variable is set
- 🔗 Test API connectivity with your token
- 📋 Report detailed status and troubleshooting tips

### Missing JOBBER_TOKEN

### Authentication Issues

#### No Authentication Configured

```bash
Configuration Error: No authentication method available
```

**Solution**: Choose one authentication method:

- Set `JOBBER_TOKEN` environment variable, OR
- Set OAuth2 variables and run `tightbeam oauth init`

#### OAuth2 Not Authorized

```bash
Configuration Error: No OAuth2 tokens found
```

**Solution**: Complete OAuth2 authorization:

```bash
tightbeam oauth init
tightbeam oauth callback --code YOUR_CODE
```

#### OAuth2 Token Expired

OAuth2 tokens refresh automatically, but if manual refresh fails:

```bash
Configuration Error: OAuth2 tokens are invalid and refresh failed
```

**Solution**: Re-authorize:

```bash
tightbeam oauth clear
tightbeam oauth init
```

### API Connection Issues

```bash
API Error: Failed to connect to Jobber API
```

**Solution**:

- Check your internet connection
- Verify your authentication is valid:
  - For tokens: ensure JOBBER_TOKEN is not expired
  - For OAuth2: run `tightbeam oauth status` to check token status
- Ensure API rate limits are not exceeded

### Database Permission Issues

```bash
Database Error: Unable to create database file
```

**Solution**:

- Ensure the parent directory exists and is writable
- Check available disk space
- Verify file permissions

### Network Timeout

If migration is slow or times out:

- Use `--verbose` flag to monitor progress
- Check network connection stability
- Consider running during off-peak hours for better API performance

## Rate Limiting

TightBeam v2 includes intelligent rate limiting to respect Jobber API limits while maximizing throughput.

### Overview

- **Token Bucket Algorithm**: 300 token capacity with 180 tokens/minute refill rate (~3 req/sec)
- **Exponential Backoff**: Automatic retry with jitter for rate limit errors (HTTP 429 and GraphQL throttling)
- **Jobber-Optimized**: Designed specifically for Jobber GraphQL API cost patterns with deferred notes
- **Page Delays**: Mandatory 2-second delay between pagination requests
- **Sustained Rate**: Targets 50-60 requests/minute for maximum reliability
- **Extended Retries**: Up to 15 retry attempts with longer backoff delays (5-300 seconds)
- **Automatic Throttling**: Seamlessly delays requests when limits are approached

### Rate Limiting Metrics

The migration summary includes comprehensive rate limiting statistics:

```bash
==================================================
MIGRATION SUMMARY
==================================================
Clients Processed: 250
Invoices Processed: 1,200
Duration: 4m 32.1s
Errors Count: 0
Status: SUCCESS

Rate Limiting:
  Requests per Minute: 387.2
  Total Requests: 1,450
  Throttled Requests: 23
  Rate Limit Errors: 2
  Average Response Time: 0.245s
  Throttle Rate: 1.6%
==================================================
```

### Metrics Explained

| Metric | Description |
|--------|-------------|
| **Requests per Minute** | Current throughput rate |
| **Total Requests** | All API calls made during migration |
| **Throttled Requests** | Requests delayed by token bucket |
| **Rate Limit Errors** | HTTP 429 responses received |
| **Average Response Time** | Mean API response time |
| **Throttle Rate** | Percentage of requests that were throttled |

### Performance Optimization

The rate limiting system automatically:

- **Prevents Rate Limit Errors**: Proactively throttles before hitting limits and detects GraphQL throttling responses
- **Maximizes Throughput**: Maintains optimal request rates while respecting Jobber API constraints
- **Handles Bursts**: Allows temporary speed increases for small datasets
- **Adapts to API Responses**: Honors Retry-After headers and handles GraphQL "Throttled" errors
- **Provides Visibility**: Detailed metrics for performance monitoring

### Rate Limit Configuration

Rate limiting is automatically configured and requires no user configuration. The system is tuned for:

- Jobber's GraphQL API limits with conservative safety margins
- Optimal balance between speed and reliability  
- Minimal throttling for typical dataset sizes
- Graceful handling of both HTTP 429 and GraphQL throttling responses
- Robust error detection and automatic retry with exponential backoff

## Performance Optimization

TightBeam v2 offers configurable performance optimization levels to balance speed with API safety based on your specific requirements.

### Optimization Levels

#### Conservative (4 req/sec)

```bash
tightbeam migrate --optimization-level conservative
```

- **Best for**: Production environments, large-scale migrations, unattended operations
- **Safety margin**: 52% below Jobber API limits
- **Performance**: ~4 requests/second sustained
- **Risk**: Very low
- **Recommended when**: Maximum reliability is priority over speed

#### Moderate (6 req/sec) - **Default**

```bash
tightbeam migrate --optimization-level moderate
# or simply:
tightbeam migrate
```

- **Best for**: Most use cases, balanced performance and safety
- **Safety margin**: 28% below Jobber API limits  
- **Performance**: ~6 requests/second sustained (2x improvement over v1)
- **Risk**: Low
- **Recommended when**: Standard migration with good balance of speed and safety

#### Aggressive (8 req/sec)

```bash
tightbeam migrate --optimization-level aggressive
```

- **Best for**: Speed-critical migrations, small datasets, active monitoring
- **Safety margin**: 4% below Jobber API limits
- **Performance**: ~8 requests/second sustained (maximum throughput)
- **Risk**: Medium (close to API limits)
- **Recommended when**: Maximum speed needed with active monitoring

### GraphQL Cost Monitoring

Enable detailed performance monitoring and cost analysis:

```bash
# Enable cost monitoring (default: enabled)
tightbeam migrate --enable-cost-monitoring

# Disable cost monitoring for minimal overhead
tightbeam migrate --disable-cost-monitoring

# Enable verbose cost analysis
tightbeam migrate --cost-monitoring-verbose
```

#### Cost Monitoring Features

- **GraphQL Query Cost Tracking**: Monitor actual vs requested costs
- **Rate Limit Status**: Real-time remaining requests and reset timing
- **Performance Metrics**: Entities/minute, cost accuracy, API efficiency
- **Optimization Insights**: Data-driven recommendations for tuning

#### Example Output with Verbose Monitoring

```bash
🚀 Performance Configuration:
   • Optimization level: MODERATE
   • Target rate: 6 requests/sec
   • Safety margin: 28% below API limits
   • GraphQL cost monitoring: ENABLED
   • Verbose cost monitoring: ENABLED

📊 Migration Performance Analysis:
   • Migration speed: 247.3 entities/minute
   • Total entities: 1,450 in 5m 52.1s

🧮 GraphQL Cost Analysis:
   • Total queries: 145
   • Avg requested cost: 6365
   • Avg actual cost: 6127
   • Cost accuracy: 96.3%

🔄 Rate Limit Status:
   • Remaining requests: 423
   • Reset in: 127s
```

### Performance Guidelines

#### Choosing the Right Optimization Level

| Dataset Size | Environment | Monitoring | Recommended Level |
|--------------|-------------|------------|-------------------|
| < 1,000 entities | Development | Active | **Aggressive** |
| 1,000-10,000 entities | Production | Periodic | **Moderate** |
| > 10,000 entities | Production | Minimal | **Conservative** |
| Any size | Unattended | None | **Conservative** |

#### Best Practices

1. **Start with Moderate**: Default provides excellent balance for most scenarios
2. **Monitor First Run**: Use `--cost-monitoring-verbose` to understand your API usage patterns
3. **Production Safety**: Use Conservative for critical production migrations
4. **Speed When Needed**: Use Aggressive for time-sensitive migrations with active monitoring
5. **Test Performance**: Measure actual migration speed for your specific data patterns

For detailed technical analysis and rationale, see `docs/JOBBER_API_OPTIMIZATION.md`.

## Development

### Running Tests

```bash
# Run integration tests
python integration_test.py

# Check CLI help
python -m src.cli --help

# Check OAuth2 commands
python -m src.cli oauth --help
```

### Project Structure

```bash
src/
├── auth/                 # Authentication management (OAuth2 + Token)
├── clients/              # Jobber API client with auto-refresh
├── coordinators/         # Workflow orchestration
├── exceptions/           # Domain-specific exceptions
├── interfaces/           # Protocol definitions
├── loggers/              # Logging implementations
├── mappers/              # Data transformation
├── models/               # Data models
├── repositories/         # Database operations (includes OAuth2 storage)
└── cli.py                # Command-line interface with OAuth2 commands
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run integration tests
5. Submit a pull request

## Support

For issues and questions:

- Create an issue on GitHub
- Check the troubleshooting section above
- Review error messages and exit codes for guidance
- Use `tightbeam oauth status` to check authentication status
