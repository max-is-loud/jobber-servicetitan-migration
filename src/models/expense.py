"""Expense entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Expense:
    """
    Represents a Jobber expense entity.

    Expenses are costs associated with jobs, including materials, equipment,
    subcontractor fees, and other business expenses. They track the financial
    aspects of job completion and impact job profitability calculations.

    Relationships:
    - job_id: Links to the Job this expense is associated with
    - Expenses are connected to jobs via the ExpenseConnection in GraphQL

    Financial Data:
    - amount_cents: Amount stored in cents for financial precision
    - receipt_url: Optional link to receipt image/document
    - category: Expense categorization for reporting
    """

    id: str  # EncodedId! - The unique identifier
    job_id: str  # job.id - Foreign key to associated Job
    amount_cents: int  # amount converted to cents for precision (e.g., 15099 = $150.99)
    description: str  # description: String! - Expense description
    category: str  # category: String - Expense category (materials, labor, etc.)
    receipt_url: str  # receiptUrl: String - URL to receipt image/document
    vendor: str  # vendor: String - Vendor or supplier name
    expense_date: str  # expenseDate: ISO8601DateTime! - When expense occurred
    created_at: str  # createdAt: ISO8601DateTime! - When expense was recorded
    updated_at: str  # updatedAt: ISO8601DateTime! - Last modification timestamp
