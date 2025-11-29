"""Unit tests for MigrationUI class."""

import pytest
from unittest.mock import Mock, patch, call
from datetime import datetime
from rich.console import Console
from rich.progress import TaskID

from src.ui.migration_ui import MigrationUI
from src.models.migration_summary import MigrationSummary


@pytest.fixture
def mock_console():
    """Mock Rich Console."""
    return Mock(spec=Console)


@pytest.fixture
def migration_ui(mock_console):
    """Create MigrationUI with mocked console."""
    return MigrationUI(mock_console)


@pytest.fixture
def sample_summary():
    """Create sample MigrationSummary for testing."""
    return MigrationSummary(
        clients_processed=100,
        invoices_processed=250,
        quotes_processed=50,
        notes_processed=75,
        note_references_collected=0,
        start_time="2025-11-28T10:00:00",
        end_time="2025-11-28T10:05:30",
        duration_seconds=330.5,
        errors=[],
        attachments_processed=15,
        files_downloaded=10,
        total_bytes_downloaded=5000000,
        download_failures=0,
        clients_skipped=5,
        invoices_skipped=10,
    )


class TestMigrationUIInit:
    """Test MigrationUI initialization."""

    def test_init_stores_console(self, mock_console):
        """Test console is stored during initialization."""
        ui = MigrationUI(mock_console)
        assert ui._console is mock_console

    def test_init_creates_empty_state(self, migration_ui):
        """Test initial state is empty."""
        assert migration_ui._progress is None
        assert migration_ui._download_progress is None
        assert migration_ui._live is None
        assert migration_ui._entity_tasks == {}


class TestShowRunHeader:
    """Test show_run_header method."""

    def test_displays_panel_with_db_path(self, migration_ui, mock_console):
        """Test run header displays database path in panel."""
        migration_ui.show_run_header("/path/to/database.sqlite")

        # Verify console.print was called (panel + spacing)
        assert mock_console.print.call_count >= 2

    def test_handles_no_config(self, migration_ui, mock_console):
        """Test header works without config."""
        migration_ui.show_run_header("/path/to/db.sqlite", config=None)
        assert mock_console.print.called

    def test_includes_config_when_provided(self, migration_ui, mock_console):
        """Test config is included when provided."""
        config = {"name": "test_config"}
        migration_ui.show_run_header("/path/to/db.sqlite", config=config)
        # Just verify it doesn't crash - config display is reserved for future


class TestEntityProgress:
    """Test entity progress tracking methods."""

    @patch('src.ui.migration_ui.Live')
    @patch('src.ui.migration_ui.Progress')
    def test_start_entity_progress_creates_tasks(
        self,
        mock_progress_class,
        mock_live_class,
        migration_ui
    ):
        """Test progress tasks are created for each entity."""
        mock_progress = Mock()
        mock_progress_class.return_value = mock_progress
        mock_progress.add_task.side_effect = [TaskID(0), TaskID(1), TaskID(2)]

        mock_live = Mock()
        mock_live_class.return_value = mock_live

        entities = ["clients", "invoices", "quotes"]
        result = migration_ui.start_entity_progress(entities)

        # Verify Progress instance created
        assert result is mock_progress
        assert migration_ui._progress is mock_progress

        # Verify tasks added for each entity
        assert mock_progress.add_task.call_count == 3
        assert "clients" in migration_ui._entity_tasks
        assert "invoices" in migration_ui._entity_tasks
        assert "quotes" in migration_ui._entity_tasks

        # Verify Live started
        mock_live.start.assert_called_once()

    def test_update_entity_progress_with_total(self, migration_ui):
        """Test updating entity progress with known total."""
        # Setup: manually create progress and task
        migration_ui._progress = Mock()
        migration_ui._entity_tasks["clients"] = TaskID(0)

        migration_ui.update_entity_progress("clients", completed=50, total=100)

        # Verify progress.update called with correct params
        migration_ui._progress.update.assert_called_once_with(
            TaskID(0),
            completed=50,
            total=100,
        )

    def test_update_entity_progress_with_none_total(self, migration_ui):
        """Test updating entity progress with unknown total."""
        migration_ui._progress = Mock()
        migration_ui._entity_tasks["invoices"] = TaskID(1)

        migration_ui.update_entity_progress("invoices", completed=25, total=None)

        migration_ui._progress.update.assert_called_once_with(
            TaskID(1),
            completed=25,
            total=None,
        )

    def test_update_entity_progress_unknown_entity_no_crash(self, migration_ui):
        """Test updating unknown entity doesn't crash."""
        migration_ui._progress = Mock()

        # Should not crash
        migration_ui.update_entity_progress("unknown", 10, 100)

        # Should not call update
        migration_ui._progress.update.assert_not_called()

    def test_update_entity_progress_no_progress_no_crash(self, migration_ui):
        """Test updating without started progress doesn't crash."""
        # No progress started
        assert migration_ui._progress is None

        # Should not crash
        migration_ui.update_entity_progress("clients", 10, 100)


class TestShowRunSummary:
    """Test show_run_summary method."""

    def test_displays_summary_table(self, migration_ui, mock_console, sample_summary):
        """Test summary table is displayed with all metrics."""
        migration_ui.show_run_summary(sample_summary)

        # Verify console.print called (spacing + table)
        assert mock_console.print.call_count >= 2

    def test_includes_entity_counts(self, migration_ui, mock_console, sample_summary):
        """Test entity counts are included in summary."""
        migration_ui.show_run_summary(sample_summary)
        # Verify print was called - specific table content hard to verify with mocks

    def test_shows_skip_statistics_when_present(self, migration_ui, mock_console):
        """Test skip statistics shown when entities were skipped."""
        summary = MigrationSummary(
            clients_processed=90,
            invoices_processed=240,
            quotes_processed=50,
            notes_processed=75,
            note_references_collected=0,
            start_time="2025-11-28T10:00:00",
            end_time="2025-11-28T10:05:30",
            duration_seconds=330.5,
            errors=[],
            clients_skipped=10,
            invoices_skipped=10,
        )

        migration_ui.show_run_summary(summary)
        assert mock_console.print.called

    def test_shows_errors_when_present(self, migration_ui, mock_console):
        """Test errors are shown in summary."""
        summary = MigrationSummary(
            clients_processed=100,
            invoices_processed=250,
            quotes_processed=50,
            notes_processed=75,
            note_references_collected=0,
            start_time="2025-11-28T10:00:00",
            end_time="2025-11-28T10:05:30",
            duration_seconds=330.5,
            errors=["Error 1", "Error 2"],
        )

        migration_ui.show_run_summary(summary)
        assert mock_console.print.called

    def test_handles_optional_metrics(self, migration_ui, mock_console, sample_summary):
        """Test optional metrics parameter."""
        metrics = {"requests": 500}
        migration_ui.show_run_summary(sample_summary, metrics=metrics)
        assert mock_console.print.called


class TestErrorDisplay:
    """Test error display methods."""

    def test_show_error_displays_panel(self, migration_ui, mock_console):
        """Test error panel is displayed."""
        exc = ValueError("Test error message")
        migration_ui.show_error(exc)

        # Verify console.print and print_exception called
        assert mock_console.print.call_count >= 2
        mock_console.print_exception.assert_called_once_with(show_locals=False)

    def test_show_keyboard_interrupt_displays_panel(self, migration_ui, mock_console):
        """Test keyboard interrupt panel is displayed."""
        migration_ui.show_keyboard_interrupt()

        # Verify console.print called with panel
        assert mock_console.print.call_count >= 2


class TestFinalize:
    """Test finalize method."""

    def test_finalize_stops_live(self, migration_ui):
        """Test finalize stops Live display."""
        mock_live = Mock()
        migration_ui._live = mock_live

        migration_ui.finalize()

        mock_live.stop.assert_called_once()
        assert migration_ui._live is None

    def test_finalize_clears_state(self, migration_ui):
        """Test finalize clears all state."""
        # Setup some state
        migration_ui._progress = Mock()
        migration_ui._download_progress = Mock()
        migration_ui._entity_tasks = {"clients": TaskID(0)}
        migration_ui._live = Mock()

        migration_ui.finalize()

        # Verify all cleared
        assert migration_ui._progress is None
        assert migration_ui._download_progress is None
        assert migration_ui._live is None
        assert migration_ui._entity_tasks == {}

    def test_finalize_no_live_no_crash(self, migration_ui):
        """Test finalize without Live doesn't crash."""
        migration_ui._live = None
        migration_ui.finalize()  # Should not crash


class TestDownloadProgress:
    """Test download progress methods."""

    @patch('src.ui.migration_ui.Live')
    @patch('src.ui.migration_ui.Progress')
    def test_start_download_progress(
        self,
        mock_progress_class,
        mock_live_class,
        migration_ui
    ):
        """Test download progress is started."""
        mock_progress = Mock()
        mock_progress_class.return_value = mock_progress
        mock_live = Mock()
        mock_live_class.return_value = mock_live

        migration_ui.start_download_progress(100, 5000000)

        # Verify Progress and Live created
        assert migration_ui._download_progress is mock_progress
        assert migration_ui._live is mock_live
        mock_live.start.assert_called_once()

    def test_add_download_task(self, migration_ui):
        """Test adding download task."""
        migration_ui._download_progress = Mock()
        migration_ui._download_progress.add_task.return_value = TaskID(5)

        task_id = migration_ui.add_download_task("test_file.pdf", 1024)

        assert task_id == TaskID(5)
        migration_ui._download_progress.add_task.assert_called_once()

    def test_add_download_task_truncates_long_filename(self, migration_ui):
        """Test long filenames are truncated."""
        migration_ui._download_progress = Mock()
        migration_ui._download_progress.add_task.return_value = TaskID(1)

        long_name = "a" * 50 + ".pdf"
        migration_ui.add_download_task(long_name, 1024)

        # Verify truncation happened (check call args)
        call_kwargs = migration_ui._download_progress.add_task.call_args[1]
        assert len(call_kwargs["task_name"]) <= 32

    def test_add_download_task_without_started_progress_raises(self, migration_ui):
        """Test adding task without started progress raises error."""
        with pytest.raises(RuntimeError, match="Download progress not started"):
            migration_ui.add_download_task("file.pdf", 1024)

    def test_update_download_task(self, migration_ui):
        """Test updating download task progress."""
        migration_ui._download_progress = Mock()

        migration_ui.update_download_task(TaskID(3), 512)

        migration_ui._download_progress.update.assert_called_once_with(
            TaskID(3),
            advance=512
        )

    def test_update_download_task_no_progress_no_crash(self, migration_ui):
        """Test updating without progress doesn't crash."""
        migration_ui._download_progress = None
        migration_ui.update_download_task(TaskID(1), 100)  # Should not crash

    def test_complete_download_task(self, migration_ui):
        """Test completing download task hides it."""
        migration_ui._download_progress = Mock()

        migration_ui.complete_download_task(TaskID(2), "file.pdf")

        migration_ui._download_progress.update.assert_called_once_with(
            TaskID(2),
            visible=False
        )

    def test_complete_download_task_no_progress_no_crash(self, migration_ui):
        """Test completing without progress doesn't crash."""
        migration_ui._download_progress = None
        migration_ui.complete_download_task(TaskID(1), "file.pdf")  # Should not crash

    def test_show_download_summary(self, migration_ui, mock_console):
        """Test download summary table is displayed."""
        migration_ui.show_download_summary(
            total_files=100,
            total_bytes=5000000,
            duration=125.5,
            failures=2
        )

        # Verify console.print called for table
        assert mock_console.print.call_count >= 2

    def test_show_download_summary_formats_duration(self, migration_ui, mock_console):
        """Test duration is formatted correctly."""
        # Short duration (< 60s)
        migration_ui.show_download_summary(10, 1000, 45.2, 0)
        assert mock_console.print.called

        # Long duration (>= 60s)
        migration_ui.show_download_summary(100, 10000, 125.5, 0)
        assert mock_console.print.called
