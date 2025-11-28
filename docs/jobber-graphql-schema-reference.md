# Jobber GraphQL Schema Reference

This document provides the authoritative schema reference for Jobber's GraphQL API types used in tightbeam. All information was obtained via GraphQL introspection on **2025-01-26** and represents the current production schema.

## Table of Contents

- [User Types](#user-types)
- [Property Types](#property-types)
- [Line Item Types](#line-item-types)
- [Union Types](#union-types)
- [Entity Types](#entity-types)

---

## User Types

### UserEmail

**Kind:** OBJECT
**Fields:**
- `isValid: Boolean!` - Whether the email address is valid
- `raw: String!` - The raw email address string

**Usage:**
```graphql
user {
  email {
    raw        # Use 'raw', not 'email'!
    isValid
  }
}
```

**Common Mistake:** ❌ Querying `email { email }` - the field is called `raw`

---

### UserPhone

**Kind:** OBJECT
**Fields:**
- `areaCode: String` - Area code portion
- `countryCode: String` - Country code prefix
- `friendly: String` - Formatted display version
- `isValid: Boolean!` - Whether the phone number is valid
- `raw: String!` - The raw phone number string

**Usage:**
```graphql
user {
  phone {
    raw          # Use 'raw', not 'number'!
    friendly     # Human-readable format
    countryCode
    areaCode
    isValid
  }
}
```

**Common Mistake:** ❌ Querying `phone { number }` - the field is called `raw`

---

### Timezone

**Kind:** SCALAR
**Fields:** None (scalar type)

**Usage:**
```graphql
user {
  timezone     # Query directly as scalar, no selections
}
```

**Common Mistake:** ❌ Querying `timezone { identifier }` - it's a scalar, not an object

---

## Property Types

### PropertyAddress

**Kind:** OBJECT
**Fields:**
- `city: String`
- `coordinates: Coordinates` - Nested object with lat/lng
- `country: String`
- `geoStatus: String` - Geocoding status
- `id: ID`
- `name: String`
- `postalCode: String`
- `province: String`
- `street: String` - Full street address
- `street1: String` - First line of street address
- `street2: String` - Second line (unit, apt, etc.)

**Usage:**
```graphql
property {
  address {
    street       # Use 'street', not 'line1'!
    street1      # First line
    street2      # Second line
    city
    province
    postalCode
    country
    coordinates {
      latitude
      longitude
    }
  }
}
```

**Common Mistake:** ❌ Querying `address { line1, line2 }` - use `street`, `street1`, `street2`

---

### Property

**Kind:** OBJECT
**Total Fields:** 14

**Important Notes:**
- ✅ HAS `name` field (property name/title)
- ❌ DOES NOT have `coordinates` field (coordinates are on `address.coordinates`)
- ❌ DOES NOT have `createdAt` field
- ❌ DOES NOT have `updatedAt` field

**Usage:**
```graphql
property {
  id
  name                    # Property name
  client { id }
  address {
    coordinates {         # Coordinates are here, not on Property!
      latitude
      longitude
    }
  }
}
```

---

## Line Item Types

### QuoteLineItem

**Kind:** OBJECT
**Total Fields:** 18

**Pricing Fields:**
- ✅ `unitCost: Float` - Cost per unit
- ✅ `unitPrice: Float` - Price per unit
- ❌ `total: Float` - NOT AVAILABLE (must be calculated)

**Usage:**
```graphql
quote {
  lineItems {
    edges {
      node {
        name
        description
        qty
        unitCost      # Available
        unitPrice     # Available
        # total is NOT available - calculate as qty * unitPrice
      }
    }
  }
}
```

---

### InvoiceLineItem

**Kind:** OBJECT
**Total Fields:** 15

**Pricing Fields:**
- ❌ `unitCost: Float` - NOT AVAILABLE on invoices
- ✅ `unitPrice: Float` - Price per unit
- ❌ `total: Float` - NOT AVAILABLE (must be calculated)

**Usage:**
```graphql
invoice {
  lineItems {
    edges {
      node {
        description
        quantity
        unitPrice     # Available (note: 'unitPrice' not 'unitCost')
        # total is NOT available - calculate as quantity * unitPrice
      }
    }
  }
}
```

**Important Difference:** QuoteLineItem has both `unitCost` and `unitPrice`, but InvoiceLineItem only has `unitPrice`.

---

## Union Types

### RequestNoteUnion

**Kind:** UNION
**Possible Types:**
- `ClientNote`
- `RequestNote`

**Usage:**
```graphql
request {
  notes {
    edges {
      node {
        ... on ClientNote {
          id
          message
          createdAt
          client { id }
        }
        ... on RequestNote {
          id
          message
          createdAt
          request { id }
        }
      }
    }
  }
}
```

---

### QuoteNoteUnion

**Kind:** UNION
**Possible Types:**
- `ClientNote`
- `QuoteNote`
- `RequestNote`

**Usage:**
```graphql
quote {
  notes {
    edges {
      node {
        ... on ClientNote {
          id
          message
          createdAt
        }
        ... on QuoteNote {
          id
          message
          createdAt
        }
        ... on RequestNote {
          id
          message
          createdAt
        }
      }
    }
  }
}
```

---

### JobNoteUnion

**Kind:** UNION
**Possible Types:**
- `ClientNote`
- `JobNote`
- `QuoteNote`
- `RequestNote`

**Usage:**
```graphql
job {
  notes {
    edges {
      node {
        ... on ClientNote {
          id
          message
          createdAt
        }
        ... on JobNote {
          id
          message
          createdAt
        }
        ... on QuoteNote {
          id
          message
          createdAt
        }
        ... on RequestNote {
          id
          message
          createdAt
        }
      }
    }
  }
}
```

---

### InvoiceNoteUnion

**Kind:** UNION
**Possible Types:**
- `ClientNote`
- `InvoiceNote`
- `JobNote`
- `QuoteNote`
- `RequestNote`

**Usage:**
```graphql
invoice {
  notes {
    edges {
      node {
        ... on ClientNote {
          id
          message
          createdAt
        }
        ... on InvoiceNote {
          id
          message
          createdAt
        }
        ... on JobNote {
          id
          message
          createdAt
        }
        ... on QuoteNote {
          id
          message
          createdAt
        }
        ... on RequestNote {
          id
          message
          createdAt
        }
      }
    }
  }
}
```

---

## Entity Types Summary

### Visit

**Total Fields:** 30

**Timestamp Fields:**
- ✅ `createdAt: ISO8601DateTime!`
- ✅ `completedAt: ISO8601DateTime`
- ✅ `startAt: ISO8601DateTime`
- ✅ `endAt: ISO8601DateTime`
- ❌ `updatedAt` - NOT AVAILABLE

---

### Client

**Total Fields:** 42

**Contact Fields:**
- `emails: [Email!]!` - Array of Email objects
  - Each Email has: `address`, `primary`, `description`, etc.
- `phones: [ClientPhoneNumber!]!` - Array of phone objects
  - Each ClientPhoneNumber has: `number`, `primary`, `description`, etc.

**Note:** Client uses different types (`Email`, `ClientPhoneNumber`) than User (`UserEmail`, `UserPhone`)

---

### User

**Total Fields:** 21

**Contact Fields:**
- `email: UserEmail!` - Single email object (not array)
  - Use `email { raw }` to get the email string
- `phone: UserPhone` - Single phone object (not array)
  - Use `phone { raw }` to get the phone string
- `timezone: Timezone` - SCALAR type
  - Query directly: `timezone` (not `timezone { identifier }`)

---

## Common Pitfalls

1. **UserEmail vs Email**: Different types with different field names
   - Client: `emails { address }`
   - User: `email { raw }`

2. **UserPhone vs ClientPhoneNumber**: Different types with different field names
   - Client: `phones { number }`
   - User: `phone { raw }`

3. **PropertyAddress fields**: Use `street`, `street1`, `street2` instead of `line1`, `line2`

4. **Property.coordinates**: DOES NOT exist. Use `address.coordinates` instead.

5. **Timezone is SCALAR**: Query directly, don't use selections

6. **LineItem pricing**:
   - QuoteLineItem: has both `unitCost` and `unitPrice`
   - InvoiceLineItem: only has `unitPrice` (no `unitCost`)
   - Neither has `total` field

7. **Union types**: Must use inline fragments for ALL possible types in the union

8. **Visit.updatedAt**: Does NOT exist

---

## Introspection Script

To regenerate this schema reference:

```bash
# Ensure you're authenticated first
uv run tightbeam oauth init

# Run the introspection script
uv run python scripts/introspect_jobber_schema.py

# Results saved to: introspection_results.json
```

---

## Last Updated

**Date:** 2025-01-26
**Method:** GraphQL Introspection
**Script:** `scripts/introspect_jobber_schema.py`
**Raw Data:** `introspection_results.json`

---

## References

- [Jobber Developer Docs](https://developer.getjobber.com/docs/)
- [GraphQL Introspection Spec](https://spec.graphql.org/October2021/#sec-Introspection)
