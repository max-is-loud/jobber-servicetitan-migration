"""Reusable multi-progress display for concurrent operations."""

from typing import Dict, Optional
from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    TaskID,
)
from rich.panel import Panel


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

        # Create individual task progress (one bar per active worker)
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

        self._task_progress = Progress(*task_columns, console=console)

        # Create overall progress (aggregate)
        self._overall_progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(binary_units=True),
            TextColumn("at"),
            TransferSpeedColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        )

        # Overall task ID
        self._overall_task_id: Optional[TaskID] = None

        # Track active task IDs for cleanup
        self._active_tasks: Dict[str, TaskID] = {}

        # Live display
        self._live: Optional[Live] = None

    def __enter__(self):
        """Start the live display."""
        # Create grouped display (tasks above, overall below)
        progress_group = Group(
            Panel(self._task_progress, title="Active Downloads", border_style="green"),
            self._overall_progress,
        )

        self._live = Live(progress_group, console=self._console, refresh_per_second=10)
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
        """Add a new task to the display.

        Args:
            task_name: Name/ID to display for this task
            total_bytes: Total bytes for this task

        Returns:
            Task ID for updating progress
        """
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
        """Update task progress.

        Args:
            task_id: Task ID to update
            advance: Bytes to add to progress
            completed: Total bytes completed (overrides advance)
        """
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

    def complete_task(self, task_id: TaskID, task_name: str):
        """Mark task as complete and hide it.

        Args:
            task_id: Task ID to complete
            task_name: Task name for cleanup
        """
        self._task_progress.update(task_id, visible=False)
        if task_name in self._active_tasks:
            del self._active_tasks[task_name]

    def log(self, message: str, level: str = "info"):
        """Log a message above the progress display.

        Args:
            message: Message to log
            level: Log level (info, warning, error)
        """
        # Print to console - Rich Live will handle positioning
        if level == "error":
            self._console.print(f"[red]ERROR:[/red] {message}")
        elif level == "warning":
            self._console.print(f"[yellow]WARNING:[/yellow] {message}")
        else:
            self._console.print(message)
