# GraphQL Query Coverage Analysis

## Summary by Entity

| Entity | Available | Queried | Coverage | Missing |
|--------|-----------|---------|----------|----------|
| Client | 42 | 0 | 0.0% | 42 |
| Expense | 11 | 11 | 100.0% | 0 |
| Invoice | 35 | 0 | 0.0% | 35 |
| Job | 42 | 0 | 0.0% | 42 |
| ProductOrService | 16 | 12 | 75.0% | 4 |
| Property | 14 | 0 | 0.0% | 14 |
| Quote | 30 | 0 | 0.0% | 30 |
| Request | 23 | 0 | 0.0% | 23 |
| TimeSheetEntry | 18 | 0 | 0.0% | 18 |
| User | 21 | 10 | 47.6% | 11 |
| Visit | 30 | 5 | 16.7% | 25 |

## High-Value Missing Fields


### Client
- `balance`
- `companyName`
- `billingAddress`
- `isArchivable`

### Invoice
- `amounts`
- `dueDate`
- `invoiceNet`

### Quote
- `amounts`

### Job
- `billingType`
- `completedAt`
- `instructions`
- `invoicedTotal`

### Property
- `name`
- `taxRate`
- `isBillingAddress`
- `routingOrder`

### Visit
- `completedAt`
- `completedBy`
- `allDay`
- `clientConfirmed`

### User
- `availableForScheduling`
- `assignedColor`

## Potential Issues

Fields queried but not in schema (may indicate bugs or outdated queries):

