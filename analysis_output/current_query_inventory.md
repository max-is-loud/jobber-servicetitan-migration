# Current GraphQL Query Field Inventory

This document lists the fields currently queried for each entity based on manual analysis of `src/clients/jobber_client.py`.

## Summary

| Entity | Available Fields | Currently Queried | Coverage % |
|--------|------------------|-------------------|------------|
| Client | 42 | ~7 | ~17% |
| Invoice | 35 | ~15 | ~43% |
| Quote | 30 | ~12 | ~40% |
| Job | 42 | ~12 | ~29% |
| Property | 14 | ~5 | ~36% |
| Request | 23 | ~10 | ~43% |
| Visit | 30 | ~10 | ~33% |
| User | 21 | ~6 | ~29% |
| Expense | 11 | ~8 | ~73% |
| TimeSheetEntry | 18 | ~10 | ~56% |
| ProductOrService | 16 | ~8 | ~50% |

## Entity Details

### Client (Currently Queried: ~7 fields)

**Queried:**
- id
- firstName
- lastName
- emails { address }
- phones { number }
- notes { id } (nested with pagination)
- noteAttachments { id, fileName, contentType, url, fileSize, createdAt }
- createdAt
- updatedAt

**Missing High-Value Fields:**
- `balance` - Outstanding balance (Float!)
- `companyName` - Company name for business clients
- `billingAddress` - ClientAddress object
- `isArchivable` - Archive status
- `isCompany` - Company vs individual flag
- `isLead` - Lead status

### Invoice (Currently Queried: ~15 fields)

**Queried:**
- id
- invoiceNumber
- invoiceStatus (note: schema uses `invoiceStatus`, not `status`)
- subject
- message
- issuedDate
- dueDate
- client { id }
- jobs { id }
- lineItems { ... }
- notes { id } (deferred loading)
- noteAttachments { ... }
- createdAt
- updatedAt

**Missing High-Value Fields:**
- `amounts` - InvoiceAmounts object (total, subtotal, tax, discount, deposits)
- `invoiceNet` - Net amount (Int)
- `taxRate` { id, name, rate }
- `properties` { id }
- `paymentRecords` { ... }

### Quote (Currently Queried: ~12 fields)

**Queried:**
- id
- quoteNumber
- quoteStatus (schema field name)
- title
- message
- client { id }
- jobs { id }
- property { id }
- lineItems { ... }
- notes { id }
- createdAt
- updatedAt

**Missing High-Value Fields:**
- `amounts` - QuoteAmounts object (total, subtotal, tax, discount)
- `sentAt` - When quote was sent
- `taxDetails` { ... }
- `request` { id } - Link to originating request
- `salesperson` { id }

### Job (Currently Queried: ~12 fields)

**Queried:**
- id
- jobNumber
- jobStatus
- jobType
- title
- client { id }
- property { id }
- lineItems { ... }
- notes { id }
- visits { id }
- createdAt
- updatedAt

**Missing High-Value Fields:**
- `billingType` - BillingStrategy enum
- `completedAt` - Completion timestamp
- `instructions` - Job instructions text
- `invoicedTotal` - Amount invoiced (Float!)
- `arrivalWindow` { ... }
- `quote` { id }
- `request` { id }
- `salesperson` { id }

### Property (Currently Queried: ~5 fields)

**Queried:**
- id
- address { street, city, province, postalCode, country }
- client { id }
- createdAt (likely)
- updatedAt (likely)

**Missing High-Value Fields:**
- `name` - Property name/identifier
- `taxRate` { id, name, rate }
- `isBillingAddress` - Billing address flag
- `routingOrder` - Service routing order (Int)
- `customFields`

### Request (Currently Queried: ~10 fields)

**Queried:**
- id
- title
- requestStatus (note: schema field is `requestStatus`, not `status`)
- client { id }
- property { id }
- jobs { id }
- quotes { id }
- notes { id }
- createdAt
- updatedAt

**Missing Fields:**
- `source` - Request source
- `arrivalWindow` { ... }
- `assessment` { ... }
- `lineItems` { ... }
- `isScheduled`
- `referringClient` { id }

### Visit (Currently Queried: ~10 fields)

**Queried:**
- id
- title
- visitStatus
- startAt
- endAt
- client { id }
- job { id }
- property { id }
- createdAt
- updatedAt

**Missing High-Value Fields:**
- `completedAt` - Completion timestamp
- `completedBy` - Who completed the visit
- `allDay` - All-day event flag
- `clientConfirmed` - Client confirmation status
- `arrivalWindow` { ... }
- `assignedUsers` { id, name }
- `invoice` { id }

### User (Currently Queried: ~6 fields)

**Queried:**
- id
- name { first, last }
- email { raw }
- phone { raw }
- createdAt
- updatedAt

**Missing High-Value Fields:**
- `isAccountAdmin` - Admin privileges
- `isAccountOwner` - Owner privileges
- `availableForScheduling` - Scheduling availability
- `assignedColor` - Calendar color
- `status` - User status enum

### Expense (Currently Queried: ~8 fields)

**Queried:**
- id
- title
- description
- total
- date
- linkedJob { id }
- enteredBy { id }
- createdAt
- updatedAt

**Coverage: Good (~73%)**

### TimeSheetEntry (Currently Queried: ~10 fields)

**Queried:**
- id
- startAt
- endAt
- finalDuration
- approved
- user { id }
- job { id }
- visit { id }
- createdAt
- updatedAt

**Coverage: Good (~56%)**

### ProductOrService (Currently Queried: ~8 fields)

**Queried:**
- id
- name
- description
- defaultUnitCost
- taxable
- visible
- createdAt (likely)
- updatedAt (likely)

**Missing Fields:**
- `internalUnitCost`
- `markup`
- `durationMinutes`
- `category` { ... }

## Priority Missing Fields Summary

### Priority 1: Critical Business Data
1. **Client.balance** - Outstanding balance tracking
2. **Client.companyName** - Business client identification
3. **Client.billingAddress** - Billing information
4. **Invoice.amounts** - Structured financial data
5. **Quote.amounts** - Structured financial data
6. **Job.billingType** - Billing strategy
7. **Job.completedAt** - Completion tracking
8. **Job.invoicedTotal** - Financial tracking

### Priority 2: Important Metadata
1. **Client.isArchivable** - Archive status
2. **Job.instructions** - Job context
3. **Property.name** - Property identification
4. **Property.taxRate** - Tax relationships
5. **Visit.completedAt** - Completion tracking
6. **Visit.clientConfirmed** - Confirmation status
7. **User.isAccountAdmin** - Admin privileges
8. **User.isAccountOwner** - Owner privileges

### Priority 3: Enhanced Features
1. **Visit.completedBy** - Who completed work
2. **Visit.allDay** - All-day scheduling
3. **Property.routingOrder** - Service routing
4. **User.availableForScheduling** - Scheduling metadata
5. **User.assignedColor** - UI customization

## Notes

- Field names like `invoiceStatus` and `requestStatus` use the full prefix, not just `status`
- Most financial fields should be stored as cents (multiply by 100)
- Complex objects like `amounts`, `billingAddress`, `arrivalWindow` need special handling (flatten or JSON)
- All timestamps are ISO8601DateTime format
- Connection fields (notes, noteAttachments, jobs, etc.) use deferred loading pattern for cost optimization
