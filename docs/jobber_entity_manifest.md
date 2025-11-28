# Jobber Entity Manifest

**Version**: 1.0
**API Version**: 2023-11-15
**Generated**: 2025-11-24
**Purpose**: Canonical schema reference for Tightbeam v2 to prevent field hallucinations

---

## Overview

This document serves as the single source of truth for Jobber's GraphQL entity schema as used by Tightbeam. It defines:

- Which entities are supported for extraction
- Field names, types, and roles for each entity
- Relationship patterns between entities
- GraphQL query patterns and cost optimization rules

**⚠️ CRITICAL RULE**: If a field is NOT listed in this manifest, treat it as non-existent unless explicitly verified in live Jobber docs or schema introspection.

---

## Entity Priority Levels

### Priority 1: Core Business Entities
These entities form the core of a Jobber migration and are REQUIRED for full data coverage:

- **client** - Customers who pay for services
- **property** - Physical locations associated with clients
- **request** - Service requests from clients
- **quote** - Price quotes for services
- **job** - Work orders for services
- **visit** - Scheduled service visits
- **invoice** - Billing invoices
- **expense** - Business expenses
- **user** - Team members and account users
- **product_service** - Catalog items for jobs/invoices
- **tax_rate** - Tax rates for invoicing
- **note** - Polymorphic notes attached to entities
- **attachment** - File attachments linked to notes

### Priority 2: Extended Functionality
These entities provide additional functionality and should be extracted when available:

- **timesheet_entry** - Time tracking entries
- **task** (planned) - To-do tasks
- **reminder** (planned) - Scheduled reminders
- **schedule** (planned) - Calendar events
- **event** (planned) - Activity log events

---

## Entity Schemas

### Client

**GraphQL Type**: `Client`
**Primary Key**: `id`
**Description**: Customer entities who pay for services

#### Fields

| Field Name | Type | Role | Description |
|-----------|------|------|-------------|
| `id` | `ID!` | primary_key | Unique identifier (EncodedId) |
| `firstName` | `String!` | display | Client's first name |
| `lastName` | `String!` | display | Client's last name |
| `emails` | `[Email!]!` | contact | Array of email addresses |
| `phones` | `[Phone!]!` | contact | Array of phone numbers |
| `createdAt` | `ISO8601DateTime!` | metadata | Creation timestamp |

#### Tightbeam Mapping Notes
- **emails**: Primary email extracted to `email` field, additional emails stored as JSON array in `additional_emails`
- **phones**: Primary phone extracted to `phone` field, additional phones stored as JSON array in `additional_phones`

#### Relationships
- **has_many** `property` - Client properties
- **has_many** `note` - Client notes
- **has_many** `request` - Service requests
- **has_many** `quote` - Price quotes
- **has_many** `job` - Work orders
- **has_many** `invoice` - Billing invoices

---

### Property

**GraphQL Type**: `Property`
**Primary Key**: `id`
**Description**: Physical locations associated with clients

#### Fields

| Field Name | Type | Role | Description |
|-----------|------|------|-------------|
| `id` | `ID!` | primary_key | Unique identifier |
| `client` | `Client` | foreign_key | Client who owns this property |
| `address` | `String` | location | Property address |
| `createdAt` | `ISO8601DateTime!` | metadata | Creation timestamp |
| `updatedAt` | `ISO8601DateTime!` | metadata | Last update timestamp |

#### Relationships
- **belongs_to** `client` - Owner client (FK: `client_id`)
- **has_many** `note` - Property notes

---

### Request

**GraphQL Type**: `Request`
**Primary Key**: `id`
**Description**: Service requests from clients

#### Fields

| Field Name | Type | Role | Description |
|-----------|------|------|-------------|
| `id` | `ID!` | primary_key | Unique identifier |
| `title` | `String` | display | Request title |
| `description` | `String` | display | Request description |
| `status` | `String` | state | Request status |
| `priority` | `String` | state | Request priority |
| `source` | `String` | metadata | Request origin |
| `assignedTo` | `User` | foreign_key | Assigned team member |
| `client` | `Client` | foreign_key | Client who made request |
| `property` | `Property` | foreign_key | Related property |
| `convertedToQuote` | `Quote` | foreign_key | Quote created from request |
| `convertedToJob` | `Job` | foreign_key | Job created from request |
| `createdAt` | `ISO8601DateTime!` | metadata | Creation timestamp |
| `updatedAt` | `ISO8601DateTime!` | metadata | Last update timestamp |

#### Relationships
- **belongs_to** `client` (FK: `client_id`)
- **belongs_to** `property` (FK: `property_id`)
- **belongs_to** `user` (FK: `assigned_to`)
- **has_many** `note`

---

### Quote

**GraphQL Type**: `Quote`
**Primary Key**: `id`
**Description**: Price quotes for services

#### Fields

| Field Name | Type | Role | Description |
|-----------|------|------|-------------|
| `id` | `ID!` | primary_key | Unique identifier |
| `quoteNumber` | `String` | display | Quote number |
| `title` | `String` | display | Quote title |
| `quoteStatus` | `String` | state | Quote status |
| `total` | `Money` | financial | Total amount |
| `client` | `Client` | foreign_key | Client for quote |
| `property` | `Property` | foreign_key | Related property |
| `createdAt` | `ISO8601DateTime!` | metadata | Creation timestamp |
| `updatedAt` | `ISO8601DateTime!` | metadata | Last update timestamp |

#### Relationships
- **belongs_to** `client` (FK: `client_id`)
- **belongs_to** `property` (FK: `property_id`)
- **has_many** `note`

---

### Job

**GraphQL Type**: `Job`
**Primary Key**: `id`
**Description**: Work orders for services

#### Fields

| Field Name | Type | Role | Description |
|-----------|------|------|-------------|
| `id` | `ID!` | primary_key | Unique identifier |
| `jobNumber` | `String` | display | Job number |
| `title` | `String` | display | Job title |
| `jobStatus` | `String` | state | Job status |
| `total` | `Money` | financial | Total amount |
| `client` | `Client` | foreign_key | Client for job |
| `property` | `Property` | foreign_key | Related property |
| `createdAt` | `ISO8601DateTime!` | metadata | Creation timestamp |
| `updatedAt` | `ISO8601DateTime!` | metadata | Last update timestamp |

#### Relationships
- **belongs_to** `client` (FK: `client_id`)
- **belongs_to** `property` (FK: `property_id`)
- **has_many** `visit`
- **has_many** `note`
- **has_one** `invoice`

---

### Visit

**GraphQL Type**: `Visit`
**Primary Key**: `id`
**Description**: Scheduled service visits

#### Fields

| Field Name | Type | Role | Description |
|-----------|------|------|-------------|
| `id` | `ID!` | primary_key | Unique identifier |
| `title` | `String` | display | Visit title |
| `visitStatus` | `String` | state | Visit status |
| `startAt` | `ISO8601DateTime` | schedule | Start time |
| `endAt` | `ISO8601DateTime` | schedule | End time |
| `job` | `Job` | foreign_key | Parent job |
| `createdAt` | `ISO8601DateTime!` | metadata | Creation timestamp |
| `updatedAt` | `ISO8601DateTime!` | metadata | Last update timestamp |

#### Relationships
- **belongs_to** `job` (FK: `job_id`)
- **has_many** `note`

---

### Invoice

**GraphQL Type**: `Invoice`
**Primary Key**: `id`
**Description**: Billing invoices

#### Fields

| Field Name | Type | Role | Description |
|-----------|------|------|-------------|
| `id` | `ID!` | primary_key | Unique identifier |
| `invoiceNumber` | `String` | display | Invoice number |
| `total` | `Money` | financial | Total amount |
| `subtotal` | `Money` | financial | Subtotal before tax |
| `status` | `String` | state | Invoice status |
| `issuedAt` | `ISO8601DateTime` | metadata | Issue date |
| `dueDate` | `ISO8601DateTime` | schedule | Payment due date |
| `client` | `Client` | foreign_key | Client for invoice |
| `job` | `Job` | foreign_key | Related job |
| `createdAt` | `ISO8601DateTime!` | metadata | Creation timestamp |
| `updatedAt` | `ISO8601DateTime!` | metadata | Last update timestamp |

#### Relationships
- **belongs_to** `client` (FK: `client_id`)
- **belongs_to** `job` (FK: `job_id`)
- **has_many** `note`

---

### Note (Polymorphic)

**GraphQL Type**: Polymorphic - `ClientNote`, `JobNote`, `PropertyNote`, `QuoteNote`, `InvoiceNote`, `RequestNote`, `VisitNote`
**Primary Key**: `id`
**Description**: Polymorphic notes attached to various entities

#### Fields

| Field Name | Type | Role | Description |
|-----------|------|------|-------------|
| `id` | `ID!` | primary_key | Unique identifier |
| `message` | `String!` | display | Note content text |
| `createdAt` | `ISO8601DateTime!` | metadata | Creation timestamp |
| `updatedAt` | `ISO8601DateTime!` | metadata | Last update timestamp |

#### Polymorphic Pattern

Notes use a polymorphic pattern in Jobber's GraphQL schema. Each note type (`ClientNote`, `JobNote`, etc.) has a parent field pointing to the owning entity.

**Example GraphQL Fragment**:
```graphql
... on ClientNote {
  id
  message
  client { id }
  createdAt
  updatedAt
}
... on JobNote {
  id
  message
  job { id }
  createdAt
  updatedAt
}
```

**Tightbeam Normalization**:
We normalize polymorphic notes to:
- `entity_type`: Discriminator field ('client', 'job', 'property', etc.)
- `entity_id`: Foreign key ID referencing the parent entity

---

### Attachment

**GraphQL Type**: `NoteAttachment`
**Primary Key**: `id`
**Description**: File attachments linked to notes

#### Fields

| Field Name | Type | Role | Description |
|-----------|------|------|-------------|
| `id` | `ID!` | primary_key | Unique identifier |
| `note` | `Note` | foreign_key | Parent note |
| `fileName` | `String!` | display | Original filename |
| `contentType` | `String` | metadata | MIME type |
| `fileSize` | `Int` | metadata | Size in bytes |
| `url` | `String!` | metadata | Remote download URL |
| `createdAt` | `ISO8601DateTime!` | metadata | Creation timestamp |

#### Relationships
- **belongs_to** `note` (FK: `note_id`)

#### Tightbeam Extensions
- **local_file_path**: Added field for download tracking
- **Storage pattern**: `./attachments/{note_id}/{filename}`
- **⚠️ URL Expiry**: Attachment URLs are temporary - download within 24 hours

---

### Other Entities (Summary)

#### Expense
- **Primary Key**: `id`
- **Key Fields**: `description`, `amount`, `expenseDate`, `createdAt`

#### User
- **Primary Key**: `id`
- **Key Fields**: `name`, `email`, `createdAt`

#### ProductOrService
- **Primary Key**: `id`
- **Key Fields**: `name`, `description`, `unitCost`, `createdAt`

#### TaxRate
- **Primary Key**: `id`
- **Key Fields**: `name`, `rate`, `createdAt`

#### TimesheetEntry
- **Primary Key**: `id`
- **Key Fields**: `description`, `startAt`, `endAt`, `job`, `user`, `createdAt`
- **Relationships**: belongs_to `job`, belongs_to `user`

---

## GraphQL Query Patterns

### Cursor-Based Pagination (Relay)

All collection queries use Relay-style cursor pagination:

```graphql
query GetClients($cursor: String) {
  clients(first: 50, after: $cursor) {
    edges {
      node {
        id
        firstName
        lastName
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

**Required Parameters**:
- `first: Int` - Number of items to fetch
- `after: String` - Cursor for next page

**Response Fields**:
- `edges { node { ... } }` - Array of results
- `pageInfo { hasNextPage, endCursor }` - Pagination metadata

---

## Cost Optimization Rules

### Rule 1: Always Include `first: N`

**❌ BAD** (100× cost multiplier):
```graphql
clients {
  edges { node { id firstName } }
}
# Cost: 2 fields × 100 assumed nodes = 200 points
```

**✅ GOOD**:
```graphql
clients(first: 50) {
  edges { node { id firstName } }
}
# Cost: 2 fields × 50 nodes = 100 points
```

### Rule 2: Limit Nested Queries

**❌ BAD** (exponential cost):
```graphql
clients {  # Assume 100
  edges {
    node {
      notes {  # Assume 100 per client → 10,000 total
        edges { node { id } }
      }
    }
  }
}
# Cost: 10,000+ points
```

**✅ GOOD**:
```graphql
clients(first: 50) {
  edges {
    node {
      notes(first: 10) {  # Limit nested queries
        edges { node { id message } }
      }
    }
  }
}
# Cost: ~550 points (50 clients × 11 fields each)
```

### Rule 3: Avoid Deep Nesting

Maximum 2-3 levels of nesting. For deeper relationships, use multiple queries instead.

---

## Validation Rules

When implementing entity extraction, enforce these rules:

1. ✅ All entities MUST have `id` field
2. ✅ All entities MUST have `createdAt` timestamp
3. ✅ Foreign keys MUST reference valid entity IDs
4. ✅ Polymorphic notes MUST have `entity_type` discriminator
5. ⚠️ Attachment URLs are temporary - download within 24 hours
6. ✅ Use `INSERT OR REPLACE` for idempotent database operations
7. ✅ Commit transactions after each batch (page) of results

---

## Schema Updates

When Jobber updates their GraphQL schema:

1. **Do NOT** modify this manifest without verification
2. Run schema introspection query against live API
3. Compare results with this manifest
4. Update manifest + regenerate this documentation
5. Update corresponding Tightbeam models and mappers
6. Add migration script if schema breaking changes

---

## References

- **Jobber API Docs**: https://developer.getjobber.com/docs/
- **GraphQL Endpoint**: https://api.getjobber.com/api/graphql
- **API Version**: 2023-11-15
- **Tightbeam Models**: `src/models/`
- **GraphQL Queries**: `src/clients/jobber_client.py`
