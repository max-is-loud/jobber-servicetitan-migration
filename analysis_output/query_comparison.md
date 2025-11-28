# GraphQL Query Comparison: Pagination vs Single Entity

## Issue Found: Query Inconsistency

The codebase has TWO different query types for each entity:
1. **Pagination Queries** - Used by `fetch_*()` methods (e.g., `TAX_RATES_QUERY`)
2. **Single Entity Queries** - Used in `ENTITY_BY_ID_QUERY` for individual fetching

**Problem:** These queries request DIFFERENT fields for the same entity types, leading to inconsistent data extraction.

---

## TaxRate Query Comparison

### TAX_RATES_QUERY (Pagination)
**Location:** `src/clients/jobber_client.py:708-724`
```graphql
query GetTaxRates($cursor: String) {
  taxRates(first: 100, after: $cursor) {
    edges {
      node {
        id
        name
        description
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

### ENTITY_BY_ID_QUERY ... on TaxRate (Single Entity)
**Location:** `src/clients/jobber_client.py:1227-1240`
```graphql
... on TaxRate {
  id
  name
  rate            # ← MISSING in pagination query
  region          # ← MISSING in pagination query
  compound        # ← MISSING in pagination query
  active          # ← MISSING in pagination query
  description
  taxNumber       # ← MISSING in pagination query
  displayOrder    # ← MISSING in pagination query
  defaultForRegion # ← MISSING in pagination query
  createdAt       # ← MISSING in pagination query
  updatedAt       # ← MISSING in pagination query
}
```

### Impact
When fetching tax rates via pagination (`fetch_tax_rates()`), the mapper will receive incomplete data with only 3 fields instead of 12. This means:
- `rate` will always be 0
- `region` will always be empty
- `compound` will always be false
- `active` will always be true (default)
- `taxNumber` will always be empty
- `displayOrder` will always be 0
- `defaultForRegion` will always be false
- `createdAt` will always be empty
- `updatedAt` will always be empty

Only when fetching a single tax rate by ID will all fields be populated correctly.

---

## Recommendation

**SOLUTION:** Update `TAX_RATES_QUERY` to match the fields in `ENTITY_BY_ID_QUERY`:

```graphql
TAX_RATES_QUERY = """
    query GetTaxRates($cursor: String) {
      taxRates(first: 100, after: $cursor) {
        edges {
          node {
            id
            name
            rate
            region
            compound
            active
            description
            taxNumber
            displayOrder
            defaultForRegion
            createdAt
            updatedAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """
```

This ensures consistent data extraction regardless of how the tax rate was fetched.
