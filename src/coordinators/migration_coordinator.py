"""Migration coordinator for orchestrating complete data migration workflow."""

from typing import Optional, Any
from contextlib import nullcontext

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
from ..mappers import EntityMapper
from ..models import MigrationSummary
from ..repositories import Repository


class MigrationCoordinator(BaseMigrationCoordinator):
    """
    Console-based migration coordinator for orchestrating complete data migration workflow.

    Provides console logging-based progress feedback while delegating shared migration
    logic to BaseMigrationCoordinator. Implements Template Method pattern with simple
    logging-based progress display methods.

    Coordinates the entire data migration process including initialization,
    cursor-based pagination, data transformation, persistence, and error handling
    for all entity types: Client, Invoice, Quote, Note, and Attachment.
    Maintains single responsibility by delegating business logic to injected
    dependencies including specialized extractors.
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
        """Initialize MigrationCoordinator with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
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

    def _create_progress_display(self) -> Any:
        """Create console-based progress display (returns None for simple logging).

        Template Method Implementation: Console coordinator uses simple logging,
        so no display object is needed.

        Returns:
            None (console logging doesn't require display objects)
        """
        return None

    def _add_entity_task(
        self, display_obj: Any, entity_name: str, description: str
    ) -> Optional[Any]:
        """Add entity migration task using console logging.

        Template Method Implementation: Console coordinator logs task start
        and returns None since no task tracking object is needed.

        Args:
            display_obj: None (unused for console logging)
            entity_name: Name of entity type being migrated
            description: Initial task description

        Returns:
            None (console logging doesn't use task identifiers)
        """
        # Log task initiation using provided description
        # Remove Rich-specific formatting codes for clean console output
        clean_description = description.replace("[cyan]", "").replace("[green]", "")
        self._logger.info(f"Starting {entity_name} migration: {clean_description}")
        return None

    def _update_task_progress(
        self,
        display_obj: Any,
        task_id: Optional[Any],
        description: str,
        completed: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        """Update task progress using console logging.

        Template Method Implementation: Console coordinator logs progress updates
        but doesn't need to update any display objects.

        Args:
            display_obj: None (unused for console logging)
            task_id: None (unused for console logging)
            description: Updated task description
            completed: Current progress count (unused for console)
            total: Total expected count (unused for console)
        """
        # Console logging handles progress updates through existing logger calls
        # in the base class _migrate_clients() and _migrate_invoices() methods
        pass

    def _complete_task(
        self,
        display_obj: Any,
        task_id: Optional[Any],
        entity_name: str,
        final_count: int,
    ) -> None:
        """Mark task as completed using console logging.

        Template Method Implementation: Console coordinator logs completion
        with final entity count.

        Args:
            display_obj: None (unused for console logging)
            task_id: None (unused for console logging)
            entity_name: Name of entity type that was migrated
            final_count: Final number of entities processed
        """
        self._logger.info(
            f"✅ Completed {entity_name} migration: {final_count:,} entities processed"
        )

    def _start_display_context(self, display_obj: Any):
        """Start console display context (no-op context manager).

        Template Method Implementation: Console coordinator doesn't need
        special display lifecycle management, so returns nullcontext.

        Args:
            display_obj: None (unused for console logging)

        Returns:
            nullcontext (no-op context manager)
        """
        return nullcontext()
