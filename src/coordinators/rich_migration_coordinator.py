"""Enhanced migration coordinator with Rich progress bars and status displays."""

from typing import Optional, Any

from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)

from .base_migration_coordinator import BaseMigrationCoordinator
from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..extractors import (
    AttachmentDownloader,
    NoteReferenceCollector,
    NotesExtractor,
    QuotesExtractor,
)
from ..interfaces import Logger
from ..loggers import RichLogger
from ..mappers import EntityMapper
from ..repositories import Repository


class RichMigrationCoordinator(BaseMigrationCoordinator):
    """Enhanced migration coordinator with Rich progress bars and visual feedback.

    Provides Rich UI-based progress feedback while delegating shared migration
    logic to BaseMigrationCoordinator. Implements Template Method pattern with
    Rich progress bars, status displays, and real-time updates.

    Provides the same functionality as console MigrationCoordinator but with enhanced
    visual feedback using Rich progress bars, status displays, and real-time
    updates during migration operations.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        note_reference_collector: Optional[NoteReferenceCollector] = None,
        notes_extractor: Optional[NotesExtractor] = None,
        quotes_extractor: Optional[QuotesExtractor] = None,
        attachment_downloader: Optional[AttachmentDownloader] = None,
        config_manager: Optional[ConfigManagerImpl] = None,
        resume: bool = False,
        enable_adaptive_optimization: bool = False,
    ) -> None:
        """Initialize Rich migration coordinator with enhanced visual feedback.

        Args:
            jobber_client: Client for Jobber API operations
            entity_mapper: Mapper for transforming API data to domain models
            repository: Repository for database operations
            logger: Logger for progress and error reporting
            note_reference_collector: Optional collector for deferred note processing
            notes_extractor: Optional extractor for Note entities with deferred processing
            quotes_extractor: Optional extractor for Quote entities
            attachment_downloader: Optional downloader for Attachment files
            config_manager: Optional ConfigManager for delays and pagination settings
            resume: Whether to skip entities that already exist in database
            enable_adaptive_optimization: Whether to enable adaptive performance optimization
        """
        # Initialize base class with all dependencies
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            note_reference_collector=note_reference_collector,
            notes_extractor=notes_extractor,
            quotes_extractor=quotes_extractor,
            attachment_downloader=attachment_downloader,
            config_manager=config_manager,
            resume=resume,
            enable_adaptive_optimization=enable_adaptive_optimization,
        )

        self._console = Console()

        # Check if we have a RichLogger for enhanced features
        self._rich_logger = isinstance(logger, RichLogger)

    def _create_progress_display(self) -> Progress:
        """Create Rich Progress display for migration tracking.

        Template Method Implementation: Rich coordinator creates Rich Progress
        with spinners, bars, and time tracking.

        Returns:
            Rich Progress object for visual progress tracking
        """
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self._console,
        )

    def _add_entity_task(
        self, display_obj: Progress, entity_name: str, description: str
    ) -> TaskID:
        """Add a new entity migration task to Rich progress display.

        Template Method Implementation: Rich coordinator adds progress task
        with Rich formatting and returns TaskID for updates.

        Args:
            display_obj: Rich Progress object from _create_progress_display()
            entity_name: Name of entity type being migrated
            description: Initial task description with Rich formatting

        Returns:
            TaskID for progress updates
        """
        return display_obj.add_task(description, total=None)

    def _update_task_progress(
        self,
        display_obj: Progress,
        task_id: Optional[Any],
        description: str,
        completed: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        """Update Rich progress display for existing task.

        Template Method Implementation: Rich coordinator updates progress
        with real-time visual feedback and Rich formatting.

        Args:
            display_obj: Rich Progress object from _create_progress_display()
            task_id: TaskID from _add_entity_task()
            description: Updated task description with Rich formatting
            completed: Current progress count
            total: Total expected count (if known)
        """
        # Only update if we have a valid task_id (Rich UI case)
        if task_id is not None:
            if completed is not None and total is not None:
                display_obj.update(
                    task_id, description=description, completed=completed, total=total
                )
            elif completed is not None:
                display_obj.update(
                    task_id, description=description, completed=completed
                )
            else:
                display_obj.update(task_id, description=description)

    def _complete_task(
        self,
        display_obj: Progress,
        task_id: Optional[Any],
        entity_name: str,
        final_count: int,
    ) -> None:
        """Mark Rich progress task as completed with final status.

        Template Method Implementation: Rich coordinator updates task
        with green checkmark and final count.

        Args:
            display_obj: Rich Progress object from _create_progress_display()
            task_id: TaskID from _add_entity_task()
            entity_name: Name of entity type that was migrated
            final_count: Final number of entities processed
        """
        # Only update if we have a valid task_id (Rich UI case)
        if task_id is not None:
            display_obj.update(
                task_id,
                description=f"[green]✓ {entity_name.title()} complete ({final_count:,} processed)",
            )

    def _start_display_context(self, display_obj: Progress) -> Live:
        """Start Rich Live display context for real-time updates.

        Template Method Implementation: Rich coordinator wraps Progress
        in Live context for real-time refresh and visual updates.

        Args:
            display_obj: Rich Progress object from _create_progress_display()

        Returns:
            Rich Live context manager for real-time display updates
        """
        return Live(display_obj, console=self._console, refresh_per_second=4)
