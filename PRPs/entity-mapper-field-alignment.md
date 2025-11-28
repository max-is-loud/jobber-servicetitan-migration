# Implementation Plan: Entity Mapper Field Alignment Fixes

## Overview
Fix all field mismatches between GraphQL queries and entity mappers to prevent data loss. Analysis revealed 5 critical issues causing data to be queried but not captured, resulting in incomplete database records.

## Problem Statement
Recent work refactored GraphQL queries to request all necessary fields from the Jobber API. However, entity mappers were not updated to match, causing:
- Query returns field `X`, mapper looks for field `Y` → data lost
- Query returns scalar, mapper expects object → data lost
- Query requests field, mapper never reads it → data ignored

## Research Findings

### Analysis Results (from codebase-analyst agent)
**Total entities analyzed:** 12
**Critical issues found:** 5
**Medium issues found:** 2
**Entities working correctly:** 7

### Critical Data Loss Scenarios

1. **TaxRate** - 75% data loss
   - Query: Requests only 3 fields (id, name, description)
   - Mapper: Expects 12 fields
   - Result: 9 fields always empty

2. **ProductService** - Category and booking data loss
   - Category: Mapper expects object `{name: string}`, API returns scalar string
   - Booking: Mapper reads `onlineBookingEnabled`, API returns `onlineBookingsEnabled`

3. **Visit** - Assignment tracking lost
   - completedBy: Mapper expects object, API returns scalar string
   - updatedAt: Mapper expects field that doesn't exist in API

4. **Request** - Contact information discarded
   - Query requests 4 contact fields, but Request model has no place to store them

5. **Expense** - Financial tracking metadata lost
   - Query requests 3 tracking fields, mapper never uses them

### Affected Files
- **Queries:** `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py`
- **Mappers:** `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py`
- **Models:** `/home/max/projects/tightbeam-v2/src/models/*.py`

### Analysis Documentation
Comprehensive analysis available in `/home/max/projects/tightbeam-v2/analysis_output/`:
- `field_mismatch_analysis.md` - Detailed per-entity breakdown
- `DETAILED_FIELD_COMPARISON.md` - Code-level fixes with examples
- `EXECUTIVE_SUMMARY.md` - High-level overview

## Implementation Tasks

### Phase 1: Critical TaxRate Fixes (Priority: Urgent)

#### Task 1.1: Expand TAX_RATES_QUERY
**File:** `src/clients/jobber_client.py` (lines 688-705)
**Description:** Add 9 missing fields to TAX_RATES_QUERY to match what mapper expects

**Change from:**
```graphql
query GetTaxRates($cursor: String) {
  taxRates(first: {size}, after: $cursor) {
    edges {
      node {
        id
        name
        description
      }
    }
  }
}
```

**Change to:**
```graphql
query GetTaxRates($cursor: String) {
  taxRates(first: {size}, after: $cursor) {
    edges {
      node {
        id
        name
        description
        rate
        region
        compound
        active
        taxNumber
        displayOrder
        defaultForRegion
        createdAt
        updatedAt
      }
    }
  }
}
```

**Impact:** Fixes 75% data loss for tax rates
**Estimated effort:** 10 minutes

---

### Phase 2: ProductService Critical Fixes (Priority: Urgent)

#### Task 2.1: Fix Category Type Mismatch
**File:** `src/mappers/entity_mapper.py` (lines 1046-1047)
**Description:** Handle category as scalar string instead of object

**Change from:**
```python
category_obj = data.get("category", {})
category = category_obj.get("name", "") if isinstance(category_obj, dict) else ""
```

**Change to:**
```python
category = data.get("category", "")
if isinstance(category, dict):
    category = category.get("name", "")
```

**Impact:** Fixes empty category field for all products/services
**Estimated effort:** 5 minutes

#### Task 2.2: Fix onlineBookingsEnabled Field Name
**File:** `src/mappers/entity_mapper.py` (line 1067)
**Description:** Add missing 's' to match API field name

**Change from:**
```python
online_booking_enabled = 1 if data.get("onlineBookingEnabled") else 0
```

**Change to:**
```python
online_booking_enabled = 1 if data.get("onlineBookingsEnabled") else 0
```

**Impact:** Fixes online booking flag always being false
**Estimated effort:** 2 minutes

---

### Phase 3: Visit Mapper Fixes (Priority: High)

#### Task 3.1: Fix completedBy Scalar Handling
**File:** `src/mappers/entity_mapper.py` (line 910)
**Description:** Handle completedBy as scalar string, not relationship object

**Change from:**
```python
completed_by_id = MapperUtils.extract_id_from_relationship(data.get("completedBy"))
```

**Change to:**
```python
completed_by = data.get("completedBy", "")
completed_by_id = completed_by if isinstance(completed_by, str) else ""
```

**Impact:** Fixes empty completedBy field for visits
**Estimated effort:** 5 minutes

#### Task 3.2: Remove Non-existent updatedAt Field
**File:** `src/mappers/entity_mapper.py` (line 917)
**Description:** Remove reference to field that doesn't exist in API

**Change from:**
```python
updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))
```

**Change to:**
```python
updated_at = None  # Field not available in Jobber Visit schema
```

**Impact:** Prevents confusion about missing field
**Estimated effort:** 2 minutes

---

### Phase 4: Request Model Enhancement (Priority: Medium)

#### Task 4.1: Add Contact Fields to Request Model
**File:** `src/models/request.py`
**Description:** Add fields to store contact information that's being queried

**Add to Request dataclass:**
```python
company_name: str = ""
contact_name: str = ""
email: str = ""
phone: str = ""
```

**Estimated effort:** 5 minutes

#### Task 4.2: Update Request Mapper to Capture Contact Fields
**File:** `src/mappers/entity_mapper.py` (map_request method)
**Description:** Map the contact fields that are already being queried

**Add to mapper:**
```python
company_name = data.get("companyName", "")
contact_name = data.get("contactName", "")
email = data.get("email", "")
phone = data.get("phone", "")
```

**Estimated effort:** 5 minutes

#### Task 4.3: Update Request Table Schema
**File:** Schema migration needed
**Description:** Add columns to requests table

**SQL:**
```sql
ALTER TABLE requests ADD COLUMN company_name TEXT DEFAULT '';
ALTER TABLE requests ADD COLUMN contact_name TEXT DEFAULT '';
ALTER TABLE requests ADD COLUMN email TEXT DEFAULT '';
ALTER TABLE requests ADD COLUMN phone TEXT DEFAULT '';
```

**Estimated effort:** 10 minutes

---

### Phase 5: Expense Model Enhancement (Priority: Medium)

#### Task 5.1: Add Tracking Fields to Expense Model
**File:** `src/models/expense.py`
**Description:** Add fields to store tracking metadata

**Add to Expense dataclass:**
```python
entered_by_id: str = ""
paid_by_id: str = ""
reimbursable_to_id: str = ""
```

**Estimated effort:** 5 minutes

#### Task 5.2: Update Expense Mapper to Capture Tracking Fields
**File:** `src/mappers/entity_mapper.py` (map_expense method)
**Description:** Map the tracking fields that are already being queried

**Add to mapper:**
```python
entered_by_id = MapperUtils.extract_id_from_relationship(data.get("enteredBy"))
paid_by_id = MapperUtils.extract_id_from_relationship(data.get("paidBy"))
reimbursable_to_id = MapperUtils.extract_id_from_relationship(data.get("reimbursableTo"))
```

**Estimated effort:** 5 minutes

#### Task 5.3: Update Expense Table Schema
**File:** Schema migration needed
**Description:** Add columns to expenses table

**SQL:**
```sql
ALTER TABLE expenses ADD COLUMN entered_by_id TEXT DEFAULT '';
ALTER TABLE expenses ADD COLUMN paid_by_id TEXT DEFAULT '';
ALTER TABLE expenses ADD COLUMN reimbursable_to_id TEXT DEFAULT '';
```

**Estimated effort:** 10 minutes

---

### Phase 6: Testing and Validation (Priority: High)

#### Task 6.1: Create Field Alignment Unit Tests
**File:** `tests/test_entity_mapper_field_alignment.py` (new file)
**Description:** Automated tests to prevent future mismatches

**Test coverage:**
- For each entity, verify every query field has a corresponding mapper read
- Test type mismatches (scalar vs object)
- Test field name exact matches

**Estimated effort:** 2 hours

#### Task 6.2: Integration Testing with Real Data
**Description:** Re-run max-extract for affected entities and verify data completeness

**Test entities:**
```bash
tightbeam migrate max-extract --entities tax_rates
tightbeam migrate max-extract --entities products_services
tightbeam migrate max-extract --entities visits
tightbeam migrate max-extract --entities requests
tightbeam migrate max-extract --entities expenses
```

**Validation:** Query database to confirm fields are populated
**Estimated effort:** 1 hour

#### Task 6.3: Data Backfill for Existing Records
**Description:** Re-extract entities that had data loss to populate missing fields

**Approach:**
1. Use `--resume` flag to skip re-extracting working entities
2. Extract only affected entities with fixed mappers
3. Validate data completeness before/after

**Estimated effort:** 2 hours (depending on data volume)

---

### Phase 7: Prevention and Documentation (Priority: Low)

#### Task 7.1: Create Query-Mapper Validation Script
**File:** `scripts/validate_query_mapper_alignment.py` (new file)
**Description:** Automated script to detect field mismatches

**Functionality:**
- Parse GraphQL queries to extract requested fields
- Parse mapper code to extract read fields
- Compare and report mismatches
- Run in CI to prevent regressions

**Estimated effort:** 4 hours

#### Task 7.2: Document Field Mapping Conventions
**File:** `docs/entity-mapping-guide.md` (new file)
**Description:** Developer guide for adding/modifying entities

**Content:**
- How to add a new entity
- GraphQL query → Mapper → Model field mapping workflow
- Common pitfalls (scalar vs object, field name case sensitivity)
- Testing checklist

**Estimated effort:** 1 hour

---

## Technical Design

### Data Flow
```
Jobber API (GraphQL)
    ↓ Returns field: "onlineBookingsEnabled"
JobberClient._get_products_services_query()
    ↓ Query requests: onlineBookingsEnabled
EntityMapper.map_product_service()
    ✗ Old: Reads data.get("onlineBookingEnabled")  // Missing 's' - always None
    ✓ New: Reads data.get("onlineBookingsEnabled")  // Correct match
ProductService dataclass
    ↓ Field: online_booking_enabled populated correctly
Repository.save_product_service()
    ↓ Saves to database
Database: products_services.online_booking_enabled = 1 ✓
```

### Field Naming Conventions

**GraphQL → Python Mapping:**
- GraphQL: `camelCase` → Python: `snake_case`
- Example: `onlineBookingsEnabled` → `online_booking_enabled`

**Common Mismatches:**
- Plural vs singular: `bookings` vs `booking`
- Nested objects: Query returns object, mapper expects scalar (or vice versa)
- Optional fields: Query may return null, mapper must handle gracefully

---

## Codebase Integration Points

### Files to Modify

1. **src/clients/jobber_client.py**
   - Line 688-705: Expand TAX_RATES_QUERY (Task 1.1)

2. **src/mappers/entity_mapper.py**
   - Line 910: Fix Visit completedBy handling (Task 3.1)
   - Line 917: Remove Visit updatedAt reference (Task 3.2)
   - Line 1046-1047: Fix ProductService category handling (Task 2.1)
   - Line 1067: Fix ProductService field name (Task 2.2)
   - Add Request contact field mapping (Task 4.2)
   - Add Expense tracking field mapping (Task 5.2)

3. **src/models/request.py**
   - Add 4 contact fields (Task 4.1)

4. **src/models/expense.py**
   - Add 3 tracking fields (Task 5.1)

### New Files to Create

1. **tests/test_entity_mapper_field_alignment.py**
   - Unit tests for field alignment (Task 6.1)

2. **scripts/validate_query_mapper_alignment.py**
   - Automated validation script (Task 7.1)

3. **docs/entity-mapping-guide.md**
   - Developer documentation (Task 7.2)

### Database Migrations

**Migration file needed:** `migrations/add_missing_entity_fields.sql`

```sql
-- Request contact fields
ALTER TABLE requests ADD COLUMN company_name TEXT DEFAULT '';
ALTER TABLE requests ADD COLUMN contact_name TEXT DEFAULT '';
ALTER TABLE requests ADD COLUMN email TEXT DEFAULT '';
ALTER TABLE requests ADD COLUMN phone TEXT DEFAULT '';

-- Expense tracking fields
ALTER TABLE expenses ADD COLUMN entered_by_id TEXT DEFAULT '';
ALTER TABLE expenses ADD COLUMN paid_by_id TEXT DEFAULT '';
ALTER TABLE expenses ADD COLUMN reimbursable_to_id TEXT DEFAULT '';
```

---

## Testing Strategy

### Unit Tests
- Test each mapper method with sample GraphQL response data
- Verify all queried fields are read by mapper
- Test type conversions (scalar/object handling)
- Test null/missing field handling

### Integration Tests
- Extract each affected entity type
- Query database to verify all expected fields are populated
- Compare before/after data completeness metrics

### Edge Cases
- Null values in API responses
- Empty strings vs null
- Nested objects that are null
- Fields that exist in some records but not others

---

## Success Criteria

### Phase 1-3 (Critical Fixes)
- [ ] TaxRate: All 12 fields populated for extracted records
- [ ] ProductService: category and online_booking_enabled populated correctly
- [ ] Visit: completedBy populated correctly, no errors about updatedAt

### Phase 4-5 (Data Completeness)
- [ ] Request: 4 new contact fields captured and stored
- [ ] Expense: 3 new tracking fields captured and stored

### Phase 6 (Quality Assurance)
- [ ] All unit tests passing
- [ ] Integration tests show 100% field coverage for all entities
- [ ] Data backfill completed for affected records

### Phase 7 (Prevention)
- [ ] Validation script integrated into CI pipeline
- [ ] Developer documentation published
- [ ] No new field mismatches detected in code review

---

## Implementation Timeline

### Week 1: Critical Fixes
- **Days 1-2:** Tasks 1.1, 2.1, 2.2, 3.1, 3.2 (all mapper fixes)
- **Day 3:** Task 6.2 (integration testing)
- **Day 4:** Task 6.3 (data backfill if needed)

### Week 2: Data Completeness
- **Days 1-2:** Tasks 4.1-4.3 (Request model)
- **Days 3-4:** Tasks 5.1-5.3 (Expense model)
- **Day 5:** Task 6.1 (unit tests)

### Week 3: Prevention
- **Days 1-3:** Task 7.1 (validation script)
- **Day 4:** Task 7.2 (documentation)
- **Day 5:** Buffer for issues/refinement

**Total estimated effort:** 10-12 days

---

## Risk Assessment

### High Risk
- **Database migrations on production data:** Use transactions, test on copy first
- **Data backfill may take hours:** Run during maintenance window

### Medium Risk
- **Field type changes may break existing code:** Thorough testing required
- **API schema may change:** Validation script will catch this

### Low Risk
- **New fields on models:** Backwards compatible (default values)
- **Mapper fixes:** Self-contained changes

---

## Rollback Plan

### If Critical Issues Arise
1. Revert mapper changes: `git revert <commit>`
2. Database rollback: Drop new columns if empty
3. Re-deploy previous version

### Data Integrity Protection
- All fixes preserve existing data (additive only)
- New fields have safe defaults (empty string, not null)
- No destructive schema changes

---

## Dependencies and Prerequisites

### Required
- Access to Jobber API with valid credentials
- Write access to codebase
- Database migration permissions

### Nice to Have
- Staging environment for testing
- Sample Jobber account with diverse data
- CI/CD pipeline for automated testing

---

## Notes and Considerations

### Why This Happened
1. GraphQL queries were updated in recent refactor
2. Mappers were not updated in parallel
3. No automated validation between queries and mappers
4. Field name conventions inconsistent (camelCase vs snake_case)

### Lessons Learned
- Always update queries, mappers, and models together
- Automated testing can prevent field mismatches
- Schema introspection should be part of CI/CD
- Documentation helps maintain consistency

### Future Enhancements
- Consider using GraphQL code generation to auto-create mappers
- Implement schema validation in pre-commit hooks
- Create developer checklist for adding new entities

---

**Plan Status:** Ready for execution with `/execute-plan PRPs/entity-mapper-field-alignment.md`

**Estimated Total Time:** 10-12 days (2-3 weeks with testing and review)

**Priority:** High - Critical data loss issues must be fixed ASAP

**Risk Level:** Medium - Schema changes require careful testing but are low-risk with proper rollback plan
