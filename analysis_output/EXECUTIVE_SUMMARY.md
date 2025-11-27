# GraphQL Field Mismatch Analysis - Executive Summary

**Date:** 2025-11-27
**Analyzed By:** Automated Analysis Tool
**Total Entities Analyzed:** 12

---

## Critical Findings

### 🔴 CRITICAL: 3 entities with data corruption

1. **TaxRate** - 9 of 12 fields missing from pagination query
   - **Impact:** 75% of tax rate data will be empty/defaults
   - **Root Cause:** Pagination query only requests 3 fields, mapper expects 12
   - **Affected Query:** `TAX_RATES_QUERY` (line 708)
   - **Fix:** Add missing fields to query

2. **ProductService** - 2 field type mismatches
   - **Impact:** Category and online booking settings will be empty
   - **Root Cause:**
     - Mapper treats `category` as object, query returns scalar
     - Mapper reads `onlineBookingEnabled`, query returns `onlineBookingsEnabled`
   - **Affected Mapper:** Lines 1046, 1067
   - **Fix:** Update mapper to handle scalar category and fix field name

3. **Visit** - 1 field type mismatch + 1 missing field
   - **Impact:** completedBy extraction will fail (expects object, gets scalar)
   - **Root Cause:**
     - Mapper uses `extract_id_from_relationship()` on scalar field
     - `updatedAt` requested by mapper but not in query
   - **Affected Mapper:** Line 910
   - **Fix:** Handle completedBy as scalar, add updatedAt to query

---

## ⚠️ MEDIUM: 2 entities with incomplete data extraction

4. **Request** - 4 fields queried but not mapped
   - **Impact:** Contact information from requests is being discarded
   - **Queried but Unused:** `companyName`, `contactName`, `email`, `phone`
   - **Root Cause:** Fields extracted from GraphQL but Request model doesn't have them
   - **Affected Model:** `src/models/request.py`
   - **Fix:** Add fields to Request model or remove from query

5. **Expense** - 3 relationship fields queried but not mapped
   - **Impact:** Financial tracking metadata is being discarded
   - **Queried but Unused:** `enteredBy.id`, `paidBy.id`, `reimbursableTo.id`
   - **Root Cause:** Fields extracted from GraphQL but Expense model doesn't have them
   - **Affected Model:** `src/models/expense.py`
   - **Fix:** Add fields to Expense model or remove from query

---

## ✅ GOOD: 7 entities with correct field alignment

- Client ✅
- Invoice ✅
- Quote ✅
- Job ✅
- Property ✅ (recently fixed)
- User ✅
- TimeSheetEntry ✅

---

## Data Loss Summary

| Entity | Fields Missing/Wrong | Data Loss % | Severity |
|--------|---------------------|-------------|----------|
| TaxRate | 9/12 | 75% | 🔴 Critical |
| ProductService | 2/12 | 17% | 🔴 Critical |
| Visit | 1/16 + 1 extra | ~12% | 🔴 Critical |
| Request | 4 unused | Variable | ⚠️ Medium |
| Expense | 3 unused | Variable | ⚠️ Medium |

---

## Root Cause Analysis

### Primary Issues

1. **Query Inconsistency:** Pagination queries vs single-entity queries request different fields
   - Example: `TAX_RATES_QUERY` has 3 fields, `ENTITY_BY_ID_QUERY ... on TaxRate` has 12 fields
   - **Solution:** Standardize field selection across query types

2. **Type Assumptions:** Mapper assumes object types where API returns scalars
   - Example: `category` treated as `{name: string}` but is actually just `string`
   - **Solution:** Validate against GraphQL schema introspection

3. **Model-Query Mismatch:** Models missing fields that are being queried
   - Example: Request query gets contact info, but Request model has no fields for it
   - **Solution:** Either add fields to models or remove from queries

---

## Recommended Fix Order

### Phase 1: Critical Data Loss (Immediate)
1. Fix TaxRate query - Add 9 missing fields
2. Fix ProductService mapper - Handle scalar category, fix field name
3. Fix Visit mapper - Handle scalar completedBy

### Phase 2: Data Completeness (Next Sprint)
4. Enhance Request model - Add contact fields
5. Enhance Expense model - Add tracking fields
6. Add Visit.updatedAt to query

### Phase 3: Prevention (Long-term)
7. Create automated query-mapper validation tests
8. Use GraphQL schema introspection for validation
9. Standardize pagination vs single-entity queries

---

## Files Requiring Changes

### Queries (`src/clients/jobber_client.py`)
- Line 708: `TAX_RATES_QUERY` - Add 9 fields
- Line 593: `VISITS_QUERY` - Add updatedAt field

### Mappers (`src/mappers/entity_mapper.py`)
- Line 1046: ProductService - Fix category extraction (scalar not object)
- Line 1067: ProductService - Fix field name `onlineBookingEnabled` → `onlineBookingsEnabled`
- Line 910: Visit - Fix completedBy extraction (scalar not relationship)
- Line 917: Visit - Handle missing updatedAt gracefully

### Models (Optional - if keeping queried fields)
- `src/models/request.py` - Add: companyName, contactName, email, phone
- `src/models/expense.py` - Add: enteredBy, paidBy, reimbursableTo

---

## Validation Strategy

### Immediate Testing
```bash
# Test each entity extraction with real API data
# Verify all queried fields are captured in models
# Check for None/empty values that should have data
```

### Automated Prevention
```python
# Create unit test that:
# 1. Parses GraphQL query to extract requested fields
# 2. Inspects mapper code to find accessed fields
# 3. Compares and reports mismatches
# 4. Fails CI if mismatches detected
```

---

## Success Criteria

✅ All queried fields are successfully mapped to model properties
✅ No mapper tries to access fields not in query
✅ Pagination and single-entity queries return consistent data
✅ Zero data loss during extraction
✅ Automated tests prevent future regressions

---

## Next Steps

1. Review this analysis with team
2. Prioritize fixes based on business impact
3. Create tickets for each fix
4. Implement automated validation
5. Document field mapping standards
