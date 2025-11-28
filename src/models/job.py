"""Job entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    """
    Represents a Jobber job entity.

    Jobs are the core work units in Jobber, representing actual service work
    to be performed for clients. Jobs can be created from quotes and can
    generate invoices upon completion.

    Relationships:
    - client_id: Links to the Client who requested the work
    - property_id: Optional link to the Property where work is performed
    - quote_id: Optional link to the Quote that generated this job
    """

    id: str  # EncodedId! - The unique identifier
    client_id: str  # client.id - Client relationship ID for foreign key
    property_id: str  # property.id - Optional property where work is performed
    quote_id: str  # quote.id - Optional quote that generated this job
    job_number: str  # jobNumber: String! - A non-unique number assigned to the job
    title: str  # title: String! - The description of the job
    description: str  # description: String - Detailed job description
    status: str  # status: String! - Job status (e.g., pending, in_progress, completed)
    scheduled_start_at: str  # scheduledStartAt: ISO8601DateTime - When work is scheduled
    scheduled_end_at: str  # scheduledEndAt: ISO8601DateTime - When work should complete
    completed_at: str  # completedAt: ISO8601DateTime - When job was completed
    total: int  # amounts.total converted to cents for precision
    created_at: str  # createdAt: ISO8601DateTime! - ISO format string
    updated_at: str  # updatedAt: ISO8601DateTime! - ISO format string
    job_type: str = ""  # jobType: JobTypeEnum - Type of job (one_time, recurring, etc.)
    billing_type: str = ""  # billingType: BillingTypeEnum - Billing method (flat_rate, hourly, etc.)
    invoiced_total: int = 0  # invoicedTotal: Float - Total amount invoiced in cents
