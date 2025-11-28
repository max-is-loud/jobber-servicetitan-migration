"""Unit tests for NotesExtractor."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from src.extractors.notes_extractor import NotesExtractor
from src.clients import JobberClient
from src.mappers import EntityMapper
from src.repositories import Repository
from src.interfaces import Logger
from src.config import ConfigManagerImpl
from src.models import Note


class TestNotesExtractor:
    """Test suite for NotesExtractor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JobberClient)
        self.mock_mapper = Mock(spec=EntityMapper)
        self.mock_repository = Mock(spec=Repository)
        self.mock_logger = Mock(spec=Logger)
        self.mock_config_manager = MagicMock()  # Use MagicMock for flexible mocking

        # Configure config manager defaults
        self.mock_config_manager.get_batch_size.return_value = 50
        self.mock_config_manager.get_delay_between_requests.return_value = 0.1

    def test_init_with_kwargs(self):
        """Test initialization with optional kwargs."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
            config_manager=self.mock_config_manager,
            skip_existing_entities=True,
        )

        assert extractor._jobber_client == self.mock_client
        assert extractor._entity_mapper == self.mock_mapper
        assert extractor._repository == self.mock_repository
        assert extractor._logger == self.mock_logger
        assert extractor._config_manager == self.mock_config_manager
        assert extractor._skip_existing_entities is True
        assert extractor._entity_name == "note"

    def test_init_defaults(self):
        """Test initialization with default values."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

        assert extractor._skip_existing_entities is False
        assert extractor._config_manager is not None

    def test_fetch_page_returns_empty(self):
        """Test _fetch_page returns empty result (deferred loading pattern)."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

        result = extractor._fetch_page(cursor=None)

        assert result == {
            "data": {
                "notes": {"edges": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}
            }
        }

    def test_extract_edges_and_page_info(self):
        """Test extracting edges and page info from API response."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

        response = {
            "data": {
                "notes": {
                    "edges": [{"node": {"id": "1", "message": "Test note"}}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor123"},
                }
            }
        }

        edges, page_info = extractor._extract_edges_and_page_info(response)

        assert len(edges) == 1
        assert edges[0]["node"]["id"] == "1"
        assert page_info["hasNextPage"] is True
        assert page_info["endCursor"] == "cursor123"

    def test_map_entity(self):
        """Test mapping a GraphQL node to Note domain model."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

        mock_note = Note(
            id="note123",
            entity_type="Client",
            entity_id="client456",
            message="Test note message",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        self.mock_mapper.map_note.return_value = mock_note

        node = {"id": "note123", "message": "Test note message"}
        result = extractor._map_entity(node)

        assert result == mock_note
        self.mock_mapper.map_note.assert_called_once_with(node)

    def test_save_entities(self):
        """Test saving notes to repository."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

        notes = [
            Note(
                id="note1",
                entity_type="Client",
                entity_id="client1",
                message="Note 1",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
            Note(
                id="note2",
                entity_type="Job",
                entity_id="job1",
                message="Note 2",
                created_at="2024-01-02T00:00:00Z",
                updated_at="2024-01-02T00:00:00Z",
            ),
        ]

        extractor._save_entities(notes)

        self.mock_repository.save_notes.assert_called_once_with(notes)
        assert extractor._last_batch_entities == notes

    def test_get_entities_from_last_batch(self):
        """Test retrieving notes from last batch."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

        notes = [
            Note(
                id="note1",
                entity_type="Client",
                entity_id="client1",
                message="Note 1",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
        ]

        extractor._last_batch_entities = notes
        result = extractor._get_entities_from_last_batch()

        assert result == notes

    @patch("time.sleep")
    def test_extract_deferred_notes_basic(self, mock_sleep):
        """Test basic deferred notes extraction with single batch."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
            config_manager=self.mock_config_manager,
        )

        # Setup note references
        note_references = [
            {"note_id": "note1", "entity_type": "Client", "entity_id": "client1"},
            {"note_id": "note2", "entity_type": "Job", "entity_id": "job1"},
        ]

        # Mock GraphQL response
        mock_response = {
            "data": {
                "node": {
                    "id": "note1",
                    "message": "Test note",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-01T00:00:00Z",
                }
            }
        }
        self.mock_client.fetch_note_by_id.side_effect = [mock_response, mock_response]

        # Mock entity mapper
        mock_note1 = Note(
            id="note1",
            entity_type="Client",
            entity_id="client1",
            message="Test note 1",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        mock_note2 = Note(
            id="note2",
            entity_type="Job",
            entity_id="job1",
            message="Test note 2",
            created_at="2024-01-02T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
        )
        self.mock_mapper.map_note.side_effect = [mock_note1, mock_note2]

        # Execute
        result = extractor.extract_deferred_notes(note_references)

        # Verify
        assert result["processed"] == 2
        assert result["skipped"] == 0

        # Verify GraphQL calls
        assert self.mock_client.fetch_note_by_id.call_count == 2

        # Verify save calls
        self.mock_repository.save_notes.assert_called()

    @patch("time.sleep")
    def test_extract_deferred_notes_with_skip(self, mock_sleep):
        """Test deferred notes extraction with skip_existing_entities enabled."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
            config_manager=self.mock_config_manager,
            skip_existing_entities=True,
        )

        # Setup note references
        note_references = [
            {"note_id": "note1", "entity_type": "Client", "entity_id": "client1"},
            {"note_id": "note2", "entity_type": "Job", "entity_id": "job1"},
        ]

        # Mock note1 exists, note2 doesn't (using _should_skip_entity which checks repository)
        extractor._should_skip_entity = Mock(side_effect=[True, False])

        # Mock GraphQL response for note2 only
        mock_response = {
            "data": {
                "node": {
                    "id": "note2",
                    "message": "Test note 2",
                    "createdAt": "2024-01-02T00:00:00Z",
                    "updatedAt": "2024-01-02T00:00:00Z",
                }
            }
        }
        self.mock_client.fetch_note_by_id.return_value = mock_response

        # Mock entity mapper for note2
        mock_note2 = Note(
            id="note2",
            entity_type="Job",
            entity_id="job1",
            message="Test note 2",
            created_at="2024-01-02T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
        )
        self.mock_mapper.map_note.return_value = mock_note2

        # Execute
        result = extractor.extract_deferred_notes(note_references)

        # Verify
        assert result["processed"] == 1
        assert result["skipped"] == 1

        # Verify GraphQL called only once (for note2)
        assert self.mock_client.fetch_note_by_id.call_count == 1

    @patch("time.sleep")
    def test_extract_deferred_notes_handles_errors(self, mock_sleep):
        """Test deferred notes extraction handles API errors gracefully."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
            config_manager=self.mock_config_manager,
        )

        # Setup note references
        note_references = [
            {"note_id": "note1", "entity_type": "Client", "entity_id": "client1"},
            {"note_id": "note2", "entity_type": "Job", "entity_id": "job1"},
        ]

        # First call succeeds, second fails
        mock_success_response = {
            "data": {
                "node": {
                    "id": "note1",
                    "message": "Test note 1",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-01T00:00:00Z",
                }
            }
        }

        self.mock_client.fetch_note_by_id.side_effect = [
            mock_success_response,
            Exception("API Error"),
        ]

        # Mock entity mapper for note1
        mock_note1 = Note(
            id="note1",
            entity_type="Client",
            entity_id="client1",
            message="Test note 1",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        self.mock_mapper.map_note.return_value = mock_note1

        # Execute
        result = extractor.extract_deferred_notes(note_references)

        # Verify - should continue processing despite error
        # Note: errors are logged but don't affect the counts, second note just isn't processed
        assert result["processed"] == 1
        assert result["skipped"] == 0

        # Verify error was logged (using debug level)
        self.mock_logger.debug.assert_called()
        # Check that error message was in one of the debug calls
        debug_calls = [str(call) for call in self.mock_logger.debug.call_args_list]
        assert any("Failed to process note" in str(call) for call in debug_calls)

    @patch("time.sleep")
    def test_extract_deferred_notes_empty_references(self, mock_sleep):
        """Test deferred notes extraction with empty references list."""
        extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
            config_manager=self.mock_config_manager,
        )

        # Execute with empty list
        result = extractor.extract_deferred_notes([])

        # Verify
        assert result["processed"] == 0
        assert result["skipped"] == 0

        # Verify no API calls
        self.mock_client.fetch_note_by_id.assert_not_called()
