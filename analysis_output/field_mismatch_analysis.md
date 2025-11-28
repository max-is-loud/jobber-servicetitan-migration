# Entity Mapper Field Alignment Analysis

## Summary
- Total entities analyzed: 12
- Entities with mismatches: 5
- Critical issues found: 7

---

## Detailed Findings

### 1. Client

**GraphQL Query Fields Requested:**
```
id
firstName
lastName
companyName
balance
isArchivable
isCompany
billingAddress.street
billingAddress.city
billingAddress.province
billingAddress.postalCode
billingAddress.country
emails[].address
phones[].number
notes (nested connection)
noteAttachments (nested connection)
createdAt
updatedAt
```

**Mapper Fields Being Read:**
```
id ✓
firstName ✓
lastName ✓
companyName ✓
balance ✓
isArchivable ✓
isCompany ✓
billingAddress.street ✓
billingAddress.city ✓
billingAddress.province ✓
billingAddress.postalCode ✓
billingAddress.country ✓
emails[].address ✓
phones[].number ✓
createdAt ✓
```

**Issues:**
✅ No mismatches - All fields align correctly

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:46-125`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:34-117`

---

### 2. Invoice

**GraphQL Query Fields Requested:**
```
id
client.id
invoiceNumber
amounts.total
amounts.subtotal
amounts.taxAmount
amounts.discountAmount
amounts.depositAmount
invoiceNet
invoiceStatus
issuedDate
dueDate
subject
message
lineItems (nested connection)
notes (nested connection)
noteAttachments (nested connection)
createdAt
updatedAt
```

**Mapper Fields Being Read:**
```
id ✓
client.id ✓
invoiceNumber ✓
amounts.total ✓
amounts.subtotal ✓
amounts.taxAmount ✓
amounts.discountAmount ✓
amounts.depositAmount ✓
invoiceNet ✓
invoiceStatus ✓
issuedDate ✓
dueDate ✓
subject ✓
message ✓
lineItems ✓
createdAt ✓
updatedAt ✓
```

**Issues:**
✅ No mismatches - All fields align correctly

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:127-211`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:119-206`

---

### 3. Quote

**GraphQL Query Fields Requested:**
```
id
client.id
property.id
quoteNumber
quoteStatus
title
amounts.total
amounts.subtotal
amounts.taxAmount
amounts.discountAmount
message
sentAt
lineItems (nested connection)
notes (nested connection)
noteAttachments (nested connection)
createdAt
transitionedAt
updatedAt
```

**Mapper Fields Being Read:**
```
id ✓
client.id ✓
property.id ✓
quoteNumber ✓
title ✓
amounts.total ✓
amounts.subtotal ✓
amounts.taxAmount ✓
amounts.discountAmount ✓
message ✓
quoteStatus ✓
sentAt ✓
lineItems ✓
createdAt ✓
transitionedAt ✓
updatedAt ✓
```

**Issues:**
✅ No mismatches - All fields align correctly

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:213-300`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:208-300`

---

### 4. Job

**GraphQL Query Fields Requested:**
```
id
client.id
property.id
quote.id
jobNumber
jobType
title
instructions
jobStatus
billingType
startAt
endAt
completedAt
total
invoicedTotal
notes (nested connection)
noteAttachments (nested connection)
createdAt
updatedAt
```

**Mapper Fields Being Read:**
```
id ✓
client.id ✓
property.id ✓
quote.id ✓
jobNumber ✓
title ✓
instructions ✓ (mapped to description)
jobStatus ✓ (mapped to status)
startAt ✓ (mapped to scheduled_start_at)
endAt ✓ (mapped to scheduled_end_at)
completedAt ✓
total ✓
jobType ✓
billingType ✓
invoicedTotal ✓
createdAt ✓
updatedAt ✓
```

**Issues:**
✅ No mismatches - All fields align correctly (field name transformations are intentional)

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:317-391`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:471-553`

---

### 5. Property ✅ ALREADY FIXED

**GraphQL Query Fields Requested:**
```
id
name
client.id
taxRate.id
taxRate.name
isBillingAddress
routingOrder
address.street
address.street1
address.street2
address.city
address.province
address.postalCode
address.country
address.coordinates.latitude
address.coordinates.longitude
```

**Mapper Fields Being Read:**
```
id ✓
name ✓
client.id ✓
taxRate.id ✓
taxRate.name ✓
isBillingAddress ✓
routingOrder ✓
address.street1 ✓
address.street2 ✓
address.city ✓
address.province ✓
address.postalCode ✓
address.country ✓
address.coordinates.latitude ✓
address.coordinates.longitude ✓
```

**Issues:**
✅ ALREADY FIXED in recent commit

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:393-437`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:555-639`

---

### 6. Request

**GraphQL Query Fields Requested:**
```
id
client.id
property.id
title
source
requestStatus
companyName
contactName
email
phone
notes (nested connection)
noteAttachments (nested connection)
createdAt
updatedAt
```

**Mapper Fields Being Read:**
```
id ✓
client.id ✓
property.id ✓
title ✓
source ✓
requestStatus ✓ (mapped to status)
companyName ✗ (NOT MAPPED - field requested but never used)
contactName ✗ (NOT MAPPED - field requested but never used)
email ✗ (NOT MAPPED - field requested but never used)
phone ✗ (NOT MAPPED - field requested but never used)
createdAt ✓
updatedAt ✓
```

**Issues:**
1. **MISSING**: Query requests `companyName` but mapper never uses it
2. **MISSING**: Query requests `contactName` but mapper never uses it
3. **MISSING**: Query requests `email` but mapper never uses it
4. **MISSING**: Query requests `phone` but mapper never uses it

**Impact:** MEDIUM - Contact information from requests is being lost

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:439-516`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:641-712`

**Note:** Mapper extracts these fields (lines 679-682) but doesn't use them in the Request model constructor. The Request model may need additional fields.

---

### 7. User

**GraphQL Query Fields Requested:**
```
id
name.first
name.last
email.raw
phone.raw
timezone
isAccountAdmin
isAccountOwner
availableForScheduling
assignedColor
status
createdAt
lastLoginAt
```

**Mapper Fields Being Read:**
```
id ✓
name.first ✓
name.last ✓
email.raw ✓
isAccountAdmin ✓
isAccountOwner ✓
status ✓
phone.raw ✓
timezone ✓
availableForScheduling ✓
assignedColor ✓
createdAt ✓
lastLoginAt ✓
```

**Issues:**
✅ No mismatches - All fields align correctly

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:522-554`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:714-790`

---

### 8. Expense

**GraphQL Query Fields Requested:**
```
id
linkedJob.id
title
description
total
date
enteredBy.id
paidBy.id
reimbursableTo.id
createdAt
updatedAt
```

**Mapper Fields Being Read:**
```
id ✓
linkedJob.id ✓
title ✓
description ✓
total ✓
date ✓
createdAt ✓
updatedAt ✓
```

**Issues:**
1. **MISSING**: Query requests `enteredBy.id` but mapper never uses it
2. **MISSING**: Query requests `paidBy.id` but mapper never uses it
3. **MISSING**: Query requests `reimbursableTo.id` but mapper never uses it

**Impact:** MEDIUM - Financial tracking metadata is being lost

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:557-589`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:792-852`

---

### 9. Visit

**GraphQL Query Fields Requested:**
```
id
job.id
client.id
property.id
assignedUsers[].id
title
instructions
visitStatus
allDay
clientConfirmed
duration
startAt
endAt
completedAt
completedBy
createdAt
```

**Mapper Fields Being Read:**
```
id ✓
job.id ✓
client.id ✓
property.id ✓
assignedUsers[0].id ✓
title ✓
instructions ✓
visitStatus ✓
allDay ✓
duration ✓
clientConfirmed ✓
completedBy ✗ (MISMATCH - trying to extract ID from relationship, but field is scalar)
startAt ✓
endAt ✓
completedAt ✓
createdAt ✓
updatedAt ✗ (EXTRA - mapper tries to read but NOT in query)
```

**Issues:**
1. **CRITICAL**: Mapper line 910 tries to extract `completedBy` as relationship object, but GraphQL returns it as a scalar string (line 624)
2. **EXTRA**: Mapper reads `updatedAt` but query doesn't request it (line 917)

**Impact:** HIGH - completedBy data extraction will fail

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:591-634`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:854-940`

---

### 10. TimeSheetEntry

**GraphQL Query Fields Requested:**
```
id
user.id
job.id
visit.id
approvedBy.id
paidBy.id
label
note
labourRate
finalDuration
visitDurationTotal
approved
ticking
startAt
endAt
createdAt
updatedAt
```

**Mapper Fields Being Read:**
```
id ✓
user.id ✓
job.id ✓
visit.id ✓
approvedBy.id ✓
paidBy.id ✓
label ✓
note ✓
labourRate ✓
finalDuration ✓
visitDurationTotal ✓
approved ✓
ticking ✓
startAt ✓
endAt ✓
createdAt ✓
updatedAt ✓
```

**Issues:**
✅ No mismatches - All fields align correctly

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:637-677`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:942-1020`

---

### 11. ProductService

**GraphQL Query Fields Requested:**
```
id
name
description
category
defaultUnitCost
internalUnitCost
markup
durationMinutes
taxable
visible
onlineBookingsEnabled
onlineBookingSortOrder
```

**Mapper Fields Being Read:**
```
id ✓
name ✓
description ✓
category ✗ (MISMATCH - mapper tries to extract from nested object, but query returns scalar)
defaultUnitCost ✓
internalUnitCost ✓
markup ✓
durationMinutes ✓
taxable ✓
visible ✓
onlineBookingEnabled ✗ (MISMATCH - query uses 'onlineBookingsEnabled', mapper reads 'onlineBookingEnabled')
onlineBookingSortOrder ✓
```

**Issues:**
1. **CRITICAL**: Mapper line 1046 tries to extract `category` from nested object `category.name`, but GraphQL returns it as a scalar string (line 688)
2. **CRITICAL**: Mapper line 1067 reads `onlineBookingEnabled` (singular), but query returns `onlineBookingsEnabled` (plural with 's')

**Impact:** HIGH - Category and online booking flag will be empty

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:680-705`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:1022-1101`

---

### 12. TaxRate

**GraphQL Query Fields Requested:**
```
id
name
description
```

**Mapper Fields Being Read:**
```
id ✓
name ✓
rate ✗ (EXTRA - mapper tries to read but NOT in query)
region ✗ (EXTRA - mapper tries to read but NOT in query)
compound ✗ (EXTRA - mapper tries to read but NOT in query)
active ✗ (EXTRA - mapper tries to read but NOT in query)
description ✓
taxNumber ✗ (EXTRA - mapper tries to read but NOT in query)
displayOrder ✗ (EXTRA - mapper tries to read but NOT in query)
defaultForRegion ✗ (EXTRA - mapper tries to read but NOT in query)
createdAt ✗ (EXTRA - mapper tries to read but NOT in query)
updatedAt ✗ (EXTRA - mapper tries to read but NOT in query)
```

**Issues:**
1. **EXTRA**: Mapper reads `rate` but NOT in query (will always be 0)
2. **EXTRA**: Mapper reads `region` but NOT in query (will always be empty)
3. **EXTRA**: Mapper reads `compound` but NOT in query (will always be false)
4. **EXTRA**: Mapper reads `active` but NOT in query (will always be true by default)
5. **EXTRA**: Mapper reads `taxNumber` but NOT in query (will always be empty)
6. **EXTRA**: Mapper reads `displayOrder` but NOT in query (will always be 0)
7. **EXTRA**: Mapper reads `defaultForRegion` but NOT in query (will always be false)
8. **EXTRA**: Mapper reads `createdAt` but NOT in query (will always be empty)
9. **EXTRA**: Mapper reads `updatedAt` but NOT in query (will always be empty)

**Impact:** CRITICAL - Almost all tax rate data will be empty/default values

**Files:**
- Query: `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py:708-724`
- Mapper: `/home/max/projects/tightbeam-v2/src/mappers/entity_mapper.py:1103-1160`

---

## Priority Fix List

### Critical (Data Loss)
1. **TaxRate** - 9 fields missing from query - almost all data will be empty
2. **ProductService** - 2 field mismatches (category, onlineBookingEnabled) - core data corrupted
3. **Visit** - 1 field type mismatch (completedBy) - will cause extraction errors

### Medium (Missing Data)
4. **Request** - 4 fields not mapped (companyName, contactName, email, phone) - contact info lost
5. **Expense** - 3 fields not mapped (enteredBy, paidBy, reimbursableTo) - tracking metadata lost
6. **Visit** - 1 extra field (updatedAt) - minor issue, will be empty

### Low (Already Fixed)
7. **Property** - Already fixed in recent commit ✅

---

## Recommended Actions

### Immediate (Critical Fixes)
1. **Fix TaxRate Query** - Add missing fields to `TAX_RATES_QUERY`
2. **Fix ProductService** - Fix category extraction and field name mismatch
3. **Fix Visit completedBy** - Handle as scalar instead of relationship

### Short-term (Data Completeness)
4. **Enhance Request model** - Add fields for companyName, contactName, email, phone
5. **Enhance Expense model** - Add fields for enteredBy, paidBy, reimbursableTo
6. **Fix Visit query** - Add updatedAt if needed, or remove from mapper

### Testing
- Create integration tests comparing query fields vs mapper field access
- Add schema validation to catch mismatches during development
- Consider using GraphQL introspection to auto-validate queries
