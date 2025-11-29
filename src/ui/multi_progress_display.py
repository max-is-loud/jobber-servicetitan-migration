"""Reusable multi-progress display for concurrent operations."""

from collections import deque
from threading import Lock
from typing import Dict, Optional
from rich.console import Console, RenderableType, Group
from rich.layout import Layout
from rich.live import Live
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    TaskID,
    Task,
)
from rich.panel import Panel
from rich.text import Text
from rich.table import Table


class MultiProgressDisplay:
    """
    Reusable multi-progress display for concurrent operations.

    Features:
    - Individual progress bars per concurrent task (with task ID + speed)
    - Overall summary progress bar at bottom
    - Logs scroll above the fixed progress display
    - Thread-safe updates from concurrent workers

    Usage:
        with MultiProgressDisplay(console, max_workers=5) as display:
            display.start_overall(total_items=100, total_bytes=1000000)
            for item in items:
                task_id = display.add_task(item.id, total_bytes=item.size)
                executor.submit(worker, display, task_id)

            # In worker:
            display.update(task_id, advance=bytes_downloaded)
            display.log(f"Downloaded {filename}")
    """

    def __init__(
        self,
        console: Console,
        max_workers: int = 3,
        description: str = "Processing",
        show_speed: bool = True,
    ):
        """Initialize multi-progress display.

        Args:
            console: Rich console for output
            max_workers: Maximum concurrent tasks to display
            description: Overall progress description
            show_speed: Whether to show transfer speeds
        """
        self._console = console
        self._max_workers = max_workers
        self._description = description
        self._show_speed = show_speed

        # Log buffer (unlimited - shows all logs)
        self._log_buffer: list = []

        # Create individual task progress (one bar per active worker)
        # Don't pass console - we'll render it ourselves
        task_columns = [
            TextColumn("[bold cyan]{task.fields[task_name]}", justify="right"),
            BarColumn(bar_width=None),
            DownloadColumn(binary_units=True),
        ]
        if show_speed:
            task_columns.extend([
                TextColumn("at"),
                TransferSpeedColumn(),
            ])
        task_columns.append(TimeRemainingColumn())

        self._task_progress = Progress(*task_columns)

        # Create overall progress (aggregate)
        self._overall_progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(binary_units=True),
            TextColumn("at"),
            TransferSpeedColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
        )

        # Overall task ID
        self._overall_task_id: Optional[TaskID] = None

        # Track active task IDs for cleanup
        self._active_tasks: Dict[str, TaskID] = {}

        # Layout and Live display
        self._layout: Optional[Layout] = None
        self._live: Optional[Live] = None

        # Thread lock for synchronizing updates from worker threads
        self._lock = Lock()

    def _render_logs(self) -> RenderableType:
        """Render the log buffer with Rich markup.

        Shows only the last 40 lines to create auto-scrolling effect.
        """
        if not self._log_buffer:
            return Text("Waiting for downloads to start...", style="dim italic")

        # Show only last 40 lines to create scrolling "tail -f" effect
        # This prevents the panel from filling up and stopping
        visible_lines = self._log_buffer[-40:]

        # Use Text.from_markup to preserve Rich formatting
        result = Text()
        for line in visible_lines:
            result.append_text(Text.from_markup(line))
            result.append("\n")

        return result

    def __enter__(self):
        """Start the live display with fixed layout."""
        # Create layout with fixed sections
        self._layout = Layout()

        # Split into log area (top, grows) and progress area (bottom, fixed height)
        self._layout.split_column(
            Layout(name="logs", ratio=3),  # Top 75% - scrollable logs
            Layout(name="progress", size=self._max_workers + 5),  # Bottom - fixed height
        )

        # Split progress area into active downloads and overall
        self._layout["progress"].split_column(
            Layout(Panel(self._task_progress, title="Active Downloads", border_style="green"), name="tasks"),
            Layout(self._overall_progress, size=1, name="overall"),
        )

        # Initialize log area
        self._layout["logs"].update(Panel(self._render_logs(), title="Download Log", border_style="blue"))

        # Start Live display with full screen takeover
        self._live = Live(
            self._layout,
            console=self._console,
            screen=True,  # Take over full terminal (like top/htop)
            refresh_per_second=30,  # High refresh rate for smooth UI (30Hz)
        )
        self._live.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop the live display."""
        if self._live:
            self._live.stop()
        return False

    def start_overall(self, total_items: int, total_bytes: int):
        """Start the overall progress tracking.

        Args:
            total_items: Total number of items to process
            total_bytes: Total bytes to transfer
        """
        self._overall_task_id = self._overall_progress.add_task(
            f"{self._description} ({total_items} items)",
            total=total_bytes,
        )

    def add_task(self, task_name: str, total_bytes: int) -> TaskID:
        """Add a new task to the display (thread-safe).

        Args:
            task_name: Name/ID to display for this task
            total_bytes: Total bytes for this task

        Returns:
            Task ID for updating progress
        """
        with self._lock:
            # Truncate long task names
            display_name = task_name[:24] if len(task_name) > 24 else task_name

            task_id = self._task_progress.add_task(
                "download",
                task_name=display_name,
                total=total_bytes,
            )

            self._active_tasks[task_name] = task_id
            return task_id

    def update(
        self,
        task_id: TaskID,
        advance: int = 0,
        completed: Optional[int] = None,
    ):
        """Update task progress (thread-safe).

        Args:
            task_id: Task ID to update
            advance: Bytes to add to progress
            completed: Total bytes completed (overrides advance)
        """
        with self._lock:
            # Update individual task
            if completed is not None:
                self._task_progress.update(task_id, completed=completed)
            else:
                self._task_progress.update(task_id, advance=advance)

            # Update overall progress
            if self._overall_task_id is not None:
                if completed is not None:
                    # For completed, don't double-count
                    pass
                else:
                    self._overall_progress.update(self._overall_task_id, advance=advance)

            # Note: We don't call _update_sorted_tasks() here because Rich's Live
            # display already updates at 30Hz, and TransferSpeedColumn has built-in
            # throttling to keep speeds readable

    def complete_task(self, task_id: TaskID, task_name: str):
        """Mark task as complete and hide it (thread-safe).

        Args:
            task_id: Task ID to complete
            task_name: Task name for cleanup
        """
        with self._lock:
            self._task_progress.update(task_id, visible=False)
            if task_name in self._active_tasks:
                del self._active_tasks[task_name]

    def log(self, message: str, level: str = "info"):
        """Log a message to the log buffer (thread-safe).

        Args:
            message: Message to log
            level: Log level (info, warning, error)
        """
        with self._lock:
            # Format message with level styling and bold for visibility
            if level == "error":
                formatted = f"[bold red]✗ ERROR:[/bold red] [red]{message}[/red]"
            elif level == "warning":
                formatted = f"[bold yellow]⚠ WARNING:[/bold yellow] [yellow]{message}[/yellow]"
            else:
                # Keep info messages clean (they already have ✓ from caller)
                formatted = message

            # Add to log buffer
            self._log_buffer.append(formatted)

            # Update log panel in layout
            if self._layout:
                self._layout["logs"].update(
                    Panel(
                        self._render_logs(),
                        title="[bold blue]Download Log[/bold blue]",
                        border_style="blue",
                    )
                )
