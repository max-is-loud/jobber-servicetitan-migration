# Detailed Field-by-Field Comparison

This document provides exact line numbers and code snippets for each mismatch found.

---

## 🔴 CRITICAL ISSUE #1: TaxRate

### GraphQL Query (TAX_RATES_QUERY)
**File:** `src/clients/jobber_client.py`
**Lines:** 708-724

```graphql
TAX_RATES_QUERY = """
    query GetTaxRates($cursor: String) {
      taxRates(first: 100, after: $cursor) {
        edges {
          node {
            id              # ✅ Mapped
            name            # ✅ Mapped
            description     # ✅ Mapped
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

### Mapper Expectations
**File:** `src/mappers/entity_mapper.py`
**Lines:** 1103-1160

```python
def map_tax_rate(self, data: dict[str, Any]) -> TaxRate:
    tax_rate_id = data.get("id")           # ✅ Available in query
    name = data.get("name", "")            # ✅ Available in query
    rate = data.get("rate", 0)             # ❌ NOT in query - will be 0
    rate_percentage = str(rate)

    region = data.get("region", "")        # ❌ NOT in query - will be ""
    compound = str(data.get("compound", False)).lower()  # ❌ NOT in query - will be "false"
    active = str(data.get("active", True)).lower()       # ❌ NOT in query - will be "true"
    description = data.get("description", "")            # ✅ Available in query
    tax_number = data.get("taxNumber", "")               # ❌ NOT in query - will be ""

    display_order = data.get("displayOrder", 0)          # ❌ NOT in query - will be 0
    default_for_region = str(data.get("defaultForRegion", False)).lower()  # ❌ NOT in query

    created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))    # ❌ NOT in query
    updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))    # ❌ NOT in query
```

### Fix Required
Add missing fields to `TAX_RATES_QUERY`:
```graphql
TAX_RATES_QUERY = """
    query GetTaxRates($cursor: String) {
      taxRates(first: 100, after: $cursor) {
        edges {
          node {
            id
            name
            rate              # ADD THIS
            region            # ADD THIS
            compound          # ADD THIS
            active            # ADD THIS
            description
            taxNumber         # ADD THIS
            displayOrder      # ADD THIS
            defaultForRegion  # ADD THIS
            createdAt         # ADD THIS
            updatedAt         # ADD THIS
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

---

## 🔴 CRITICAL ISSUE #2: ProductService - Category Field

### GraphQL Query (PRODUCTS_SERVICES_QUERY)
**File:** `src/clients/jobber_client.py`
**Lines:** 680-705

```graphql
PRODUCTS_SERVICES_QUERY = """
    query GetProductsServices($cursor: String) {
      productOrServices(first: 100, after: $cursor) {
        edges {
          node {
            id
            name
            description
            category          # ← Returns SCALAR string, not object
            defaultUnitCost
            ...
```

### Mapper Bug
**File:** `src/mappers/entity_mapper.py`
**Lines:** 1045-1047

```python
# Extract category
category_obj = data.get("category", {})  # ❌ BUG: Treats scalar as object
category = MapperUtils.safe_get_nested(category_obj, "name", default="")
```

### What Happens
1. GraphQL returns: `{"category": "Landscaping"}`
2. Mapper expects: `{"category": {"name": "Landscaping"}}`
3. Result: `category` is always empty string

### Fix Required
```python
# Extract category (scalar field, not object)
category = data.get("category", "")  # FIX: Treat as scalar
```

---

## 🔴 CRITICAL ISSUE #3: ProductService - Field Name Mismatch

### GraphQL Query (PRODUCTS_SERVICES_QUERY)
**File:** `src/clients/jobber_client.py`
**Line:** 695

```graphql
onlineBookingsEnabled    # ← Note the plural "Bookings"
```

### Mapper Bug
**File:** `src/mappers/entity_mapper.py`
**Line:** 1067

```python
online_booking_enabled = str(data.get("onlineBookingEnabled", False)).lower()
#                                       ^^^^^^^^^^^^^^^^^^^
#                                       WRONG: Missing 's' in "Bookings"
```

### Fix Required
```python
online_booking_enabled = str(data.get("onlineBookingsEnabled", False)).lower()
#                                       ^^^^^^^^^^^^^^^^^^^^
#                                       CORRECT: With 's'
```

---

## 🔴 CRITICAL ISSUE #4: Visit - completedBy Type Mismatch

### GraphQL Query (VISITS_QUERY)
**File:** `src/clients/jobber_client.py`
**Line:** 624

```graphql
completedBy    # ← Returns SCALAR (user ID string or null)
```

### Mapper Bug
**File:** `src/mappers/entity_mapper.py`
**Line:** 910

```python
# Extract completed by user ID
completed_by_id = MapperUtils.extract_id_from_relationship(data.get("completedBy"))
#                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                 BUG: Expects object like {"id": "123"}, but gets scalar "123"
```

### What Happens
1. GraphQL returns: `{"completedBy": "user_123"}` or `{"completedBy": null}`
2. Mapper calls: `extract_id_from_relationship("user_123")`
3. `extract_id_from_relationship` expects dict, gets string
4. Result: Returns empty string instead of "user_123"

### Fix Required
```python
# Extract completed by user ID (scalar field)
completed_by_data = data.get("completedBy")
if isinstance(completed_by_data, str):
    completed_by_id = completed_by_data
else:
    # Fallback for relationship object format (if API changes)
    completed_by_id = MapperUtils.extract_id_from_relationship(completed_by_data)
```

---

## 🔴 CRITICAL ISSUE #5: Visit - Missing updatedAt

### GraphQL Query (VISITS_QUERY)
**File:** `src/clients/jobber_client.py`
**Lines:** 593-634

```graphql
# Note: Field 'updatedAt' is NOT PRESENT in this query
# According to comment on line 592: "updatedAt field does not exist on Visit type"
```

### Mapper Expectation
**File:** `src/mappers/entity_mapper.py`
**Line:** 917

```python
updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))
# ❌ Will always be empty string - field not in query
```

### Fix Required
Either:
1. **If field exists in API:** Add to query
2. **If field doesn't exist:** Remove from mapper (current comment suggests it doesn't exist)

```python
# Option 2: Remove the line since Visit doesn't have updatedAt
# updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))  # REMOVE
```

---

## ⚠️ MEDIUM ISSUE #1: Request - Unused Fields

### GraphQL Query (_get_requests_query)
**File:** `src/clients/jobber_client.py`
**Lines:** 467-471

```graphql
companyName     # ← Queried but not used
contactName     # ← Queried but not used
email           # ← Queried but not used
phone           # ← Queried but not used
```

### Mapper Behavior
**File:** `src/mappers/entity_mapper.py`
**Lines:** 679-682

```python
# Additional contact fields from API
company_name = data.get("companyName", "")     # ← Extracted
contact_name = data.get("contactName", "")     # ← Extracted
email = data.get("email", "")                  # ← Extracted
phone = data.get("phone", "")                  # ← Extracted

# ... but then NEVER USED in Request() constructor
```

### Request Model
**File:** `src/models/request.py`
**Lines:** 6-31

```python
@dataclass(frozen=True)
class Request:
    id: str
    client_id: str
    property_id: str
    title: str
    description: str
    status: str
    priority: str
    source: str
    assigned_to: str
    converted_to_quote_id: str
    converted_to_job_id: str
    created_at: str
    updated_at: str
    # ❌ NO FIELDS FOR: company_name, contact_name, email, phone
```

### Fix Required
**Option 1:** Add fields to model (recommended)
```python
@dataclass(frozen=True)
class Request:
    # ... existing fields ...
    company_name: str = ""    # ADD
    contact_name: str = ""    # ADD
    email: str = ""           # ADD
    phone: str = ""           # ADD
```

**Option 2:** Remove from query (if not needed)
```python
# In mapper, remove lines 679-682
# In query, remove lines 467-471
```

---

## ⚠️ MEDIUM ISSUE #2: Expense - Unused Relationship Fields

### GraphQL Query (EXPENSES_QUERY)
**File:** `src/clients/jobber_client.py`
**Lines:** 570-578

```graphql
enteredBy {       # ← Queried but not used
  id
}
paidBy {          # ← Queried but not used
  id
}
reimbursableTo {  # ← Queried but not used
  id
}
```

### Mapper Behavior
**File:** `src/mappers/entity_mapper.py`
**Lines:** 792-852

```python
def map_expense(self, data: dict[str, Any]) -> Expense:
    # ... extracts job_id, title, description, total, date ...
    # ❌ NEVER extracts enteredBy, paidBy, reimbursableTo
```

### Fix Required
**Option 1:** Add to Expense model and mapper
```python
# In mapper:
entered_by_id = MapperUtils.extract_id_from_relationship(data.get("enteredBy"))
paid_by_id = MapperUtils.extract_id_from_relationship(data.get("paidBy"))
reimbursable_to_id = MapperUtils.extract_id_from_relationship(data.get("reimbursableTo"))

# In model (src/models/expense.py):
@dataclass(frozen=True)
class Expense:
    # ... existing fields ...
    entered_by_id: str = ""      # ADD
    paid_by_id: str = ""         # ADD
    reimbursable_to_id: str = "" # ADD
```

**Option 2:** Remove from query
```python
# Remove lines 570-578 from EXPENSES_QUERY
```

---

## Summary Table

| Issue | Entity | Type | Severity | Lines (Query) | Lines (Mapper) | Fix Type |
|-------|--------|------|----------|---------------|----------------|----------|
| #1 | TaxRate | Missing fields | 🔴 Critical | 708-724 | 1103-1160 | Add to query |
| #2 | ProductService | Type mismatch | 🔴 Critical | 688 | 1046-1047 | Fix mapper |
| #3 | ProductService | Name mismatch | 🔴 Critical | 695 | 1067 | Fix mapper |
| #4 | Visit | Type mismatch | 🔴 Critical | 624 | 910 | Fix mapper |
| #5 | Visit | Missing field | 🔴 Critical | N/A | 917 | Remove from mapper |
| #6 | Request | Unused fields | ⚠️ Medium | 467-471 | 679-682 | Add to model or remove query |
| #7 | Expense | Unused fields | ⚠️ Medium | 570-578 | N/A | Add to mapper/model or remove query |

---

## Testing Each Fix

### Test TaxRate Fix
```python
# After fixing TAX_RATES_QUERY, verify:
tax_rate = client.fetch_tax_rates()
assert tax_rate.rate_percentage != "0"  # Should have actual rate
assert tax_rate.region != ""            # Should have region
assert tax_rate.created_at != ""        # Should have timestamp
```

### Test ProductService Fixes
```python
# After fixing category and field name:
product = client.fetch_products_services()
assert product.category != ""                    # Should have category name
assert product.online_booking_enabled in ["true", "false"]  # Should have value
```

### Test Visit Fix
```python
# After fixing completedBy:
visit = client.fetch_visits()
if visit.completed_at:  # If completed
    assert visit.completed_by_id != ""  # Should have user ID
```

---

## Validation Script

```python
#!/usr/bin/env python3
"""Validate that all GraphQL query fields are properly mapped."""

import re
from pathlib import Path

def extract_query_fields(query_str: str) -> set[str]:
    """Extract field names from GraphQL query."""
    # Simple regex to find field names (excludes nested objects)
    fields = re.findall(r'^\s*(\w+)\s*(?:\(|{)?', query_str, re.MULTILINE)
    return set(f for f in fields if not f.startswith('query'))

def extract_mapper_accesses(mapper_code: str) -> set[str]:
    """Extract field accesses from mapper code."""
    # Find all data.get("fieldName") calls
    accesses = re.findall(r'data\.get\(["\'](\w+)["\']', mapper_code)
    return set(accesses)

# Use this to validate each entity
```
