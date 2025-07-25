"""Rich migration coordinator - simplified inheritance from BaseMigrationCoordinator."""

from typing import Optional

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
from ..repositories import Repository


class RichMigrationCoordinator(BaseMigrationCoordinator):
    """Enhanced migration coordinator with Rich progress bars and status displays.

    Simplified migration coordinator that inherits all Rich UI functionality
    from BaseMigrationCoordinator. Provides the same interface for backward
    compatibility while leveraging the unified Rich-based implementation.

    All Rich progress bars, error panels, and visual feedback are now handled
    directly by BaseMigrationCoordinator.
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
        # Initialize base class with all Rich functionality
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
