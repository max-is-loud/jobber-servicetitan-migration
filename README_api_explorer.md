# Jobber API Explorer

This script explores the Jobber API to identify important top-level entities that would need to be migrated when moving from Jobber to another service management platform.

## Prerequisites

1. You must have already set up OAuth authentication using tightbeam:

   ```bash
   tightbeam oauth init
   ```

2. The script requires the `requests` library (should already be installed with tightbeam):

   ```bash
   pip install requests
   ```

## Usage

Simply run the script:

```bash
python explore_jobber_api.py
```

Or if you made it executable:

```bash
./explore_jobber_api.py
```

## Technical Details

The script uses the Jobber GraphQL API with the required `X-JOBBER-GRAPHQL-VERSION: 2023-11-15` header to ensure compatibility.

## What it does

The script will:

1. **Retrieve OAuth Token** - Uses the OAuth token stored in `tightbeam.db` by the tightbeam tool
2. **Explore Schema** - Queries the GraphQL schema to find all top-level query fields
3. **Sample Entities** - Fetches sample data from major entities like Clients, Jobs, Quotes, etc.
4. **Analyze Relationships** - Shows how entities are connected to each other
5. **Migration Summary** - Provides a comprehensive list of entities that would need migration

## Key Entities Discovered

The script identifies these main entity categories:

- **Core Business Entities**: Clients, Jobs, Quotes, Invoices, Properties
- **Operational Entities**: Requests, Assessments, Visits, Expenses, TimeSheet Entries
- **Supporting Entities**: Users, Products/Services, Notes, Attachments, Custom Fields, Tags
- **Financial Entities**: Payment Records, Line Items, Tax Rates

## Output

The script provides:

- A list of all GraphQL query fields available in the API
- Sample data from each major entity type
- Relationship mapping between entities
- A summary of migration requirements

This information is essential for understanding what data needs to be extracted and migrated when moving away from Jobber to another service management platform.
