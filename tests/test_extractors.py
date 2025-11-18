"""Unit tests for entity extractors."""

from unittest.mock import Mock, MagicMock, patch, call
import pytest

from src.extractors.jobs_extractor import JobsExtractor
from src.extractors.users_extractor import UsersExtractor
from src.extractors.quotes_extractor import QuotesExtractor
from src.extractors.properties_extractor import PropertiesExtractor
from src.clients import JobberClient
from src.mappers import EntityMapper
from src.repositories import Repository
from src.interfaces import Logger
from src.models import Job, User, Quote, Property, Note
from src.exceptions import MappingError, JobberApiError


# Helper functions to create test entities
def create_test_job(**kwargs):
    """Create a Job instance with default values for testing."""
    defaults = {
        "id": "job_123",
        "client_id": "client_123",
        "property_id": "prop_123",
        "quote_id": "quote_123",
        "job_number": "J-001",
        "title": "Test Job",
        "description": "Test description",
        "status": "pending",
        "scheduled_start_at": "2023-11-15T10:00:00Z",
        "scheduled_end_at": "2023-11-15T12:00:00Z",
        "completed_at": "",
        "total": 10000,
        "created_at": "2023-11-15T10:00:00Z",
        "updated_at": "2023-11-15T10:00:00Z",
    }
    defaults.update(kwargs)
    return Job(**defaults)


def create_test_user(**kwargs):
    """Create a User instance with default values for testing."""
    defaults = {
        "id": "user_123",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "role": "admin",
        "is_account_admin": "true",
        "is_account_owner": "false",
        "status": "active",
        "phone": "555-0100",
        "timezone": "America/New_York",
        "created_at": "2023-11-15T10:00:00Z",
        "last_login_at": "2023-11-16T10:00:00Z",
    }
    defaults.update(kwargs)
    return User(**defaults)


def create_test_property(**kwargs):
    """Create a Property instance with default values for testing."""
    defaults = {
        "id": "prop_123",
        "client_id": "client_123",
        "name": "Main Office",
        "address_line1": "123 Main St",
        "address_line2": "",
        "city": "Anytown",
        "state_province": "CA",
        "postal_code": "12345",
        "country": "USA",
        "latitude": "37.7749",
        "longitude": "-122.4194",
        "created_at": "2023-11-15T10:00:00Z",
        "updated_at": "2023-11-15T10:00:00Z",
    }
    defaults.update(kwargs)
    return Property(**defaults)


class TestJobsExtractor:
    """Test suite for JobsExtractor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JobberClient)
        self.mock_mapper = Mock(spec=EntityMapper)
        self.mock_repository = Mock(spec=Repository)
        self.mock_logger = Mock(spec=Logger)

        self.extractor = JobsExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

    def test_init_creates_extractor(self):
        """Test JobsExtractor initialization."""
        assert self.extractor._jobber_client == self.mock_client
        assert self.extractor._entity_mapper == self.mock_mapper
        assert self.extractor._repository == self.mock_repository
        assert self.extractor._logger == self.mock_logger
        assert self.extractor._entity_name == "job"

    def test_fetch_page_calls_client_fetch_jobs(self):
        """Test _fetch_page calls jobber_client.fetch_jobs."""
        expected_response = {"data": {"jobs": {"edges": []}}}
        self.mock_client.fetch_jobs.return_value = expected_response

        result = self.extractor._fetch_page(cursor="test_cursor")

        self.mock_client.fetch_jobs.assert_called_once_with("test_cursor")
        assert result == expected_response

    def test_fetch_page_without_cursor(self):
        """Test _fetch_page without cursor."""
        expected_response = {"data": {"jobs": {"edges": []}}}
        self.mock_client.fetch_jobs.return_value = expected_response

        result = self.extractor._fetch_page()

        self.mock_client.fetch_jobs.assert_called_once_with(None)
        assert result == expected_response

    def test_extract_edges_and_page_info(self):
        """Test _extract_edges_and_page_info extracts correctly."""
        response = {
            "data": {
                "jobs": {
                    "edges": [
                        {"node": {"id": "job_1"}},
                        {"node": {"id": "job_2"}},
                    ],
                    "pageInfo": {
                        "hasNextPage": True,
                        "endCursor": "cursor_abc",
                    },
                }
            }
        }

        edges, page_info = self.extractor._extract_edges_and_page_info(response)

        assert len(edges) == 2
        assert edges[0]["node"]["id"] == "job_1"
        assert page_info["hasNextPage"] is True
        assert page_info["endCursor"] == "cursor_abc"

    def test_extract_edges_and_page_info_empty_response(self):
        """Test _extract_edges_and_page_info with empty response."""
        response = {"data": {}}

        edges, page_info = self.extractor._extract_edges_and_page_info(response)

        assert edges == []
        assert page_info == {}

    def test_map_entity_calls_mapper(self):
        """Test _map_entity calls entity_mapper.map_job."""
        node = {"id": "job_123", "title": "Test Job"}
        expected_job = create_test_job(id="job_123", title="Test Job")
        self.mock_mapper.map_job.return_value = expected_job

        result = self.extractor._map_entity(node)

        self.mock_mapper.map_job.assert_called_once_with(node)
        assert result == expected_job

    def test_save_entities_calls_repository(self):
        """Test _save_entities calls repository.save_jobs."""
        jobs = [
            create_test_job(id="job_1", client_id="c1", title="Job 1"),
            create_test_job(id="job_2", client_id="c2", title="Job 2"),
        ]

        self.extractor._save_entities(jobs)

        self.mock_repository.save_jobs.assert_called_once_with(jobs)
        assert self.extractor._last_batch_entities == jobs

    def test_extract_related_entities_extracts_notes(self):
        """Test _extract_related_entities extracts job notes."""
        job = create_test_job(id="job_123", client_id="c1", title="Test")
        node = {
            "id": "job_123",
            "notes": {
                "edges": [
                    {
                        "node": {
                            "id": "note_1",
                            "message": "Test note",
                            "createdAt": "2023-11-15T10:00:00Z",
                        }
                    },
                ]
            },
        }

        expected_note = Note(
            id="note_1",
            entity_type="Job",
            entity_id="job_123",
            message="Test note",
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )
        self.mock_mapper.map_note.return_value = expected_note

        result = self.extractor._extract_related_entities(node, job)

        assert "notes" in result
        assert len(result["notes"]) == 1
        assert result["notes"][0] == expected_note

    def test_extract_related_entities_no_notes(self):
        """Test _extract_related_entities with no notes."""
        job = create_test_job(id="job_123", client_id="c1", title="Test")
        node = {"id": "job_123"}

        result = self.extractor._extract_related_entities(node, job)

        assert result == {}

    def test_extract_related_entities_handles_mapping_error(self):
        """Test _extract_related_entities handles mapping errors gracefully."""
        job = create_test_job(id="job_123", client_id="c1", title="Test")
        node = {
            "id": "job_123",
            "notes": {
                "edges": [
                    {"node": {"id": "note_1", "message": "Test"}},
                ]
            },
        }

        self.mock_mapper.map_note.side_effect = MappingError("Invalid note data")

        result = self.extractor._extract_related_entities(node, job)

        # Should return empty dict when all notes fail to map
        assert result == {}

    def test_save_related_entities_saves_notes(self):
        """Test _save_related_entities saves notes."""
        notes = [
            Note(
                id="note_1",
                entity_type="Job",
                entity_id="job_123",
                message="Test",
                created_at="2023-11-15T10:00:00Z",
                updated_at="2023-11-15T10:00:00Z",
            ),
        ]
        related = {"notes": notes}

        self.extractor._save_related_entities(related)

        self.mock_repository.save_notes.assert_called_once_with(notes)

    def test_save_related_entities_no_notes(self):
        """Test _save_related_entities with no notes."""
        self.extractor._save_related_entities({})

        self.mock_repository.save_notes.assert_not_called()

    def test_get_entities_from_last_batch(self):
        """Test _get_entities_from_last_batch returns last batch."""
        jobs = [
            create_test_job(id="job_1", client_id="c1", title="Job 1"),
        ]
        self.extractor._last_batch_entities = jobs

        result = self.extractor._get_entities_from_last_batch()

        assert result == jobs

    def test_get_entity_count_with_total_count(self):
        """Test get_entity_count when API provides totalCount."""
        response = {
            "data": {
                "jobs": {
                    "totalCount": 150,
                    "edges": [],
                    "pageInfo": {},
                }
            }
        }
        self.mock_client.fetch_jobs.return_value = response

        result = self.extractor.get_entity_count()

        assert result == 150

    def test_get_entity_count_without_total_count_single_page(self):
        """Test get_entity_count without totalCount, single page."""
        response = {
            "data": {
                "jobs": {
                    "edges": [{"node": {"id": f"job_{i}"}} for i in range(10)],
                    "pageInfo": {"hasNextPage": False},
                }
            }
        }
        self.mock_client.fetch_jobs.return_value = response

        result = self.extractor.get_entity_count()

        assert result == 10

    def test_get_entity_count_without_total_count_multiple_pages(self):
        """Test get_entity_count without totalCount, multiple pages."""
        response = {
            "data": {
                "jobs": {
                    "edges": [{"node": {"id": f"job_{i}"}} for i in range(30)],
                    "pageInfo": {"hasNextPage": True},
                }
            }
        }
        self.mock_client.fetch_jobs.return_value = response

        result = self.extractor.get_entity_count()

        # Should return -1 when exact count unknown
        assert result == -1

    def test_get_entity_count_empty_result(self):
        """Test get_entity_count with no jobs."""
        response = {
            "data": {
                "jobs": {
                    "edges": [],
                    "pageInfo": {"hasNextPage": False},
                }
            }
        }
        self.mock_client.fetch_jobs.return_value = response

        result = self.extractor.get_entity_count()

        assert result == 0


class TestUsersExtractor:
    """Test suite for UsersExtractor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JobberClient)
        self.mock_mapper = Mock(spec=EntityMapper)
        self.mock_repository = Mock(spec=Repository)
        self.mock_logger = Mock(spec=Logger)

        self.extractor = UsersExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
            skip_existing_entities=False,
        )

    def test_init_creates_extractor(self):
        """Test UsersExtractor initialization."""
        assert self.extractor._jobber_client == self.mock_client
        assert self.extractor._entity_mapper == self.mock_mapper
        assert self.extractor._repository == self.mock_repository
        assert self.extractor._logger == self.mock_logger
        assert self.extractor._entity_name == "user"

    def test_init_with_skip_existing_entities(self):
        """Test UsersExtractor with skip_existing_entities flag."""
        extractor = UsersExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
            skip_existing_entities=True,
        )

        assert extractor._skip_existing_entities is True

    def test_fetch_page_calls_client_fetch_users(self):
        """Test _fetch_page calls jobber_client.fetch_users."""
        expected_response = {"data": {"users": {"edges": []}}}
        self.mock_client.fetch_users.return_value = expected_response

        result = self.extractor._fetch_page(cursor="test_cursor")

        self.mock_client.fetch_users.assert_called_once_with("test_cursor")
        assert result == expected_response

    def test_extract_edges_and_page_info(self):
        """Test _extract_edges_and_page_info extracts correctly."""
        response = {
            "data": {
                "users": {
                    "edges": [
                        {"node": {"id": "user_1"}},
                        {"node": {"id": "user_2"}},
                    ],
                    "pageInfo": {
                        "hasNextPage": True,
                        "endCursor": "cursor_xyz",
                    },
                }
            }
        }

        edges, page_info = self.extractor._extract_edges_and_page_info(response)

        assert len(edges) == 2
        assert edges[0]["node"]["id"] == "user_1"
        assert page_info["hasNextPage"] is True
        assert page_info["endCursor"] == "cursor_xyz"

    def test_map_entity_calls_mapper(self):
        """Test _map_entity calls entity_mapper.map_user."""
        node = {"id": "user_123", "name": {"first": "John", "last": "Doe"}}
        expected_user = create_test_user(id="user_123", first_name="John", last_name="Doe", email="john@example.com")
        self.mock_mapper.map_user.return_value = expected_user

        result = self.extractor._map_entity(node)

        self.mock_mapper.map_user.assert_called_once_with(node)
        assert result == expected_user

    def test_save_entities_calls_repository(self):
        """Test _save_entities calls repository.save_users."""
        users = [
            create_test_user(id="user_1", first_name="John", last_name="Doe", email="j@e.com"),
            create_test_user(id="user_2", first_name="Jane", last_name="Smith", email="jane@e.com"),
        ]

        self.extractor._save_entities(users)

        self.mock_repository.save_users.assert_called_once_with(users)
        assert self.extractor._last_batch_entities == users

    def test_extract_related_entities_extracts_notes(self):
        """Test _extract_related_entities extracts user notes."""
        user = create_test_user(id="user_123", first_name="John", last_name="Doe", email="j@e.com")
        node = {
            "id": "user_123",
            "notes": {
                "edges": [
                    {
                        "node": {
                            "id": "note_1",
                            "message": "Performance review",
                            "createdAt": "2023-11-15T10:00:00Z",
                        }
                    },
                ]
            },
        }

        expected_note = Note(
            id="note_1",
            entity_type="User",
            entity_id="user_123",
            message="Performance review",
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )
        self.mock_mapper.map_note.return_value = expected_note

        result = self.extractor._extract_related_entities(node, user)

        assert "notes" in result
        assert len(result["notes"]) == 1
        assert result["notes"][0] == expected_note

    def test_get_entity_count_with_total_count(self):
        """Test get_entity_count when API provides totalCount."""
        response = {
            "data": {
                "users": {
                    "totalCount": 25,
                    "edges": [],
                    "pageInfo": {},
                }
            }
        }
        self.mock_client.fetch_users.return_value = response

        result = self.extractor.get_entity_count()

        assert result == 25


class TestQuotesExtractor:
    """Test suite for QuotesExtractor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JobberClient)
        self.mock_mapper = Mock(spec=EntityMapper)
        self.mock_repository = Mock(spec=Repository)
        self.mock_logger = Mock(spec=Logger)

        self.extractor = QuotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

    def test_init_creates_extractor(self):
        """Test QuotesExtractor initialization."""
        assert self.extractor._jobber_client == self.mock_client
        assert self.extractor._entity_mapper == self.mock_mapper
        assert self.extractor._repository == self.mock_repository
        assert self.extractor._logger == self.mock_logger
        assert self.extractor._entity_name == "quote"

    def test_fetch_page_calls_client_fetch_quotes(self):
        """Test _fetch_page calls jobber_client.fetch_quotes."""
        expected_response = {"data": {"quotes": {"edges": []}}}
        self.mock_client.fetch_quotes.return_value = expected_response

        result = self.extractor._fetch_page(cursor="test_cursor")

        self.mock_client.fetch_quotes.assert_called_once_with("test_cursor")
        assert result == expected_response

    def test_map_entity_calls_mapper(self):
        """Test _map_entity calls entity_mapper.map_quote."""
        node = {"id": "quote_123", "title": "Lawn Care"}
        expected_quote = Quote(
            id="quote_123",
            client_id="client_123",
            quote_number="Q-001",
            title="Lawn Care",
            total=50000,
            subtotal=45000,
            disclaimer="",
            line_items="[]",
            created_at="2023-11-15T10:00:00Z",
            transitioned_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )
        self.mock_mapper.map_quote.return_value = expected_quote

        result = self.extractor._map_entity(node)

        self.mock_mapper.map_quote.assert_called_once_with(node)
        assert result == expected_quote

    def test_save_entities_calls_repository(self):
        """Test _save_entities calls repository.save_quotes."""
        quotes = [
            Quote(
                id="quote_1",
                client_id="c1",
                quote_number="Q-001",
                title="Service 1",
                total=50000,
                subtotal=45000,
                disclaimer="",
                line_items="[]",
                created_at="2023-11-15T10:00:00Z",
                transitioned_at="2023-11-15T10:00:00Z",
                updated_at="2023-11-15T10:00:00Z",
            ),
        ]

        self.extractor._save_entities(quotes)

        self.mock_repository.save_quotes.assert_called_once_with(quotes)


class TestPropertiesExtractor:
    """Test suite for PropertiesExtractor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JobberClient)
        self.mock_mapper = Mock(spec=EntityMapper)
        self.mock_repository = Mock(spec=Repository)
        self.mock_logger = Mock(spec=Logger)

        self.extractor = PropertiesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

    def test_init_creates_extractor(self):
        """Test PropertiesExtractor initialization."""
        assert self.extractor._jobber_client == self.mock_client
        assert self.extractor._entity_mapper == self.mock_mapper
        assert self.extractor._repository == self.mock_repository
        assert self.extractor._logger == self.mock_logger
        assert self.extractor._entity_name == "property"

    def test_fetch_page_calls_client_fetch_properties(self):
        """Test _fetch_page calls jobber_client.fetch_properties."""
        expected_response = {"data": {"properties": {"edges": []}}}
        self.mock_client.fetch_properties.return_value = expected_response

        result = self.extractor._fetch_page(cursor="test_cursor")

        self.mock_client.fetch_properties.assert_called_once_with("test_cursor")
        assert result == expected_response

    def test_map_entity_calls_mapper(self):
        """Test _map_entity calls entity_mapper.map_property."""
        node = {"id": "property_123", "address": "123 Main St"}
        expected_property = create_test_property(id="property_123", address_line1="123 Main St")
        self.mock_mapper.map_property.return_value = expected_property

        result = self.extractor._map_entity(node)

        self.mock_mapper.map_property.assert_called_once_with(node)
        assert result == expected_property

    def test_save_entities_calls_repository(self):
        """Test _save_entities calls repository.save_properties."""
        properties = [
            create_test_property(id="prop_1", client_id="c1", address_line1="123 Main St"),
        ]

        self.extractor._save_entities(properties)

        self.mock_repository.save_properties.assert_called_once_with(properties)

    def test_extract_related_entities_returns_empty(self):
        """Test _extract_related_entities returns empty dict.

        Properties don't have related notes or complex relationships,
        so _extract_related_entities always returns an empty dict.
        """
        prop = create_test_property(id="prop_123", client_id="c1", address_line1="123 Main St")
        node = {
            "id": "prop_123",
            "notes": {
                "edges": [
                    {
                        "node": {
                            "id": "note_1",
                            "message": "Needs gate code",
                            "createdAt": "2023-11-15T10:00:00Z",
                        }
                    },
                ]
            },
        }

        result = self.extractor._extract_related_entities(node, prop)

        # Properties don't support notes, should return empty dict
        assert result == {}
        assert "notes" not in result


class TestExtractorErrorHandling:
    """Test suite for extractor error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JobberClient)
        self.mock_mapper = Mock(spec=EntityMapper)
        self.mock_repository = Mock(spec=Repository)
        self.mock_logger = Mock(spec=Logger)

        self.extractor = JobsExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

    def test_fetch_page_handles_api_error(self):
        """Test _fetch_page propagates API errors."""
        self.mock_client.fetch_jobs.side_effect = JobberApiError("API Error")

        with pytest.raises(JobberApiError):
            self.extractor._fetch_page()

    def test_map_entity_handles_mapping_error(self):
        """Test _map_entity propagates mapping errors."""
        node = {"id": "job_123"}
        self.mock_mapper.map_job.side_effect = MappingError("Invalid data")

        with pytest.raises(MappingError):
            self.extractor._map_entity(node)

    def test_extract_edges_handles_malformed_response(self):
        """Test _extract_edges_and_page_info handles malformed responses."""
        # Missing 'data' key
        response = {}

        edges, page_info = self.extractor._extract_edges_and_page_info(response)

        assert edges == []
        assert page_info == {}

    def test_extract_edges_handles_null_edges(self):
        """Test _extract_edges_and_page_info handles null edges."""
        response = {
            "data": {
                "jobs": {
                    "edges": None,
                    "pageInfo": None,
                }
            }
        }

        edges, page_info = self.extractor._extract_edges_and_page_info(response)

        # Should handle None gracefully
        assert edges is None or edges == []
        assert page_info is None or page_info == {}
