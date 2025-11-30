"""Protocol interface for migration progress callbacks and display management."""

from typing import Any, Optional, Protocol


class MigrationProgressDisplay(Protocol):
    """Protocol for migration progress display implementations.

    Defines interface for both console and Rich UI progress displays,
    enabling different visual feedback approaches while maintaining
    consistent progress tracking capabilities.
    """

    def create_progress_display(self) -> Any:
        """Create and initialize progress display system.

        Returns:
            Display object (Progress for Rich, None for console logging)
        """
        ...

    def add_entity_task(self, display_obj: Any, entity_name: str, description: str) -> Optional[Any]:
        """Add a new entity migration task to the progress display.

        Args:
            display_obj: Display object from create_progress_display()
            entity_name: Name of entity type being migrated
            description: Initial task description

        Returns:
            Task identifier for updates (TaskID for Rich, None for console)
        """
        ...

    def update_task_progress(
        self,
        display_obj: Any,
        task_id: Optional[Any],
        description: str,
        completed: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        """Update progress for an existing task.

        Args:
            display_obj: Display object from create_progress_display()
            task_id: Task identifier from add_entity_task()
            description: Updated task description
            completed: Current progress count
            total: Total expected count (if known)
        """
        ...

    def complete_task(
        self,
        display_obj: Any,
        task_id: Optional[Any],
        entity_name: str,
        final_count: int,
    ) -> None:
        """Mark a task as completed with final status.

        Args:
            display_obj: Display object from create_progress_display()
            task_id: Task identifier from add_entity_task()
            entity_name: Name of entity type that was migrated
            final_count: Final number of entities processed
        """
        ...
