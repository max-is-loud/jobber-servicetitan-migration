"""User entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    """
    Represents a Jobber user entity.

    Users are the employees and service providers who operate within a Jobber account.
    They can be assigned to visits, create jobs, and manage client relationships.
    Users have roles and permissions within the account hierarchy.

    Relationships:
    - account_id: Links to the parent Account entity
    - User data maps directly from Jobber GraphQL User schema

    Role Information:
    - isAccountAdmin: Boolean indicating admin privileges
    - isAccountOwner: Boolean indicating account ownership
    - status: User status (active, inactive, etc.)
    """

    id: str  # EncodedId! - The unique identifier
    first_name: str  # name.first: String! - User's first name
    last_name: str  # name.last: String! - User's last name
    email: str  # email.raw: String! - Primary email address (UserEmail type)
    role: str  # Derived from isAccountAdmin/isAccountOwner flags
    is_account_admin: str  # isAccountAdmin: Boolean! - Admin privileges
    is_account_owner: str  # isAccountOwner: Boolean! - Account ownership
    status: str  # status: UserStatusEnum! - User status
    phone: str  # phone.raw: String - Phone number (UserPhone type)
    timezone: str  # timezone: Timezone (scalar) - User's timezone
    created_at: str  # createdAt: ISO8601DateTime! - When user was created
    last_login_at: str  # lastLoginAt: ISO8601DateTime - Last login timestamp
    available_for_scheduling: int = 0  # availableForScheduling: Boolean! - Scheduling availability (0/1)
    assigned_color: str = ""  # assignedColor: String - Calendar color for this user
