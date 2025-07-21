"""GraphQL cost entity model for TightBeam optimization."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GraphQLCost:
    """
    Represents a GraphQL query complexity cost measurement.

    Tracks the complexity points consumed by GraphQL queries to enable
    data-driven optimization of batch sizes and query limits. This replaces
    conservative defaults (like 30-record batches) with optimal values based
    on real GraphQL cost patterns from the Jobber API.

    Cost Tracking Fields:
    - requested_cost: Expected complexity points before query execution
    - actual_cost: Actual complexity points consumed by the query
    - cost_difference: Difference between actual and requested (actual - requested)
    - query_type: Type of GraphQL query (e.g., 'fetch_clients', 'fetch_invoices')
    - batch_size: Number of records requested in the batch
    - timestamp: Precise timing of the query execution (Unix timestamp)

    Analysis Purpose:
    Enables optimization by analyzing the relationship between batch size
    and complexity points to maximize efficiency while staying within
    Jobber's GraphQL rate limits and complexity budgets.
    """

    query_type: str  # Type of GraphQL query being tracked
    batch_size: int  # Number of records requested in the batch
    requested_cost: int  # Expected complexity points before execution
    actual_cost: int  # Actual complexity points consumed
    cost_difference: int  # Difference between actual and requested costs
    timestamp: float  # Unix timestamp of query execution
    created_at: str  # ISO8601DateTime when record was created
    id: Optional[int] = None  # Database primary key (auto-generated)
