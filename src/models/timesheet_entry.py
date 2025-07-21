"""TimeSheetEntry entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeSheetEntry:
    """
    Represents a Jobber timesheet entry entity.

    TimeSheetEntries record the time spent by users on jobs and visits.
    They are used for time tracking, labor costing, payroll processing,
    and billing calculations. Entries can be active (ticking) or completed.

    Relationships:
    - user_id: Links to the User who performed the work
    - job_id: Links to the Job where work was performed
    - visit_id: Optional link to specific Visit within the job
    - approved_by_id: Links to User who approved the timesheet
    - paid_by_id: Links to User who marked entry as paid

    Time Tracking:
    - start_at/end_at: Actual work time window
    - final_duration: Calculated duration in seconds
    - ticking: Boolean indicating if timer is actively running
    """

    id: str  # EncodedId! - The unique identifier
    user_id: str  # user.id - Foreign key to User who performed work
    job_id: str  # job.id - Foreign key to associated Job
    visit_id: str  # visit.id - Optional foreign key to specific Visit
    approved_by_id: str  # approvedBy.id - User who approved this entry
    paid_by_id: str  # paidBy.id - User who marked entry as paid
    label: str  # label: String - Label on the timesheet entry
    note: str  # note: String - Note attached to the entry
    labour_rate: str  # labourRate: Float - Labour rate for this entry
    final_duration_seconds: int  # finalDuration: Seconds! - Duration in seconds
    visit_duration_total_seconds: int  # visitDurationTotal: Int! - Total visit duration
    approved: str  # approved: Boolean! - Whether entry is approved
    ticking: str  # ticking: Boolean! - Whether timer is actively running
    start_at: str  # startAt: ISO8601DateTime! - When work started
    end_at: str  # endAt: ISO8601DateTime - When work ended (nil for ticking)
    created_at: str  # createdAt: ISO8601DateTime! - When entry was created
    updated_at: str  # updatedAt: ISO8601DateTime! - Last modification timestamp
