# Architecture Documentation

This directory contains architectural analysis documents and design decisions for the TightBeam v2 project.

## Documents

### [Rate Limiting Architecture](rate-limiting.md)
Comprehensive analysis of rate limiting architecture, comparing different approaches for managing API rate limits across the application. Documents the decision to use the ServiceFactory pattern for centralized rate limiting setup.

**Key Topics:**
- Current architecture analysis
- Token bucket implementation
- ServiceFactory pattern justification
- Decision matrix and trade-offs

**Status:** Implemented in PR #41

### [Notes Optimization Strategy](notes-optimization.md)
Detailed optimization strategy for reducing GraphQL query costs when extracting notes from the Jobber API. Identifies a 60-70% cost reduction opportunity through nested query optimization.

**Key Topics:**
- Current note extraction analysis
- GraphQL query cost breakdown
- Optimization recommendations with code examples
- Real-world cost projections

**Status:** Analysis complete, implementation pending

## Purpose

These documents serve as:
- **Decision Records**: Rationale for architectural choices
- **Implementation Guides**: Detailed strategies for complex features
- **Knowledge Transfer**: Context for future maintainers
- **Optimization Roadmap**: Identified improvements and their impact

## Maintenance

When implementing features based on these analyses:
1. Update the document with implementation status
2. Add links to relevant PRs/commits
3. Document any deviations from the original plan
4. Mark sections as outdated if architecture changes
