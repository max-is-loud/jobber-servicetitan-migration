# Jobber GraphQL Schema - Entity Field Summary

## Key Entities

### Client (42 fields)

| Field | Type | Nullable |
|-------|------|----------|
| balance | Float! | ✗ |
| billingAddress | ClientAddress | ✓ |
| billingAddressPresent | Boolean! | ✗ |
| clientProperties | PropertyConnection! | ✗ |
| companyName | String | ✓ |
| contacts | ContactModelConnection! | ✗ |
| createdAt | ISO8601DateTime! | ✗ |
| customFields | [Unknown]! | ✗ |
| defaultEmails | [Unknown]! | ✗ |
| defaultPhones | [Unknown]! | ✗ |
| emails | [Unknown]! | ✗ |
| firstName | String! | ✗ |
| id | EncodedId! | ✗ |
| invoices | InvoiceConnection! | ✗ |
| isArchivable | Boolean! | ✗ |
| isArchived | Boolean! | ✗ |
| isCompany | Boolean! | ✗ |
| isLead | Boolean! | ✗ |
| jobberWebUri | String! | ✗ |
| jobs | JobConnection! | ✗ |
| lastName | String! | ✗ |
| messages | MessageInterfaceConnection! | ✗ |
| name | String! | ✗ |
| noteAttachments | ClientNoteFileConnection! | ✗ |
| notes | ClientNoteConnection! | ✗ |
| phones | [Unknown]! | ✗ |
| quotes | QuoteConnection! | ✗ |
| receivesFollowUps | Boolean! | ✗ |
| receivesInvoiceFollowUps | Boolean! | ✗ |
| receivesQuoteFollowUps | Boolean! | ✗ |
| receivesReminders | Boolean! | ✗ |
| receivesReviewRequests | Boolean! | ✗ |
| requestedWorkObjects | RequestedWorkObjectUnionConnection | ✓ |
| requests | RequestConnection! | ✗ |
| sampleData | Boolean! | ✗ |
| scheduledItems | ScheduledItemInterfaceConnection! | ✗ |
| secondaryName | String | ✓ |
| sourceAttribution | SourceAttribution | ✓ |
| tags | TagConnection! | ✗ |
| title | String | ✓ |
| unallocatedDepositRecords | PaymentRecordInterfaceConnection! | ✗ |
| updatedAt | ISO8601DateTime! | ✗ |

### Invoice (35 fields)

| Field | Type | Nullable |
|-------|------|----------|
| allowReviewRequest | Boolean! | ✗ |
| amounts | InvoiceAmounts | ✓ |
| billingAddress | InvoiceBillingAddress | ✓ |
| billingIsSameAsPropertyAddress | Boolean | ✓ |
| client | Client | ✓ |
| clientHubUri | String | ✓ |
| contractDisclaimer | String | ✓ |
| createdAt | ISO8601DateTime! | ✗ |
| customFields | [Unknown]! | ✗ |
| dateViewedInClientHub | ISO8601DateTime | ✓ |
| dueDate | ISO8601DateTime | ✓ |
| hasInvoiceNumberDuplicates | Boolean! | ✗ |
| id | EncodedId! | ✗ |
| invoiceNet | Int | ✓ |
| invoiceNumber | String! | ✗ |
| invoiceStatus | InvoiceStatusTypeEnum! | ✗ |
| issuedDate | ISO8601DateTime | ✓ |
| jobberWebUri | String! | ✗ |
| jobs | JobConnection! | ✗ |
| lineItems | InvoiceLineItemConnection! | ✗ |
| linkedCommunications | MessageInterfaceConnection! | ✗ |
| message | String | ✓ |
| nextDateToSendReviewSms | ISO8601DateTime | ✓ |
| noteAttachments | InvoiceNoteFileConnection! | ✗ |
| notes | InvoiceNoteUnionConnection! | ✗ |
| paymentRecords | PaymentRecordConnection! | ✗ |
| properties | PropertyConnection! | ✗ |
| receivedDate | ISO8601DateTime | ✓ |
| salesperson | User | ✓ |
| subject | String! | ✗ |
| taxCalculationMethod | String! | ✗ |
| taxDetails | TaxDetails | ✓ |
| taxRate | TaxRate | ✓ |
| updatedAt | ISO8601DateTime! | ✗ |
| visits | VisitConnection! | ✗ |

### Quote (30 fields)

| Field | Type | Nullable |
|-------|------|----------|
| amounts | QuoteAmounts! | ✗ |
| client | Client | ✓ |
| clientHubUri | String | ✓ |
| clientHubViewedAt | ISO8601DateTime | ✓ |
| contractDisclaimer | String | ✓ |
| createdAt | ISO8601DateTime! | ✗ |
| customFields | [Unknown]! | ✗ |
| depositAmountUnallocated | Float | ✓ |
| depositRecords | PaymentRecordConnection! | ✗ |
| eligibleForFinancing | Boolean! | ✗ |
| id | EncodedId! | ✗ |
| jobberWebUri | String! | ✗ |
| jobs | JobConnection | ✓ |
| lastTransitioned | QuoteLastTransitioned! | ✗ |
| lineItems | QuoteLineItemConnection! | ✗ |
| linkedCommunications | MessageInterfaceConnection! | ✗ |
| message | String | ✓ |
| noteAttachments | QuoteNoteFileConnection! | ✗ |
| notes | QuoteNoteUnionConnection! | ✗ |
| property | Property | ✓ |
| quoteNumber | String! | ✗ |
| quoteStatus | QuoteStatusTypeEnum! | ✗ |
| request | Request | ✓ |
| salesperson | User | ✓ |
| sentAt | ISO8601DateTime | ✓ |
| taxDetails | TaxDetails | ✓ |
| title | String | ✓ |
| transitionedAt | ISO8601DateTime! | ✗ |
| unallocatedDepositRecords | PaymentRecordConnection! | ✗ |
| updatedAt | ISO8601DateTime! | ✗ |

### Job (42 fields)

| Field | Type | Nullable |
|-------|------|----------|
| allowReviewRequest | Boolean! | ✗ |
| arrivalWindow | ArrivalWindow | ✓ |
| billingType | BillingStrategy! | ✗ |
| bookingConfirmationSentAt | ISO8601DateTime | ✓ |
| client | Client! | ✗ |
| completedAt | ISO8601DateTime | ✓ |
| createdAt | ISO8601DateTime! | ✗ |
| customFields | [Unknown]! | ✗ |
| defaultVisitTitle | String! | ✗ |
| endAt | ISO8601DateTime | ✓ |
| expenses | ExpenseConnection! | ✗ |
| id | EncodedId! | ✗ |
| instructions | String | ✓ |
| invoiceSchedule | InvoiceSchedule! | ✗ |
| invoicedTotal | Float! | ✗ |
| invoices | InvoiceConnection! | ✗ |
| jobBalanceTotals | JobBalanceTotals | ✓ |
| jobCosting | JobCosting | ✓ |
| jobNumber | Int! | ✗ |
| jobStatus | JobStatusTypeEnum! | ✗ |
| jobType | JobTypeTypeEnum! | ✗ |
| jobberWebUri | String! | ✗ |
| lineItems | JobLineItemConnection! | ✗ |
| nextDateToSendReviewSms | ISO8601DateTime | ✓ |
| noteAttachments | JobNoteFileConnection! | ✗ |
| notes | JobNoteUnionConnection! | ✗ |
| paymentRecords | PaymentRecordConnection! | ✗ |
| property | Property! | ✗ |
| quote | Quote | ✓ |
| request | Request | ✓ |
| salesperson | User | ✓ |
| source | Source! | ✗ |
| startAt | ISO8601DateTime | ✓ |
| timeSheetEntries | TimeSheetEntryConnection! | ✗ |
| title | String | ✓ |
| total | Float! | ✗ |
| uninvoicedTotal | Float! | ✗ |
| updatedAt | ISO8601DateTime! | ✗ |
| visitSchedule | VisitSchedule! | ✗ |
| visits | VisitConnection! | ✗ |
| visitsInfo | VisitsInfo! | ✗ |
| willClientBeAutomaticallyCharged | Boolean | ✓ |

### Property (14 fields)

| Field | Type | Nullable |
|-------|------|----------|
| address | PropertyAddress! | ✗ |
| client | Client | ✓ |
| contacts | ContactModelConnection | ✓ |
| customFields | [Unknown]! | ✗ |
| id | EncodedId! | ✗ |
| isBillingAddress | Boolean | ✓ |
| jobberWebUri | String! | ✗ |
| jobs | JobConnection! | ✗ |
| name | String | ✓ |
| quotes | QuoteConnection! | ✗ |
| recentPricing | ProductOrServiceConnection | ✓ |
| requests | RequestConnection! | ✗ |
| routingOrder | Int | ✓ |
| taxRate | TaxRate | ✓ |

### Request (23 fields)

| Field | Type | Nullable |
|-------|------|----------|
| arrivalWindow | ArrivalWindow | ✓ |
| assessment | Assessment | ✓ |
| client | Client! | ✗ |
| companyName | String | ✓ |
| contactName | String | ✓ |
| createdAt | ISO8601DateTime! | ✗ |
| email | String | ✓ |
| id | EncodedId! | ✗ |
| isArchivable | Boolean! | ✗ |
| isScheduled | Boolean! | ✗ |
| jobberWebUri | String! | ✗ |
| jobs | JobConnection! | ✗ |
| lineItems | RequestLineItemConnection | ✓ |
| noteAttachments | RequestNoteFileConnection! | ✗ |
| notes | RequestNoteUnionConnection! | ✗ |
| phone | String | ✓ |
| property | Property | ✓ |
| quotes | QuoteConnection! | ✗ |
| referringClient | Client | ✓ |
| requestStatus | RequestStatusTypeEnum! | ✗ |
| source | String! | ✗ |
| title | String | ✓ |
| updatedAt | ISO8601DateTime! | ✗ |

### Visit (30 fields)

| Field | Type | Nullable |
|-------|------|----------|
| actionsUponComplete | [Unknown]! | ✗ |
| allDay | Boolean! | ✗ |
| arrivalWindow | ArrivalWindow | ✓ |
| assignedUsers | UserConnection | ✓ |
| client | Client! | ✗ |
| clientConfirmed | Boolean! | ✗ |
| completedAt | ISO8601DateTime | ✓ |
| completedBy | String | ✓ |
| createdAt | ISO8601DateTime! | ✗ |
| createdBy | User | ✓ |
| duration | Int | ✓ |
| endAt | ISO8601DateTime | ✓ |
| id | EncodedId! | ✗ |
| incompleteJobFormsCount | Int! | ✗ |
| instructions | String | ✓ |
| invoice | Invoice | ✓ |
| isComplete | Boolean! | ✗ |
| isDefaultTitle | Boolean! | ✗ |
| isLastScheduledVisit | Boolean! | ✗ |
| job | Job! | ✗ |
| lineItems | JobLineItemConnection! | ✗ |
| notes | JobNoteUnionConnection | ✓ |
| overrideOrder | Int | ✓ |
| property | Property! | ✗ |
| routingOrder | Int | ✓ |
| startAt | ISO8601DateTime | ✓ |
| teamReminderOffset | Minutes | ✓ |
| timeSheetEntries | TimeSheetEntryConnection | ✓ |
| title | String | ✓ |
| visitStatus | VisitStatusTypeEnum! | ✗ |

### User (21 fields)

| Field | Type | Nullable |
|-------|------|----------|
| account | Account | ✓ |
| address | UserAddress | ✓ |
| apps | ApplicationConnection! | ✗ |
| assignedColor | String | ✓ |
| assignedVehicle | Vehicle | ✓ |
| availableForScheduling | Boolean! | ✗ |
| createdAt | ISO8601DateTime! | ✗ |
| customFields | [Unknown]! | ✗ |
| email | UserEmail! | ✗ |
| firstDayOfTheWeek | UserFirstDayOfTheWeekEnum! | ✗ |
| franchiseTokenLastFour | String | ✓ |
| id | EncodedId! | ✗ |
| isAccountAdmin | Boolean! | ✗ |
| isAccountOwner | Boolean! | ✗ |
| isCurrentUser | Boolean! | ✗ |
| lastLoginAt | ISO8601DateTime | ✓ |
| name | Name! | ✗ |
| phone | UserPhone | ✓ |
| status | UserStatusEnum! | ✗ |
| timezone | Timezone | ✓ |
| uuid | String! | ✗ |

### Expense (11 fields)

| Field | Type | Nullable |
|-------|------|----------|
| createdAt | ISO8601DateTime! | ✗ |
| date | ISO8601DateTime! | ✗ |
| description | String | ✓ |
| enteredBy | User | ✓ |
| id | EncodedId! | ✗ |
| linkedJob | Job | ✓ |
| paidBy | User | ✓ |
| reimbursableTo | User | ✓ |
| title | String! | ✗ |
| total | Float | ✓ |
| updatedAt | ISO8601DateTime! | ✗ |

### TimeSheetEntry (18 fields)

| Field | Type | Nullable |
|-------|------|----------|
| approved | Boolean! | ✗ |
| approvedBy | User | ✓ |
| client | Client | ✓ |
| createdAt | ISO8601DateTime! | ✗ |
| endAt | ISO8601DateTime | ✓ |
| finalDuration | Seconds! | ✗ |
| id | EncodedId! | ✗ |
| job | Job | ✓ |
| label | String | ✓ |
| labourRate | Float | ✓ |
| note | String | ✓ |
| paidBy | User | ✓ |
| startAt | ISO8601DateTime! | ✗ |
| ticking | Boolean! | ✗ |
| updatedAt | ISO8601DateTime! | ✗ |
| user | User | ✓ |
| visit | Visit | ✓ |
| visitDurationTotal | Int! | ✗ |

### ProductOrService (16 fields)

| Field | Type | Nullable |
|-------|------|----------|
| bookableType | SelfServeBooking | ✓ |
| category | ProductsAndServicesCategory! | ✗ |
| defaultUnitCost | Float! | ✗ |
| description | String | ✓ |
| durationMinutes | Minutes | ✓ |
| id | EncodedId! | ✗ |
| internalUnitCost | Float | ✓ |
| lastJobLineItem | JobLineItem | ✓ |
| lastQuoteLineItem | QuoteLineItem | ✓ |
| markup | Float | ✓ |
| name | String! | ✗ |
| onlineBookingSortOrder | Int | ✓ |
| onlineBookingsEnabled | Boolean | ✓ |
| quantityRange | QuantityRange | ✓ |
| taxable | Boolean | ✓ |
| visible | Boolean | ✓ |


## Complex Types

### InvoiceAmounts

| Field | Type |
|-------|------|
| depositAmount | Float! |
| discountAmount | Float! |
| invoiceBalance | Float! |
| legacyDiscountAmount | Float! |
| nonTaxAmount | Float! |
| paymentsTotal | Float! |
| subtotal | Float! |
| taxAmount | Float! |
| tipsTotal | Float! |
| total | Float! |

### QuoteAmounts

| Field | Type |
|-------|------|
| depositAmount | Float! |
| discountAmount | Float! |
| nonTaxAmount | Float! |
| outstandingDepositAmount | Float! |
| subtotal | Float! |
| taxAmount | Float! |
| total | Float! |

### ClientAddress

| Field | Type |
|-------|------|
| city | String! |
| country | String! |
| latitude | String! |
| longitude | String! |
| name | String |
| postalCode | String! |
| province | String! |
| street | String! |
| street1 | String! |
| street2 | String! |

### PropertyAddress

| Field | Type |
|-------|------|
| city | String |
| coordinates | GeoPoint |
| country | String |
| geoStatus | GeoStatus |
| id | EncodedId! |
| name | String |
| postalCode | String |
| province | String |
| street | String! |
| street1 | String |
| street2 | String |


## Statistics

- Total types: 26
- Object types: 21
- Scalar types: 1
- Union types: 4
- Enum types: 0
