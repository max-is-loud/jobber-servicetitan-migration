# TightBeam v2 - Jobber Data Migration Tool

A command-line tool for extracting client and invoice data from Jobber GraphQL API and persisting it to SQLite database using object-oriented architecture.

## Features

- 🚀 **Simple CLI Interface** - Easy-to-use command with clear options
- 📊 **Complete Data Migration** - Fetches both clients and invoices with relationships
- 🔄 **Cursor-based Pagination** - Efficiently handles large datasets
- 💾 **SQLite Storage** - Reliable local database persistence  
- 🛡️ **Robust Error Handling** - Comprehensive error management with user-friendly messages
- 📝 **Structured Logging** - Detailed progress tracking and summary reporting
- 🏗️ **Clean Architecture** - Dependency injection and single responsibility patterns

## Requirements

- Python 3.8 or higher
- Valid Jobber API access token
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

## Configuration

Set your Jobber API token as an environment variable:

```bash
export JOBBER_TOKEN="your_jobber_api_token_here"
```

Or create a `.env` file in the project root:

```env
JOBBER_TOKEN=your_jobber_api_token_here
```

## Usage

### Basic Migration

```bash
# Migrate data to SQLite database
tightbeam --db ./jobber_data.sqlite

# Using Poetry
poetry run tightbeam --db ./jobber_data.sqlite
```

### Verbose Output

```bash
# Enable verbose logging for debugging
tightbeam --db ./jobber_data.sqlite --verbose

# Short form
tightbeam --db ./jobber_data.sqlite -v
```

### Using Python Module

```bash
# Run as Python module
python -m src.cli --db ./jobber_data.sqlite

# With verbose output
python -m src.cli --db ./jobber_data.sqlite --verbose
```

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
| 1 | Configuration | Missing or invalid JOBBER_TOKEN |
| 2 | API Error | Network or API communication issues |
| 3 | Data Mapping | Data transformation problems |
| 4 | Database | SQLite database operation failures |
| 5 | Unexpected | System or runtime errors |

## Troubleshooting

### Missing JOBBER_TOKEN

```bash
Configuration Error: JOBBER_TOKEN environment variable is required
```

**Solution**: Set the JOBBER_TOKEN environment variable with your Jobber API access token.

### API Connection Issues

```bash
API Error: Failed to connect to Jobber API
```

**Solution**:

- Check your internet connection
- Verify your API token is valid and not expired
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

## Development

### Running Tests

```bash
# Run integration tests
python integration_test.py

# Check CLI help
python -m src.cli --help
```

### Project Structure

```bash
src/
├── auth/                 # Authentication management
├── clients/              # Jobber API client
├── coordinators/         # Workflow orchestration
├── exceptions/           # Domain-specific exceptions
├── interfaces/           # Protocol definitions
├── loggers/              # Logging implementations
├── mappers/              # Data transformation
├── models/               # Data models
├── repositories/         # Database operations
└── cli.py                # Command-line interface
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
