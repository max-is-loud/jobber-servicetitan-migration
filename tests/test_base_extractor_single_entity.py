"""Unit tests for BaseExtractor single-entity extraction functionality."""

from unittest.mock import Mock, patch

import pytest

from src.clients import JobberClient
from src.exceptions import ConfigurationError, JobberApiError, MappingError, RepositoryError
from src.extractors.clients_extractor import ClientsExtractor
from src.interfaces import Logger
from src.mappers import EntityMapper
from src.models import Attachment, Client, Note
from src.repositories import Repository


class TestBaseExtractorSingleEntity:
    """Test suite for BaseExtractor single-entity extraction methods."""

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient."""
        return Mock(spec=JobberClient)

    @pytest.fixture
    def mock_entity_mapper(self):
        """Create mock EntityMapper."""
        return Mock(spec=EntityMapper)

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository."""
        return Mock(spec=Repository)

    @pytest.fixture
    def mock_logger(self):
        """Create mock Logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        logger.warning = Mock()
        logger.error = Mock()
        return logger

    @pytest.fixture
    def extractor(self, mock_jobber_client, mock_entity_mapper, mock_repository, mock_logger):
        """Create ClientsExtractor instance for testing."""
        return ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
        )

    # ==================== Test extract_single() ====================

    def test_extract_single_successful_extraction(self, extractor, mock_entity_mapper, mock_repository):
        """Test extract_single successfully extracts entity with all related entities."""
        # Mock node data
        node = {
            "id": "client_123",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john@example.com",
        }

        # Mock entity
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
            additional_emails="[]",
            additional_phones="[]",
        )

        # Setup mocks
        with patch.object(extractor, "_fetch_single", return_value=node):
            with patch.object(extractor, "_map_entity", return_value=client):
                with patch.object(extractor, "_extract_related_entities", return_value={}):
                    result = extractor.extract_single("client_123")

        assert result["success"] is True
        assert result["entity_id"] == "client_123"
        assert result["entity_found"] is True
        assert result["error"] is None
        mock_repository.save_clients.assert_called_once_with([client])

    def test_extract_single_entity_not_found(self, extractor):
        """Test extract_single returns entity_found=False when entity not found."""
        with patch.object(extractor, "_fetch_single", return_value=None):
            result = extractor.extract_single("nonexistent_id")

        assert result["success"] is False
        assert result["entity_id"] == "nonexistent_id"
        assert result["entity_found"] is False
        assert "Entity not found" in result["error"]

    def test_extract_single_with_related_entities(self, extractor, mock_entity_mapper, mock_repository):
        """Test extract_single extracts and saves related entities."""
        node = {"id": "client_123", "firstName": "John"}
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
            additional_emails="[]",
            additional_phones="[]",
        )

        note = Note(
            id="note_1",
            entity_type="client",
            entity_id="client_123",
            message="Test note",
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )

        related_entities = {"notes": [note]}

        with patch.object(extractor, "_fetch_single", return_value=node):
            with patch.object(extractor, "_map_entity", return_value=client):
                with patch.object(extractor, "_extract_related_entities", return_value=related_entities):
                    with patch.object(extractor, "_save_related_entities") as mock_save_related:
                        result = extractor.extract_single("client_123")

        assert result["success"] is True
        mock_save_related.assert_called_once_with(related_entities)

    def test_extract_single_mapping_error(self, extractor):
        """Test extract_single handles mapping errors."""
        node = {"id": "client_123"}

        with patch.object(extractor, "_fetch_single", return_value=node):
            with patch.object(extractor, "_map_entity", side_effect=MappingError("Invalid data")):
                result = extractor.extract_single("client_123")

        assert result["success"] is False
        assert result["entity_id"] == "client_123"
        assert result["entity_found"] is True
        assert "Mapping error" in result["error"]
        assert "Invalid data" in result["error"]

    def test_extract_single_repository_error(self, extractor, mock_repository):
        """Test extract_single handles repository errors."""
        node = {"id": "client_123"}
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
            additional_emails="[]",
            additional_phones="[]",
        )

        with patch.object(extractor, "_fetch_single", return_value=node):
            with patch.object(extractor, "_map_entity", return_value=client):
                with patch.object(extractor, "_extract_related_entities", return_value={}):
                    mock_repository.save_clients.side_effect = RepositoryError("Database error")
                    result = extractor.extract_single("client_123")

        assert result["success"] is False
        assert result["entity_id"] == "client_123"
        assert "Repository error" in result["error"]
        assert "Database error" in result["error"]

    def test_extract_single_unexpected_error(self, extractor):
        """Test extract_single handles unexpected errors."""
        with patch.object(extractor, "_fetch_single", side_effect=Exception("Unexpected error")):
            result = extractor.extract_single("client_123")

        assert result["success"] is False
        assert result["entity_id"] == "client_123"
        assert result["entity_found"] is False
        assert "Unexpected error" in result["error"]

    def test_extract_single_return_value_structure(self, extractor):
        """Test extract_single returns correct dictionary structure."""
        node = {"id": "client_123"}
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
            additional_emails="[]",
            additional_phones="[]",
        )

        with patch.object(extractor, "_fetch_single", return_value=node):
            with patch.object(extractor, "_map_entity", return_value=client):
                with patch.object(extractor, "_extract_related_entities", return_value={}):
                    result = extractor.extract_single("client_123")

        # Verify all expected keys are present
        assert "success" in result
        assert "entity_id" in result
        assert "entity_found" in result
        assert "error" in result

        # Verify types
        assert isinstance(result["success"], bool)
        assert isinstance(result["entity_id"], str)
        assert isinstance(result["entity_found"], bool)

    # ==================== Test _fetch_single() default implementation ====================

    def test_fetch_single_default_implementation(self, extractor, mock_jobber_client):
        """Test _fetch_single default implementation fetches page and filters by ID."""
        response = {
            "data": {
                "clients": {
                    "edges": [
                        {"node": {"id": "client_1", "firstName": "John"}},
                        {"node": {"id": "client_123", "firstName": "Jane"}},
                    ],
                    "pageInfo": {"hasNextPage": False},
                }
            }
        }
        mock_jobber_client.fetch_clients.return_value = response

        result = extractor._fetch_single("client_123")

        assert result is not None
        assert result["id"] == "client_123"
        assert result["firstName"] == "Jane"

    def test_fetch_single_not_found_in_page(self, extractor, mock_jobber_client):
        """Test _fetch_single returns None when entity not in page."""
        response = {
            "data": {
                "clients": {
                    "edges": [
                        {"node": {"id": "client_1", "firstName": "John"}},
                        {"node": {"id": "client_2", "firstName": "Jane"}},
                    ],
                    "pageInfo": {"hasNextPage": False},
                }
            }
        }
        mock_jobber_client.fetch_clients.return_value = response

        result = extractor._fetch_single("client_999")

        assert result is None

    def test_fetch_single_handles_api_error(self, extractor, mock_jobber_client):
        """Test _fetch_single handles API errors gracefully."""
        mock_jobber_client.fetch_clients.side_effect = JobberApiError("API error")

        result = extractor._fetch_single("client_123")

        # Should return None on error (logged but not raised)
        assert result is None


class TestAttachmentQueuing:
    """Test suite for attachment queuing functionality."""

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient."""
        return Mock(spec=JobberClient)

    @pytest.fixture
    def mock_entity_mapper(self):
        """Create mock EntityMapper."""
        return Mock(spec=EntityMapper)

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository."""
        return Mock(spec=Repository)

    @pytest.fixture
    def mock_logger(self):
        """Create mock Logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        logger.warning = Mock()
        logger.error = Mock()
        return logger

    @pytest.fixture
    def extractor_with_queuing(self, mock_jobber_client, mock_entity_mapper, mock_repository, mock_logger):
        """Create extractor with attachment queuing enabled."""
        return ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            queue_attachments=True,
            map_snapshot_id="snapshot_123",
        )

    @pytest.fixture
    def extractor_without_queuing(self, mock_jobber_client, mock_entity_mapper, mock_repository, mock_logger):
        """Create extractor without attachment queuing."""
        return ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            queue_attachments=False,
        )

    # ==================== Test _queue_attachments_for_download() ====================

    def test_queue_attachments_valid_attachments(self, extractor_with_queuing, mock_repository):
        """Test _queue_attachments_for_download queues attachments correctly."""
        attachments = [
            Attachment(
                id="attach_1",
                note_id="client_123_note_1",
                file_name="file1.pdf",
                content_type="application/pdf",
                original_url="https://example.com/file1.pdf",
                local_file_path=None,
                file_size=1024,
                created_at="2023-11-15T10:00:00Z",
            ),
            Attachment(
                id="attach_2",
                note_id="client_456_note_2",
                file_name="file2.jpg",
                content_type="image/jpeg",
                original_url="https://example.com/file2.jpg",
                local_file_path=None,
                file_size=2048,
                created_at="2023-11-15T10:00:00Z",
            ),
        ]

        extractor_with_queuing._queue_attachments_for_download(attachments)

        # Verify attachments were saved
        mock_repository.save_attachments.assert_called_once_with(attachments)

        # Verify queue items were created
        mock_repository.create_attachment_queue.assert_called_once()
        call_args = mock_repository.create_attachment_queue.call_args
        assert call_args[1]["snapshot_id"] == "snapshot_123"
        assert len(call_args[1]["attachments"]) == 2

    def test_queue_attachments_parses_parent_type_and_id(self, extractor_with_queuing, mock_repository):
        """Test _queue_attachments_for_download correctly parses parent info from note_id."""
        attachments = [
            Attachment(
                id="attach_1",
                note_id="client_123_note_1",
                file_name="file.pdf",
                content_type="application/pdf",
                original_url="https://example.com/file.pdf",
                local_file_path=None,
                file_size=1024,
                created_at="2023-11-15T10:00:00Z",
            ),
        ]

        extractor_with_queuing._queue_attachments_for_download(attachments)

        call_args = mock_repository.create_attachment_queue.call_args
        queue_items = call_args[1]["attachments"]
        assert queue_items[0]["parent_type"] == "clients"
        assert queue_items[0]["parent_id"] == "123"
        assert queue_items[0]["attachment_id"] == "attach_1"

    def test_queue_attachments_without_map_snapshot_id_raises_error(self, mock_jobber_client, mock_entity_mapper, mock_repository, mock_logger):
        """Test _queue_attachments_for_download raises ConfigurationError if map_snapshot_id not set."""
        extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            queue_attachments=True,
            # No map_snapshot_id provided
        )

        attachments = [
            Attachment(
                id="attach_1",
                note_id="client_123_note_1",
                file_name="file.pdf",
                content_type="application/pdf",
                original_url="https://example.com/file.pdf",
                local_file_path=None,
                file_size=1024,
                created_at="2023-11-15T10:00:00Z",
            ),
        ]

        with pytest.raises(ConfigurationError, match="map_snapshot_id is required"):
            extractor._queue_attachments_for_download(attachments)

    def test_queue_attachments_tracks_queued_count(self, extractor_with_queuing, mock_repository):
        """Test _queue_attachments_for_download tracks queued count."""
        attachments = [
            Attachment(
                id=f"attach_{i}",
                note_id=f"client_123_note_{i}",
                file_name=f"file{i}.pdf",
                content_type="application/pdf",
                original_url=f"https://example.com/file{i}.pdf",
                local_file_path=None,
                file_size=1024,
                created_at="2023-11-15T10:00:00Z",
            )
            for i in range(5)
        ]

        extractor_with_queuing._queue_attachments_for_download(attachments)

        assert extractor_with_queuing._attachments_queued == 5

    # ==================== Test _save_notes_and_attachments() with queuing ====================

    def test_save_notes_and_attachments_queuing_mode(self, extractor_with_queuing, mock_repository):
        """Test _save_notes_and_attachments queues attachments when queue_attachments=True."""
        note = Note(
            id="note_1",
            entity_type="client",
            entity_id="client_123",
            message="Test note",
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )

        attachment = Attachment(
            id="attach_1",
            note_id="client_123_note_1",
            file_name="file.pdf",
            content_type="application/pdf",
            original_url="https://example.com/file.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )

        related_entities = {"notes": [note], "attachments": [attachment]}

        with patch.object(extractor_with_queuing, "_queue_attachments_for_download") as mock_queue:
            extractor_with_queuing._save_notes_and_attachments(related_entities)

        # Verify notes were saved
        mock_repository.save_notes.assert_called_once_with([note])

        # Verify attachments were queued (not downloaded)
        mock_queue.assert_called_once_with([attachment])

    def test_save_notes_and_attachments_download_mode(self, extractor_without_queuing, mock_repository):
        """Test _save_notes_and_attachments downloads attachments when queue_attachments=False."""
        note = Note(
            id="note_1",
            entity_type="client",
            entity_id="client_123",
            message="Test note",
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )

        attachment = Attachment(
            id="attach_1",
            note_id="client_123_note_1",
            file_name="file.pdf",
            content_type="application/pdf",
            original_url="https://example.com/file.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )

        related_entities = {"notes": [note], "attachments": [attachment]}

        with patch.object(extractor_without_queuing, "_attachment_downloader") as mock_downloader:
            mock_downloader.download_attachment.return_value = {
                "success": True,
                "local_file_path": "/path/to/file.pdf",
                "bytes_downloaded": 1024,
            }

            extractor_without_queuing._save_notes_and_attachments(related_entities)

        # Verify notes were saved
        mock_repository.save_notes.assert_called_once_with([note])

        # Verify attachments were downloaded (not queued)
        mock_downloader.download_attachment.assert_called_once_with(attachment)

    def test_save_notes_and_attachments_mixed_notes_and_attachments(self, extractor_with_queuing, mock_repository):
        """Test _save_notes_and_attachments handles mixed notes and attachments."""
        notes = [
            Note(
                id=f"note_{i}",
                entity_type="client",
                entity_id="client_123",
                message=f"Test note {i}",
                created_at="2023-11-15T10:00:00Z",
                updated_at="2023-11-15T10:00:00Z",
            )
            for i in range(3)
        ]

        attachments = [
            Attachment(
                id=f"attach_{i}",
                note_id=f"client_123_note_{i}",
                file_name=f"file{i}.pdf",
                content_type="application/pdf",
                original_url=f"https://example.com/file{i}.pdf",
                local_file_path=None,
                file_size=1024,
                created_at="2023-11-15T10:00:00Z",
            )
            for i in range(2)
        ]

        related_entities = {"notes": notes, "attachments": attachments}

        with patch.object(extractor_with_queuing, "_queue_attachments_for_download") as mock_queue:
            extractor_with_queuing._save_notes_and_attachments(related_entities)

        # Verify correct counts
        mock_repository.save_notes.assert_called_once()
        assert len(mock_repository.save_notes.call_args[0][0]) == 3
        mock_queue.assert_called_once()
        assert len(mock_queue.call_args[0][0]) == 2
