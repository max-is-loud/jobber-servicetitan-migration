"""Unified Rich UI for migration operations.

This module provides a centralized UI layer for all migration-related CLI commands,
ensuring consistent Rich-based terminal output across entity extraction, attachment
downloads, and error reporting.
"""

from collections import deque
from threading import Lock
from typing import Dict, Optional

from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ..models.migration_summary import MigrationSummary


class MigrationUI:
    """Unified Rich UI for migration operations.

    Provides consistent terminal output for:
    - Entity extraction with progress bars
    - Attachment downloads with parallel progress tracking
    - Error and success messaging
    - Summary tables with migration metrics

    Usage:
        console = SharedServices.get_console()
        ui = MigrationUI(console)

        # Entity extraction
        ui.show_run_header(db_path, config)
        ui.start_entity_progress(["clients", "invoices"])
        ui.update_entity_progress("clients", 50, 100)
        ui.show_run_summary(summary)
        ui.finalize()

        # Attachment downloads
        ui.start_download_progress(100, 1000000)
        task_id = ui.add_download_task("file.pdf", 5000)
        ui.update_download_task(task_id, 2500)
        ui.complete_download_task(task_id, "file.pdf")
        ui.show_download_summary(100, 1000000, 45.2, 0)
    """

    def __init__(self, console: Console):
        """Initialize MigrationUI with shared console.

        Args:
            console: Shared Rich Console from SharedServices
        """
        self._console = console
        self._progress: Optional[Progress] = None
        self._download_progress: Optional[Progress] = None
        self._live: Optional[Live] = None
        self._layout: Optional[Layout] = None
        self._entity_tasks: Dict[str, TaskID] = {}
        self._lock = Lock()  # For thread-safe download operations

        # Log buffer for console messages (keeps last 100 messages for scrollback)
        self._log_buffer: deque = deque(maxlen=100)
        self._status_message: Optional[str] = None  # For rate limit/status messages

    def show_run_header(
        self,
        db_path: str,
        config: Optional[dict] = None
    ) -> None:
        """Display migration run header panel.

        Args:
            db_path: Path to the database file
            config: Optional configuration dictionary (reserved for future use)
        """
        header_lines = [
            f"[cyan]Database:[/cyan] {db_path}",
        ]

        if config:
            # Future: Add config details when ConfigManager is integrated
            header_lines.append(f"[cyan]Config:[/cyan] {config.get('name', 'default')}")

        panel = Panel(
            "\n".join(header_lines),
            title="[bold blue]Migration Run Started[/bold blue]",
            border_style="blue",
            padding=(1, 2),
        )
        self._console.print(panel)
        self._console.print()  # Add spacing

    def add_log(self, message: str) -> None:
        """Add a message to the log buffer (thread-safe).

        Args:
            message: Log message to add
        """
        with self._lock:
            self._log_buffer.append(message)
            # Update live display if active
            if self._live:
                self._live.update(self._render_layout())

    def create_logger_adapter(self, log_file: Optional[str] = None) -> 'LoggerAdapter':
        """Create a logger adapter that redirects log messages to the UI and file.

        Args:
            log_file: Optional path to log file (defaults to logs/migration.log)

        Returns:
            LoggerAdapter instance that wraps logger calls
        """
        return LoggerAdapter(self, log_file=log_file)

    def set_status(self, message: Optional[str]) -> None:
        """Set or clear the status message (e.g., rate limit countdown).

        Args:
            message: Status message to display, or None to clear
        """
        with self._lock:
            self._status_message = message

    def _render_layout(self) -> RenderableType:
        """Render the layout with log panel and progress bar."""
        # Get terminal height to calculate available log space
        terminal_height = self._console.size.height

        # Calculate available space for logs
        # Terminal height - progress panel (5) - panel borders (4) - some padding (2)
        max_log_lines = max(10, terminal_height - 11)

        # Build log panel content - only show most recent messages that fit
        log_lines = []

        # Add status message if present (e.g., rate limit countdown)
        if self._status_message:
            log_lines.append(f"[yellow]{self._status_message}[/yellow]")

        # Add recent log messages (only the most recent ones that fit)
        buffer_list = list(self._log_buffer)

        # If we have more messages than fit, show only the most recent
        if len(buffer_list) > max_log_lines - (1 if self._status_message else 0):
            # Calculate how many to show (leave room for status if present)
            lines_to_show = max_log_lines - (1 if self._status_message else 0)
            visible_logs = buffer_list[-lines_to_show:]
        else:
            visible_logs = buffer_list

        log_lines.extend(visible_logs)

        # Create layout with dynamic sizing
        layout = Layout()

        # Split into two sections: logs (auto-expand) and progress (fixed)
        layout.split_column(
            Layout(name="logs", ratio=1),  # Takes all remaining space
            Layout(name="progress", size=5),  # Fixed 5 rows for progress
        )

        # Create log panel (no fixed height - uses all available space)
        log_panel = Panel(
            "\n".join(log_lines) if log_lines else "[dim]Waiting for messages...[/dim]",
            title="[bold cyan]Console Output[/bold cyan]",
            border_style="cyan",
        )

        # Create progress panel (compact, fixed height)
        # Show spinner when no active tasks (between entities)
        if self._progress and len(self._progress.task_ids) > 0:
            progress_content = self._progress
        else:
            # No active progress bars - show waiting message with spinner
            progress_content = Group(
                Spinner("dots", text="[dim]Waiting for next entity...[/dim]")
            )

        progress_panel = Panel(
            progress_content,
            title="[bold green]Progress[/bold green]",
            border_style="green",
        )

        # Assign panels to layout sections
        layout["logs"].update(log_panel)
        layout["progress"].update(progress_panel)

        return layout

    def start_entity_progress(self, entity_names: list[str]) -> Progress:
        """Create and start progress display with Live context.

        Args:
            entity_names: List of entity type names to track

        Returns:
            Progress instance for updates
        """
        # Create progress with standard columns
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style="green"),
            MofNCompleteColumn(),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            console=self._console,
            expand=True,
        )

        # Store entity list but don't create tasks yet
        # Tasks will be created on-demand as each entity starts processing
        self._entity_names = entity_names
        self._current_entity = None

        # Start Live display with layout (full-screen mode)
        self._live = Live(
            self._render_layout(),
            console=self._console,
            refresh_per_second=10,  # Higher refresh for smooth countdown
            screen=True,  # Enable alternate screen mode for full-screen display
        )
        self._live.start()

        return self._progress

    def update_entity_progress(
        self,
        entity: str,
        completed: int,
        total: Optional[int],
        finished: bool = False
    ) -> None:
        """Update progress for specific entity.

        Creates progress bar on first call for each entity, removes it when finished.
        This ensures only one entity progress bar is visible at a time.

        Args:
            entity: Entity type name
            completed: Number of records processed
            total: Total number of records (None if unknown)
            finished: If True, marks entity as complete and removes progress bar
        """
        if not self._progress:
            return

        # Create task if this is a new entity
        if entity not in self._entity_tasks:
            task_id = self._progress.add_task(
                f"[cyan]{entity.title()}[/cyan]",
                total=total,
                completed=0,
            )
            self._entity_tasks[entity] = task_id
            self._current_entity = entity

        task_id = self._entity_tasks[entity]

        # Update task with current progress
        self._progress.update(
            task_id,
            completed=completed,
            total=total if total is not None else self._progress.tasks[task_id].total,
        )

        # Update Live display to refresh layout
        if self._live:
            self._live.update(self._render_layout())

        # Remove task when finished to keep display clean
        if finished:
            self._progress.remove_task(task_id)
            del self._entity_tasks[entity]
            if self._current_entity == entity:
                self._current_entity = None
            # Refresh layout one more time
            if self._live:
                self._live.update(self._render_layout())

    def show_run_summary(
        self,
        summary: MigrationSummary,
        metrics: Optional[dict] = None
    ) -> None:
        """Display final summary table with metrics.

        Args:
            summary: MigrationSummary instance with all migration metrics
            metrics: Optional API metrics dict (reserved for future use)
        """
        table = Table(
            title="[bold blue]Migration Summary[/bold blue]",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", style="green", justify="right")

        # Duration
        table.add_row("Duration", summary.format_duration())

        # Entity counts
        table.add_row("Clients Processed", f"{summary.clients_processed:,}")
        table.add_row("Invoices Processed", f"{summary.invoices_processed:,}")
        table.add_row("Quotes Processed", f"{summary.quotes_processed:,}")
        table.add_row("Notes Processed", f"{summary.notes_processed:,}")
        table.add_row("Attachments Processed", f"{summary.attachments_processed:,}")

        # Skip statistics (if any)
        total_skipped = summary.get_total_skipped()
        if total_skipped > 0:
            table.add_row("", "")  # Separator
            table.add_row("Total Skipped", f"{total_skipped:,}", style="yellow")
            table.add_row(
                "Skip Percentage",
                f"{summary.get_skip_percentage():.1f}%",
                style="yellow"
            )

        # Download stats
        if summary.files_downloaded > 0:
            table.add_row("", "")  # Separator
            table.add_row("Files Downloaded", f"{summary.files_downloaded:,}")
            table.add_row(
                "Bytes Downloaded",
                f"{summary.total_bytes_downloaded:,}"
            )

        # Errors and failures
        if summary.errors or summary.download_failures > 0:
            table.add_row("", "")  # Separator
            if summary.errors:
                table.add_row("Errors", f"{len(summary.errors)}", style="red")
            if summary.download_failures > 0:
                table.add_row(
                    "Download Failures",
                    f"{summary.download_failures}",
                    style="red"
                )

        # Future: Add API metrics when implemented
        if metrics:
            table.add_row("", "")  # Separator
            table.add_row("API Requests", f"{metrics.get('requests', 0):,}")

        self._console.print()
        self._console.print(table)

    def show_error(self, exc: Exception) -> None:
        """Display error panel with traceback.

        Args:
            exc: Exception to display
        """
        panel = Panel(
            Text(str(exc), style="white"),
            title="[bold red]Error[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
        self._console.print()
        self._console.print(panel)
        self._console.print_exception(show_locals=False)

    def show_keyboard_interrupt(self) -> None:
        """Display keyboard interrupt message."""
        panel = Panel(
            "[yellow]Migration interrupted by user (Ctrl+C)[/yellow]\n"
            "[dim]Progress has been saved. Run the command again to resume.[/dim]",
            title="[bold yellow]Interrupted[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )
        self._console.print()
        self._console.print(panel)

    def finalize(self) -> None:
        """Clean up Live display and progress bars."""
        if self._live:
            self._live.stop()
            self._live = None

        # Clear references
        self._progress = None
        self._download_progress = None
        self._entity_tasks.clear()

    # ========================================================================
    # Attachment Download Methods
    # ========================================================================

    def start_download_progress(
        self,
        total_files: int,
        total_bytes: int
    ) -> None:
        """Start download progress tracking.

        Creates progress display for parallel attachment downloads.
        Individual task progress bars will be created on-demand by workers.

        Args:
            total_files: Total number of files to download
            total_bytes: Total bytes to download
        """
        # Create download progress with file-specific columns
        self._download_progress = Progress(
            TextColumn("[bold cyan]{task.fields[task_name]}", justify="right"),
            BarColumn(bar_width=None),
            DownloadColumn(binary_units=True),
            TextColumn("at"),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=self._console,
        )

        # Start Live display
        self._live = Live(
            self._download_progress,
            console=self._console,
            refresh_per_second=30,  # High refresh for smooth UI
        )
        self._live.start()

    def add_download_task(
        self,
        filename: str,
        file_size: int
    ) -> TaskID:
        """Add a download task to the display (thread-safe).

        Called by worker threads when starting a download.

        Args:
            filename: Name of file being downloaded
            file_size: Total bytes for this file

        Returns:
            Task ID for updating progress
        """
        if not self._download_progress:
            raise RuntimeError("Download progress not started")

        with self._lock:
            # Truncate long filenames
            display_name = filename[:32] if len(filename) > 32 else filename

            task_id = self._download_progress.add_task(
                "download",
                task_name=display_name,
                total=file_size,
            )

            return task_id

    def update_download_task(
        self,
        task_id: TaskID,
        bytes_downloaded: int
    ) -> None:
        """Update download task progress (thread-safe).

        Called by download progress callback from worker threads.

        Args:
            task_id: Task ID to update
            bytes_downloaded: Bytes to add to progress
        """
        if not self._download_progress:
            return

        with self._lock:
            self._download_progress.update(task_id, advance=bytes_downloaded)

    def complete_download_task(
        self,
        task_id: TaskID,
        filename: str
    ) -> None:
        """Mark download task as complete and hide it (thread-safe).

        Called by worker threads when download completes.

        Args:
            task_id: Task ID to complete
            filename: Filename for logging (currently unused)
        """
        if not self._download_progress:
            return

        with self._lock:
            self._download_progress.update(task_id, visible=False)

    def show_download_summary(
        self,
        total_files: int,
        total_bytes: int,
        duration: float,
        failures: int,
    ) -> None:
        """Display download summary table.

        Args:
            total_files: Total files processed
            total_bytes: Total bytes downloaded
            duration: Download duration in seconds
            failures: Number of failed downloads
        """
        table = Table(
            title="[bold blue]Download Summary[/bold blue]",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Metric", style="cyan", width=25)
        table.add_column("Value", style="green", justify="right")

        # Duration formatting
        if duration < 60:
            duration_str = f"{duration:.1f} seconds"
        else:
            minutes = int(duration // 60)
            seconds = duration % 60
            duration_str = f"{minutes}m {seconds:.1f}s"

        table.add_row("Duration", duration_str)
        table.add_row("Files Downloaded", f"{total_files:,}")
        table.add_row("Bytes Downloaded", f"{total_bytes:,}")

        if failures > 0:
            table.add_row("Failures", f"{failures}", style="red")

        self._console.print()
        self._console.print(table)


class LoggerAdapter:
    """Logger adapter that redirects log messages to MigrationUI and file.

    Implements the Logger protocol while sending messages to both the UI's log buffer
    and a debug log file for later review.
    """

    def __init__(self, migration_ui: MigrationUI, log_file: Optional[str] = None):
        """Initialize logger adapter with MigrationUI instance.

        Args:
            migration_ui: MigrationUI instance to send log messages to
            log_file: Optional path to log file (defaults to logs/migration.log)
        """
        self._ui = migration_ui

        # Setup file logging
        if log_file is None:
            from pathlib import Path
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            log_file = str(log_dir / "migration.log")

        self._log_file = log_file
        self._file_lock = Lock()

    def _write_to_file(self, level: str, msg: str) -> None:
        """Write log message to file with timestamp (thread-safe).

        Args:
            level: Log level (INFO, DEBUG, etc.)
            msg: Log message
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {level}: {msg}\n"

        with self._file_lock:
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(log_line)
            except Exception:
                # Don't let file logging errors break the migration
                pass

    def info(self, msg: str) -> None:
        """Log info message to UI and file."""
        self._ui.add_log(f"[cyan]INFO:[/cyan] {msg}")
        self._write_to_file("INFO", msg)

    def debug(self, msg: str) -> None:
        """Log debug message to UI and file."""
        self._ui.add_log(f"[dim]DEBUG:[/dim] {msg}")
        self._write_to_file("DEBUG", msg)

    def success(self, msg: str) -> None:
        """Log success message to UI and file."""
        self._ui.add_log(f"[green]✓[/green] {msg}")
        self._write_to_file("SUCCESS", msg)

    def warning(self, msg: str) -> None:
        """Log warning message to UI and file."""
        self._ui.add_log(f"[yellow]WARNING:[/yellow] {msg}")
        self._write_to_file("WARNING", msg)

    def error(self, msg: str) -> None:
        """Log error message to UI and file."""
        self._ui.add_log(f"[red]ERROR:[/red] {msg}")
        self._write_to_file("ERROR", msg)

    def log_summary(self, summary: dict) -> None:
        """Log summary to file (no-op for UI logger)."""
        import json
        self._write_to_file("SUMMARY", json.dumps(summary, indent=2))
