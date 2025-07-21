"""Visit entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Visit:
    """
    Represents a Jobber visit entity.

    Visits represent each scheduled occurrence when a service provider goes to
    a client property to complete work. Jobs can have multiple visits for
    multi-day work or recurring services.

    Relationships:
    - job_id: Links to the Job this visit belongs to
    - client_id: Links to the Client being served
    - property_id: Links to the Property where work is performed
    - assigned_user_id: Links to the User assigned to perform the visit

    Scheduling Information:
    - start_at/end_at: Scheduled time window for the visit
    - duration_minutes: Calculated duration of the visit
    - all_day: Boolean indicating if visit is scheduled for entire day
    """

    id: str  # EncodedId! - The unique identifier
    job_id: str  # job.id - Foreign key to associated Job
    client_id: str  # client.id - Foreign key to Client being served
    property_id: str  # property.id - Foreign key to Property where work occurs
    assigned_user_id: str  # assignedUsers.first.id - Primary assigned user
    title: str  # title: String - Visit title/description
    instructions: str  # instructions: String - Specific visit instructions
    status: str  # visitStatus: VisitStatusTypeEnum! - Visit status
    all_day: str  # allDay: Boolean! - Full day visit flag
    duration_minutes: int  # duration: Int - Duration in minutes
    start_at: str  # startAt: ISO8601DateTime - Scheduled start time
    end_at: str  # endAt: ISO8601DateTime - Scheduled end time
    completed_at: str  # completedAt: ISO8601DateTime - When visit was completed
    created_at: str  # createdAt: ISO8601DateTime! - When visit was created
    updated_at: str  # updatedAt: ISO8601DateTime! - Last modification timestamp
