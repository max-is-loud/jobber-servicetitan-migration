# Database Table Usage Analysis

Analysis of all 22 database tables to determine active usage vs deprecation candidates.

## Summary

**Total Tables: 22**
- **Active Core Entities: 14**
- **Active System Tables: 8**
- **Deprecated Tables: 0**

All tables are currently in active use.

## Table Categories

### Core Entity Tables (14) - KEEP ALL

1. **clients** - Client/customer records
   - Status: ✅ ACTIVE
   - Usage: Primary entity, referenced by jobs, invoices, properties, etc.

2. **invoices** - Invoice records
   - Status: ✅ ACTIVE
   - Usage: Financial tracking, linked to clients and jobs

3. **quotes** - Quote/estimate records
   - Status: ✅ ACTIVE
   - Usage: Sales workflow, converts to jobs

4. **jobs** - Job/project records
   - Status: ✅ ACTIVE
   - Usage: Core entity, links clients, properties, visits, invoices

5. **properties** - Client property/location records
   - Status: ✅ ACTIVE
   - Usage: Service locations, linked to clients and jobs

6. **requests** - Service request records
   - Status: ✅ ACTIVE
   - Usage: Lead generation, converts to quotes/jobs

7. **visits** - Scheduled visit records
   - Status: ✅ ACTIVE
   - Usage: Scheduling, linked to jobs

8. **users** - Jobber user/team member records
   - Status: ✅ ACTIVE
   - Usage: Team management, assignment tracking

9. **expenses** - Expense records
   - Status: ✅ ACTIVE
   - Usage: Job costing, linked to jobs

10. **timesheet_entries** - Time tracking records
    - Status: ✅ ACTIVE
    - Usage: Labor tracking, linked to jobs and visits

11. **products_services** - Product/service catalog
    - Status: ✅ ACTIVE
    - Usage: Line item pricing, referenced in quotes and invoices

12. **tax_rates** - Tax rate records
    - Status: ✅ ACTIVE
    - Usage: Financial calculations, referenced by invoices and quotes

13. **notes** - Note records (polymorphic)
    - Status: ✅ ACTIVE
    - Usage: Attached to clients, jobs, invoices, quotes, requests

14. **attachments** - File attachment records
    - Status: ✅ ACTIVE
    - Usage: Files attached to notes and entities

### System Tables (8) - KEEP ALL

15. **oauth_tokens** - OAuth2 authentication tokens
    - Status: ✅ ACTIVE
    - Usage: Authentication, token refresh
    - Referenced in: `src/auth/auth_provider.py`

16. **migration_state** - Migration progress tracking
    - Status: ✅ ACTIVE
    - Usage: Resume functionality, checkpointing
    - Referenced in: `src/repositories/repository.py`, all coordinators

17. **note_references** - Deferred note loading queue
    - Status: ✅ ACTIVE
    - Usage: Cost optimization (60-70% reduction)
    - Referenced in: `src/extractors/notes_extractor.py`, all entity extractors
    - Critical for deferred note pattern

18. **graphql_costs** - GraphQL API cost tracking
    - Status: ✅ ACTIVE
    - Usage: Cost monitoring, query optimization
    - Referenced in: `src/rate_limiting/metrics_collector.py`

19. **map_snapshot** - Multi-pass migration snapshot
    - Status: ✅ ACTIVE
    - Usage: Map mode - lightweight entity discovery
    - Referenced in: `src/coordinators/map_mode_coordinator.py`, all map extractors
    - Essential for two-phase extraction pattern

20. **entity_inventory** - Entity counting and discovery
    - Status: ✅ ACTIVE
    - Usage: Progress reporting, entity counting
    - Referenced in: `src/coordinators/map_mode_coordinator.py`, all map extractors
    - Tracks discovered entities per type

21. **relation_inventory** - Relationship tracking
    - Status: ✅ ACTIVE
    - Usage: Multi-pass relationship discovery
    - Referenced in: `src/coordinators/map_mode_coordinator.py`
    - Maps entity relationships (client → jobs → invoices)

22. **extract_queue** - Entity extraction queue
    - Status: ✅ ACTIVE
    - Usage: Batch extraction, resume capability
    - Referenced in: `src/coordinators/extract_mode_coordinator.py`, all extractors
    - Manages extraction order and progress

23. **attachment_queue** - Attachment download queue
    - Status: ✅ ACTIVE
    - Usage: Deferred attachment downloads
    - Referenced in: `src/coordinators/download_mode_coordinator.py`
    - Separates attachment downloads from entity extraction

## Multi-Pass Migration Tables

The following tables are essential to the multi-pass migration architecture:

### Phase 1: Map Mode
- **map_snapshot** - Stores lightweight entity snapshots (ID + updatedAt)
- **entity_inventory** - Counts entities by type
- **relation_inventory** - Maps relationships between entities

### Phase 2: Extract Mode
- **extract_queue** - Queues entities for full extraction
- **note_references** - Defers note loading to reduce costs

### Phase 3: Download Mode
- **attachment_queue** - Queues attachments for download

## Recommendation

**KEEP ALL 22 TABLES** - No tables should be removed.

All tables serve active purposes in the application:
- 14 core entity tables store Jobber data
- 8 system tables support authentication, migration, cost tracking, and multi-pass extraction

## Next Steps for Phase 4 (Database Schema Updates)

Instead of removing tables, focus on:
1. **Adding missing columns** to existing entity tables
2. **Ensuring proper migrations** are idempotent
3. **Adding indexes** for new foreign key columns (e.g., property.tax_rate_id)
4. **Validating data types** (cents for money, TEXT for ISO dates, INTEGER for booleans)

## References

- Multi-pass architecture: See `docs/architecture/`
- Deferred note loading: See `docs/architecture/notes-optimization.md`
- Table schemas: See `DATABASE_SCHEMA.md`
- Entity models: See `src/models/`
