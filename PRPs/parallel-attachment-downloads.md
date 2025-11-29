# Implementation Plan: Parallel Attachment Downloads

## Overview

Add configurable parallel download capability to the attachment downloader to significantly improve download performance for large attachment sets. Currently, attachments are downloaded sequentially (one at a time), which is inefficient for network I/O-bound operations. This implementation will use Python's `ThreadPoolExecutor` to download multiple attachments concurrently while maintaining thread-safety and progress tracking.

**Performance Impact**: With 5 concurrent downloads, estimated 3-5x speedup for typical workloads.

## Requirements Summary

- Add configurable concurrent download setting to `settings.yaml` and config models
- Refactor `DownloadModeCoordinator._process_downloads()` to use `ThreadPoolExecutor`
- Ensure thread-safe database operations (SQLite write serialization)
- Maintain existing Rich progress bar functionality with thread-safe updates
- Preserve all existing error handling, retry logic, and download tracking
- Add comprehensive unit and integration tests for parallel execution
- Keep backward compatibility - sequential downloads still work if concurrency = 1

## Research Findings

### Best Practices

1. **ThreadPoolExecutor for I/O-Bound Operations**
   - Python's `concurrent.futures.ThreadPoolExecutor` is ideal for network I/O
   - More lightweight than multiprocessing for download operations
   - Easier to integrate with existing synchronous code than asyncio

2. **Thread-Safety Considerations**
   - SQLite connections are NOT thread-safe by default
   - `requests.Session` objects should NOT be shared between threads
   - Rich Progress bars are thread-safe for updates
   - Shared counters need `threading.Lock()` protection

3. **Repository Thread-Safety Strategy**
   - SQLite supports concurrent reads but serializes writes
   - Use connection with `check_same_thread=False` for shared access
   - Better approach: Create separate Repository instance per thread
   - Alternative: Use result collection pattern - download in threads, write sequentially

### Reference Implementations from Codebase

1. **Thread-Safe Singleton Pattern** (`src/config/config_manager.py:60-89`)
   ```python
   _instance_lock = threading.Lock()

   def __new__(cls):
       with cls._instance_lock:
           if cls._instance is None:
               cls._instance = super().__new__(cls)
   ```

2. **Thread-Safe Rate Limiter** (`src/rate_limiting/token_bucket.py:64-91`)
   ```python
   self._lock = threading.Lock()

   def consume(self, tokens: float = 1.0) -> bool:
       with self._lock:
           # Critical section protected by lock
   ```

3. **Rich Progress Bar Usage** (`src/coordinators/download_mode_coordinator.py:298-312`)
   ```python
   with Progress(...columns...) as progress:
       task_id = progress.add_task(f"Downloading {len(items)}...", total=len(items))
       for item in items:
           # ... work ...
           progress.update(task_id, advance=1)
   ```

4. **AttachmentDownloader Session Setup** (`src/extractors/attachment_downloader.py:69-79`)
   ```python
   self._session = requests.Session()
   retry_strategy = Retry(total=max_retries, status_forcelist=[429, 500, 502, 503, 504])
   adapter = HTTPAdapter(max_retries=retry_strategy)
   self._session.mount("http://", adapter)
   ```

### Technology Decisions

1. **ThreadPoolExecutor vs asyncio/aiohttp**
   - **Decision**: Use `ThreadPoolExecutor` (standard library)
   - **Rationale**:
     - Minimal code changes (no async/await refactoring)
     - Works with existing synchronous `requests` library
     - Sufficient for I/O-bound download operations
     - Easier to test and debug

2. **Repository Thread-Safety Approach**
   - **Decision**: Use "worker download + sequential database updates" pattern
   - **Rationale**:
     - Avoids SQLite multi-threaded write complexity
     - Simpler error handling and state management
     - Workers return results, main thread updates database
     - Most time is spent in network I/O anyway

3. **Progress Tracking**
   - **Decision**: Keep single Rich Progress task, update from callback
   - **Rationale**:
     - Rich Progress.update() is thread-safe
     - Single progress bar provides cleaner UX
     - Can update from `as_completed()` futures

## Implementation Tasks

### Phase 1: Configuration and Models

#### Task 1.1: Add Configuration Schema
- **Description**: Add `concurrent_downloads` setting to YAML config and validation
- **Files to modify**:
  - `config/example.settings.yaml` (Lines 73-74)
  - `src/config/config_models.py` (Lines 202-212 - AttachmentConfig)
- **Implementation**:
  ```yaml
  # config/example.settings.yaml
  attachments:
    auto_download: false
    concurrent_downloads: 3      # NEW: Number of parallel downloads (1-10)
    max_concurrent_downloads: 10 # NEW: Upper limit for validation
  ```
  ```python
  # src/config/config_models.py
  @dataclass(frozen=True)
  class AttachmentConfig:
      auto_download: bool
      concurrent_downloads: int = 3
      max_concurrent_downloads: int = 10

      def __post_init__(self) -> None:
          # Validate auto_download
          if not isinstance(self.auto_download, bool):
              raise ValueError(...)

          # Validate concurrent_downloads
          if not isinstance(self.concurrent_downloads, int):
              raise ValueError(f"concurrent_downloads must be int, got {type(...)}")
          if not 1 <= self.concurrent_downloads <= self.max_concurrent_downloads:
              raise ValueError(
                  f"concurrent_downloads must be between 1 and {self.max_concurrent_downloads}, "
                  f"got {self.concurrent_downloads}"
              )
  ```
- **Dependencies**: None
- **Estimated effort**: 30 minutes

#### Task 1.2: Update Settings Loader
- **Description**: Ensure config manager properly loads new attachment settings
- **Files to modify**:
  - `src/config/config_manager.py` (Lines 338-345 - `get_attachment_config`)
- **Implementation**: Verify default value handling for new fields
- **Dependencies**: Task 1.1
- **Estimated effort**: 15 minutes

### Phase 2: Core Parallel Download Implementation

#### Task 2.1: Create Download Worker Function
- **Description**: Extract download logic into worker function for ThreadPoolExecutor
- **Files to modify**:
  - `src/coordinators/download_mode_coordinator.py` (new private method)
- **Implementation**:
  ```python
  def _download_worker(
      self,
      queue_item: AttachmentQueueItem,
      base_download_path: str,
  ) -> dict[str, Any]:
      """Worker function for parallel downloads.

      Runs in thread pool. Downloads attachment and returns result.
      Does NOT update database - caller handles that.

      Returns:
          dict with:
          - queue_item: Original queue item
          - success: bool
          - attachment: Attachment object (if found)
          - download_result: Result dict from AttachmentDownloader
          - error: Exception or error message (if failed)
      """
      try:
          # Get attachment metadata
          attachment = self._repository.get_attachment_by_id(queue_item.attachment_id)
          if not attachment:
              return {
                  "queue_item": queue_item,
                  "success": False,
                  "attachment": None,
                  "download_result": None,
                  "error": f"Attachment not found: {queue_item.attachment_id}",
              }

          # Create downloader (each thread gets own instance)
          downloader = AttachmentDownloader(
              repository=self._repository,  # Reads are thread-safe
              logger=self._logger,
              base_download_path=base_download_path,
          )

          # Download file
          download_result = downloader.download_attachment(attachment)

          return {
              "queue_item": queue_item,
              "success": download_result["success"],
              "attachment": attachment,
              "download_result": download_result,
              "error": download_result.get("error_message") if not download_result["success"] else None,
          }

      except Exception as e:
          self._logger.error(f"Worker exception for {queue_item.attachment_id}: {e}")
          return {
              "queue_item": queue_item,
              "success": False,
              "attachment": None,
              "download_result": None,
              "error": str(e),
          }
  ```
- **Dependencies**: None
- **Estimated effort**: 1 hour

#### Task 2.2: Refactor `_process_downloads` for Parallel Execution
- **Description**: Replace sequential loop with ThreadPoolExecutor pattern
- **Files to modify**:
  - `src/coordinators/download_mode_coordinator.py` (Lines 269-383)
- **Implementation**:
  ```python
  def _process_downloads(
      self,
      queue_items: List[AttachmentQueueItem],
      output_dir: Optional[Path] = None,
  ) -> Dict[str, Any]:
      """Process attachment downloads with parallel execution and progress tracking."""

      # Get concurrency setting
      attachment_config = self._config_manager.get_attachment_config()
      max_workers = attachment_config.get("concurrent_downloads", 3)

      base_download_path = str(output_dir) if output_dir else "./attachments"

      # Track results
      downloaded_count = 0
      failed_count = 0
      total_bytes = 0

      # Process downloads with Rich progress bar
      with Progress(...columns...) as progress:
          task_id = progress.add_task(
              f"Downloading {len(queue_items)} attachments ({max_workers} concurrent)...",
              total=len(queue_items),
          )

          # Submit all downloads to thread pool
          from concurrent.futures import ThreadPoolExecutor, as_completed

          with ThreadPoolExecutor(max_workers=max_workers) as executor:
              # Submit all jobs
              future_to_item = {
                  executor.submit(self._download_worker, item, base_download_path): item
                  for item in queue_items
              }

              # Process results as they complete
              for future in as_completed(future_to_item):
                  result = future.result()
                  queue_item = result["queue_item"]

                  # Update database based on result
                  queue_item.updated_at = self._get_current_timestamp()

                  if result["success"]:
                      # Update attachment with local file path
                      attachment = result["attachment"]
                      download_result = result["download_result"]

                      updated_attachment = Attachment(
                          id=attachment.id,
                          note_id=attachment.note_id,
                          file_name=attachment.file_name,
                          content_type=attachment.content_type,
                          original_url=attachment.original_url,
                          local_file_path=download_result["local_file_path"],
                          file_size=attachment.file_size,
                          created_at=attachment.created_at,
                      )
                      self._repository.save_attachments([updated_attachment])

                      queue_item.status = "done"
                      queue_item.last_error = None
                      downloaded_count += 1
                      total_bytes += download_result.get("bytes_downloaded", 0)
                  else:
                      queue_item.status = "failed"
                      queue_item.last_error = result["error"]
                      queue_item.attempt_count += 1
                      failed_count += 1

                  # Update queue status
                  self._repository.update_attachment_queue_status(queue_item)

                  # Update progress
                  progress.update(task_id, advance=1)

      return {
          "downloaded": downloaded_count,
          "failed": failed_count,
          "total_bytes": total_bytes,
      }
  ```
- **Dependencies**: Task 2.1
- **Estimated effort**: 1.5 hours

#### Task 2.3: Add In-Progress Status Updates
- **Description**: Mark items as "in_progress" before download starts
- **Files to modify**:
  - `src/coordinators/download_mode_coordinator.py` (Task 2.2 code)
- **Implementation**: Update queue_item status before submitting to executor
- **Dependencies**: Task 2.2
- **Estimated effort**: 30 minutes

### Phase 3: Thread-Safety and Error Handling

#### Task 3.1: Verify Repository Thread-Safety
- **Description**: Test that Repository handles concurrent reads safely
- **Files to check**:
  - `src/repositories/repository.py` (Lines 40-46)
- **Actions**:
  - Verify SQLite connection mode
  - Test concurrent `get_attachment_by_id()` calls
  - Ensure writes are serialized (main thread only)
- **Dependencies**: None
- **Estimated effort**: 1 hour

#### Task 3.2: Handle Worker Exceptions Gracefully
- **Description**: Ensure exceptions in worker threads don't crash coordinator
- **Files to modify**:
  - `src/coordinators/download_mode_coordinator.py` (Task 2.1 worker function)
- **Implementation**: Already wrapped in try-except in Task 2.1
- **Dependencies**: Task 2.1
- **Estimated effort**: 30 minutes

#### Task 3.3: Add Cancellation Support (Optional Enhancement)
- **Description**: Allow graceful shutdown if user interrupts (Ctrl+C)
- **Files to modify**:
  - `src/coordinators/download_mode_coordinator.py`
- **Implementation**:
  ```python
  try:
      with ThreadPoolExecutor(max_workers=max_workers) as executor:
          # ... download logic ...
  except KeyboardInterrupt:
      executor.shutdown(wait=False, cancel_futures=True)  # Python 3.9+
      raise
  ```
- **Dependencies**: Task 2.2
- **Estimated effort**: 45 minutes

### Phase 4: Testing

#### Task 4.1: Unit Tests - Configuration Loading
- **Description**: Test new config fields load correctly with validation
- **Files to create/modify**:
  - `tests/config/test_config_models.py` (new tests)
- **Test cases**:
  - Valid concurrent_downloads values (1, 3, 10)
  - Invalid values (0, 11, -1, "three")
  - Default value handling
- **Dependencies**: Task 1.1
- **Estimated effort**: 45 minutes

#### Task 4.2: Unit Tests - Download Worker Function
- **Description**: Test worker function with mocked dependencies
- **Files to create/modify**:
  - `tests/test_download_coordinator.py` (add test class)
- **Test cases**:
  - Successful download
  - Attachment not found
  - Download failure (network error)
  - Worker exception handling
- **Implementation**:
  ```python
  def test_download_worker_success(self, coordinator, mock_repository):
      queue_item = AttachmentQueueItem(...)
      attachment = Attachment(...)
      mock_repository.get_attachment_by_id.return_value = attachment

      with patch("...AttachmentDownloader") as mock_downloader_class:
          mock_downloader = Mock()
          mock_downloader_class.return_value = mock_downloader
          mock_downloader.download_attachment.return_value = {
              "success": True,
              "local_file_path": "/tmp/file.pdf",
              "bytes_downloaded": 1024,
          }

          result = coordinator._download_worker(queue_item, "./attachments")

          assert result["success"] is True
          assert result["attachment"] == attachment
          assert result["download_result"]["bytes_downloaded"] == 1024
  ```
- **Dependencies**: Task 2.1
- **Estimated effort**: 1.5 hours

#### Task 4.3: Unit Tests - Parallel Execution Flow
- **Description**: Test ThreadPoolExecutor integration with mocked futures
- **Files to create/modify**:
  - `tests/test_download_coordinator.py`
- **Test cases**:
  - Multiple successful downloads
  - Mix of success and failure
  - Progress bar updates
  - Concurrent download count respected
- **Implementation**:
  ```python
  def test_process_downloads_parallel_execution(self, coordinator):
      queue_items = [AttachmentQueueItem(...) for _ in range(5)]

      with patch.object(coordinator, "_download_worker") as mock_worker:
          mock_worker.return_value = {"success": True, ...}

          result = coordinator._process_downloads(queue_items)

          assert mock_worker.call_count == 5
          assert result["downloaded"] == 5
  ```
- **Dependencies**: Task 2.2
- **Estimated effort**: 2 hours

#### Task 4.4: Integration Tests - Real Parallel Downloads
- **Description**: End-to-end test with real database and mock HTTP
- **Files to create/modify**:
  - `tests/integration/test_download_mode_integration.py`
- **Test cases**:
  - Parallel downloads with real SQLite database
  - Verify thread-safe database updates
  - Check final queue status for all items
  - Validate downloaded file paths
- **Implementation**:
  ```python
  def test_parallel_downloads_integration(self, real_repository, temp_dir):
      # Setup: Create 10 queue items
      snapshot_id = "test-snapshot"
      queue_items = [...]
      for item in queue_items:
          real_repository.insert_attachment_queue_item(item)

      # Mock HTTP responses
      with requests_mock.Mocker() as m:
          m.get(requests_mock.ANY, content=b"fake pdf content")

          coordinator = DownloadModeCoordinator(
              repository=real_repository,
              logger=mock_logger,
              config_manager=test_config_manager,  # concurrent_downloads=3
          )

          result = coordinator.run_download_pass(snapshot_id)

          assert result["downloaded"] == 10
          assert result["failed"] == 0

          # Verify all queue items marked done
          final_queue = real_repository.get_attachment_queue(snapshot_id)
          assert all(item.status == "done" for item in final_queue)
  ```
- **Dependencies**: Task 2.2, Task 3.1
- **Estimated effort**: 2 hours

#### Task 4.5: Performance Benchmark Test
- **Description**: Measure speedup with parallel downloads
- **Files to create**:
  - `tests/performance/test_parallel_download_performance.py` (new)
- **Test implementation**:
  ```python
  import time

  def test_parallel_speedup():
      # Test with 20 mock downloads, 100ms delay each
      # Sequential: ~2 seconds
      # Parallel (5 workers): ~400-500ms

      with ThreadPoolExecutor(max_workers=1) as executor:
          start = time.time()
          # ... sequential downloads ...
          sequential_time = time.time() - start

      with ThreadPoolExecutor(max_workers=5) as executor:
          start = time.time()
          # ... parallel downloads ...
          parallel_time = time.time() - start

      speedup = sequential_time / parallel_time
      assert speedup >= 3.0  # Expect at least 3x speedup
  ```
- **Dependencies**: Task 2.2
- **Estimated effort**: 1 hour

### Phase 5: Enhanced Progress Display (Multi-Task + Throughput)

#### Task 5.1: Create Reusable Multi-Progress Display Component
- **Description**: Build reusable component for concurrent task monitoring with individual + aggregate progress
- **Files to create**:
  - `src/ui/multi_progress_display.py` (new module)
- **Implementation**:
  ```python
  """Reusable multi-progress display for concurrent operations."""

  from typing import Dict, Optional, Any
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
          with MultiProgressDisplay(max_workers=5) as display:
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
  ```
- **Dependencies**: None
- **Estimated effort**: 2 hours

#### Task 5.2: Integrate Multi-Progress Display with DownloadModeCoordinator
- **Description**: Replace simple progress bar with multi-task display
- **Files to modify**:
  - `src/coordinators/download_mode_coordinator.py` (Lines 269-383)
- **Implementation**:
  ```python
  from ..ui.multi_progress_display import MultiProgressDisplay

  def _process_downloads(
      self,
      queue_items: List[AttachmentQueueItem],
      output_dir: Optional[Path] = None,
  ) -> Dict[str, Any]:
      """Process attachment downloads with parallel execution and multi-progress tracking."""

      # Get concurrency setting
      attachment_config = self._config_manager.get_attachment_config()
      max_workers = attachment_config.get("concurrent_downloads", 3)

      base_download_path = str(output_dir) if output_dir else "./attachments"

      # Pre-calculate total bytes
      total_bytes_to_download = 0
      for item in queue_items:
          attachment = self._repository.get_attachment_by_id(item.attachment_id)
          if attachment and attachment.file_size:
              total_bytes_to_download += attachment.file_size

      # Track results
      downloaded_count = 0
      failed_count = 0
      total_bytes = 0

      # Use multi-progress display
      with MultiProgressDisplay(
          console=self._console,
          max_workers=max_workers,
          description="Downloading attachments",
          show_speed=True,
      ) as display:
          # Start overall progress
          display.start_overall(
              total_items=len(queue_items),
              total_bytes=total_bytes_to_download,
          )

          # Submit downloads to thread pool
          from concurrent.futures import ThreadPoolExecutor, as_completed

          with ThreadPoolExecutor(max_workers=max_workers) as executor:
              # Map futures to (queue_item, task_id)
              future_to_context = {}

              for queue_item in queue_items:
                  # Get attachment metadata
                  attachment = self._repository.get_attachment_by_id(queue_item.attachment_id)
                  if not attachment:
                      display.log(f"Attachment not found: {queue_item.attachment_id}", level="warning")
                      failed_count += 1
                      continue

                  # Add task to display
                  task_id = display.add_task(
                      task_name=f"Attachment {attachment.id[:12]}",
                      total_bytes=attachment.file_size or 0,
                  )

                  # Submit download
                  future = executor.submit(
                      self._download_worker_with_progress,
                      queue_item,
                      base_download_path,
                      display,
                      task_id,
                  )

                  future_to_context[future] = (queue_item, task_id, attachment)

              # Process results as they complete
              for future in as_completed(future_to_context):
                  queue_item, task_id, attachment = future_to_context[future]
                  result = future.result()

                  # Update database
                  queue_item.updated_at = self._get_current_timestamp()

                  if result["success"]:
                      # Update attachment with local file path
                      download_result = result["download_result"]

                      updated_attachment = Attachment(
                          id=attachment.id,
                          note_id=attachment.note_id,
                          file_name=attachment.file_name,
                          content_type=attachment.content_type,
                          original_url=attachment.original_url,
                          local_file_path=download_result["local_file_path"],
                          file_size=attachment.file_size,
                          created_at=attachment.created_at,
                      )
                      self._repository.save_attachments([updated_attachment])

                      queue_item.status = "done"
                      queue_item.last_error = None
                      downloaded_count += 1
                      total_bytes += download_result.get("bytes_downloaded", 0)

                      display.log(f"✓ Downloaded {attachment.id[:12]} ({download_result['bytes_downloaded']:,} bytes)")
                  else:
                      queue_item.status = "failed"
                      queue_item.last_error = result["error"]
                      queue_item.attempt_count += 1
                      failed_count += 1

                      display.log(f"✗ Failed {attachment.id[:12]}: {result['error']}", level="error")

                  # Complete task (hide from display)
                  display.complete_task(task_id, f"Attachment {attachment.id[:12]}")

                  # Update queue status
                  self._repository.update_attachment_queue_status(queue_item)

      return {
          "downloaded": downloaded_count,
          "failed": failed_count,
          "total_bytes": total_bytes,
      }
  ```
- **Dependencies**: Task 5.1
- **Estimated effort**: 2 hours

#### Task 5.3: Create Progress-Aware Download Worker
- **Description**: Modify worker to report progress during download (not just after)
- **Files to modify**:
  - `src/coordinators/download_mode_coordinator.py` (new method)
  - `src/extractors/attachment_downloader.py` (add progress callback support)
- **Implementation**:
  ```python
  # In download_mode_coordinator.py
  def _download_worker_with_progress(
      self,
      queue_item: AttachmentQueueItem,
      base_download_path: str,
      display: MultiProgressDisplay,
      task_id: TaskID,
  ) -> dict[str, Any]:
      """Worker function for parallel downloads with real-time progress updates."""

      try:
          # Get attachment metadata
          attachment = self._repository.get_attachment_by_id(queue_item.attachment_id)
          if not attachment:
              return {
                  "success": False,
                  "error": f"Attachment not found: {queue_item.attachment_id}",
              }

          # Create downloader with progress callback
          def progress_callback(bytes_downloaded: int):
              """Called during download to update progress."""
              display.update(task_id, advance=bytes_downloaded)

          downloader = AttachmentDownloader(
              repository=self._repository,
              logger=self._logger,
              base_download_path=base_download_path,
              progress_callback=progress_callback,  # NEW
          )

          # Download file
          download_result = downloader.download_attachment(attachment)

          return {
              "success": download_result["success"],
              "download_result": download_result,
              "error": download_result.get("error_message") if not download_result["success"] else None,
          }

      except Exception as e:
          return {"success": False, "error": str(e)}

  # In attachment_downloader.py - modify __init__ and _download_attachment_file
  def __init__(
      self,
      repository: Repository,
      logger: Logger,
      base_download_path: str = "./attachments",
      max_retries: int = 3,
      chunk_size: int = 8192,
      connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
      read_timeout: int = DEFAULT_READ_TIMEOUT,
      progress_callback: Optional[Callable[[int], None]] = None,  # NEW
  ):
      # ... existing code ...
      self._progress_callback = progress_callback

  # In _download_attachment_file - modify the download loop:
  with open(temp_file_path, "wb") as f:
      for chunk in response.iter_content(chunk_size=self._chunk_size):
          if chunk:
              f.write(chunk)
              hash_obj.update(chunk)
              bytes_downloaded += len(chunk)

              # Report progress if callback provided
              if self._progress_callback:
                  self._progress_callback(len(chunk))  # NEW
  ```
- **Dependencies**: Task 5.1, Task 5.2
- **Estimated effort**: 1.5 hours

#### Task 5.4: Add UI Module Structure
- **Description**: Create UI module for reusable components
- **Files to create**:
  - `src/ui/__init__.py` (export MultiProgressDisplay)
- **Implementation**:
  ```python
  """UI components for terminal display."""

  from .multi_progress_display import MultiProgressDisplay

  __all__ = ["MultiProgressDisplay"]
  ```
- **Dependencies**: Task 5.1
- **Estimated effort**: 15 minutes

### Phase 6: Documentation and Cleanup

#### Task 6.1: Update Configuration Documentation
- **Description**: Document new concurrent_downloads setting
- **Files to modify**:
  - `config/example.settings.yaml` (Lines 73-78)
  - `README.md` (if configuration section exists)
  - `docs/ATTACHMENT_MIGRATION_GUIDE.md`
- **Content**:
  ```yaml
  # Attachment handling
  attachments:
    auto_download: false              # Automatically download attachments during extraction
    concurrent_downloads: 3           # Number of parallel downloads (1-10)
                                      # Higher values = faster downloads but more memory/network
                                      # Recommended: 3-5 for most systems
    max_concurrent_downloads: 10      # Upper limit for validation
  ```
- **Dependencies**: Task 1.1
- **Estimated effort**: 30 minutes

#### Task 5.2: Add Inline Code Comments
- **Description**: Document parallel execution flow in code
- **Files to modify**:
  - `src/coordinators/download_mode_coordinator.py`
- **Comments to add**:
  - Why ThreadPoolExecutor is used
  - Thread-safety considerations
  - Why database updates are serialized
- **Dependencies**: Task 2.2
- **Estimated effort**: 30 minutes

#### Task 5.3: Update Migration Guide
- **Description**: Add notes about parallel downloads in migration workflow
- **Files to modify**:
  - `docs/ATTACHMENT_MIGRATION_GUIDE.md`
- **Content**: Add section on performance tuning with concurrent_downloads
- **Dependencies**: Task 5.1
- **Estimated effort**: 30 minutes

## Codebase Integration Points

### Files to Modify

1. **`config/example.settings.yaml`** (Lines 73-74)
   - Add `concurrent_downloads: 3` and `max_concurrent_downloads: 10`

2. **`src/config/config_models.py`** (Lines 202-212)
   - Add fields to `AttachmentConfig` dataclass
   - Add validation in `__post_init__`

3. **`src/coordinators/download_mode_coordinator.py`** (Lines 269-383)
   - Add `_download_worker()` method (new ~60 lines)
   - Refactor `_process_downloads()` for ThreadPoolExecutor (~100 lines)

4. **`tests/test_download_coordinator.py`** (existing file)
   - Add test class for worker function (~50 lines)
   - Add tests for parallel execution (~100 lines)

5. **`tests/integration/test_download_mode_integration.py`** (existing file)
   - Add integration test for parallel downloads (~80 lines)

6. **`docs/ATTACHMENT_MIGRATION_GUIDE.md`** (existing file)
   - Add performance tuning section (~20 lines)

### New Files to Create

1. **`tests/config/test_config_models.py`** (if doesn't exist)
   - Unit tests for AttachmentConfig validation

2. **`tests/performance/test_parallel_download_performance.py`**
   - Performance benchmark tests

### Existing Patterns to Follow

1. **Configuration Pattern** (from `config_manager.py`)
   - Use frozen dataclasses with `__post_init__` validation
   - Raise `ValueError` for invalid config values
   - Provide clear error messages with current vs expected values

2. **Threading Pattern** (from `token_bucket.py`)
   - Use `threading.Lock()` for shared state
   - Use `with self._lock:` context manager
   - Keep critical sections small

3. **Testing Pattern** (from `test_download_coordinator.py`)
   - Use pytest fixtures for dependencies
   - Mock external services (AttachmentDownloader, HTTP)
   - Test both success and failure paths
   - Use `patch()` for class instantiation mocking

4. **Error Handling Pattern** (from `download_mode_coordinator.py`)
   - Wrap operations in try-except
   - Update status and error messages
   - Log errors with context
   - Always update timestamps

## Technical Design

### Architecture: Worker Pool with Sequential Database Updates

```
┌─────────────────────────────────────────────────────────┐
│          DownloadModeCoordinator                        │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ _process_downloads()                               │ │
│  │                                                    │ │
│  │  ┌──────────────────────────────────────────┐    │ │
│  │  │ ThreadPoolExecutor (max_workers=N)       │    │ │
│  │  │                                          │    │ │
│  │  │  ┌────────┐  ┌────────┐  ┌────────┐    │    │ │
│  │  │  │Worker 1│  │Worker 2│  │Worker N│    │    │ │
│  │  │  │        │  │        │  │        │    │    │ │
│  │  │  │Download│  │Download│  │Download│    │    │ │
│  │  │  │   +    │  │   +    │  │   +    │    │    │ │
│  │  │  │ Hash   │  │ Hash   │  │ Hash   │    │    │ │
│  │  │  └────┬───┘  └────┬───┘  └────┬───┘    │    │ │
│  │  │       │           │           │         │    │ │
│  │  │       └───────────┴───────────┘         │    │ │
│  │  │                   │                     │    │ │
│  │  └───────────────────┼─────────────────────┘    │ │
│  │                      │                          │ │
│  │                      ▼                          │ │
│  │        ┌─────────────────────────────┐         │ │
│  │        │   as_completed() iterator   │         │ │
│  │        │                             │         │ │
│  │        │  Process results one by one │         │ │
│  │        │  in main thread:            │         │ │
│  │        │  - Update attachment record │         │ │
│  │        │  - Update queue status      │         │ │
│  │        │  - Update progress bar      │         │ │
│  │        └─────────────────────────────┘         │ │
│  │                      │                          │ │
│  │                      ▼                          │ │
│  │        ┌─────────────────────────────┐         │ │
│  │        │ Repository (SQLite)         │         │ │
│  │        │ - save_attachments()        │         │ │
│  │        │ - update_queue_status()     │         │ │
│  │        └─────────────────────────────┘         │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### Data Flow

1. **Setup Phase**:
   - Load `concurrent_downloads` from config (default: 3)
   - Create `ThreadPoolExecutor` with max_workers from config
   - Initialize Rich progress bar

2. **Submit Phase**:
   - Submit all queue items to executor via `_download_worker()`
   - Store `future_to_item` mapping for result handling

3. **Download Phase** (in worker threads):
   - Each worker gets queue item
   - Looks up attachment metadata (thread-safe read)
   - Creates own `AttachmentDownloader` instance
   - Downloads file to disk with streaming + hash
   - Returns result dict (no database writes)

4. **Collection Phase** (main thread):
   - Iterate over `as_completed(futures)`
   - For each completed download:
     - Update attachment record with local_file_path
     - Update queue item status (done/failed)
     - Update progress bar (+1)
   - All database writes happen sequentially in main thread

5. **Completion Phase**:
   - ThreadPoolExecutor context manager ensures all threads complete
   - Return download statistics

### Thread-Safety Guarantees

| Component | Thread-Safe? | Strategy |
|-----------|--------------|----------|
| ConfigManager | ✅ Yes | Singleton with locks |
| Repository reads | ✅ Yes | SQLite supports concurrent reads |
| Repository writes | ✅ Yes | Serialized in main thread only |
| AttachmentDownloader | ⚠️ Per-thread | Each worker creates own instance |
| requests.Session | ⚠️ Per-thread | Created per AttachmentDownloader |
| Rich Progress | ✅ Yes | Thread-safe updates |
| Download counters | ✅ Yes | Updated only in main thread |

### Error Handling Strategy

```python
# Worker level (in thread)
try:
    attachment = repository.get_attachment_by_id(item.attachment_id)
    downloader = AttachmentDownloader(...)
    result = downloader.download_attachment(attachment)
    return {"success": True, "result": result}
except Exception as e:
    logger.error(f"Worker error: {e}")
    return {"success": False, "error": str(e)}

# Coordinator level (main thread)
for future in as_completed(futures):
    result = future.result()  # Get worker return value

    if result["success"]:
        # Update database with success
        queue_item.status = "done"
    else:
        # Update database with failure
        queue_item.status = "failed"
        queue_item.last_error = result["error"]
        queue_item.attempt_count += 1

    # Always update queue status
    repository.update_attachment_queue_status(queue_item)
```

## Dependencies and Libraries

### New Dependencies

- **None required** - Using standard library `concurrent.futures.ThreadPoolExecutor`

### Existing Libraries (already in use)

- `requests` - HTTP downloads with retry logic (one session per worker)
- `rich` - Progress bar (thread-safe updates)
- `sqlite3` - Database (reads are thread-safe, writes serialized)
- `threading` - Locks for ConfigManager (already used)

## Testing Strategy

### Unit Tests

1. **Configuration validation**:
   - Valid concurrent_downloads values (1, 3, 5, 10)
   - Invalid values (0, 11, -1, non-integer)
   - Default value when not specified

2. **Worker function**:
   - Successful download return value
   - Attachment not found handling
   - Download failure (network error)
   - Exception in worker

3. **Parallel execution flow**:
   - ThreadPoolExecutor called with correct max_workers
   - All queue items submitted
   - Results processed via as_completed()
   - Database updates happen sequentially
   - Progress bar updated correctly

### Integration Tests

1. **Real database + parallel downloads**:
   - Create 10 attachment queue items
   - Mock HTTP responses with `requests_mock`
   - Run download_pass with concurrent_downloads=3
   - Verify all items status = "done"
   - Verify all files downloaded to correct paths
   - Check no SQLite errors from concurrent access

2. **Thread-safety verification**:
   - Concurrent reads to Repository (get_attachment_by_id)
   - Sequential writes to Repository (update_queue_status)
   - No database corruption or errors

### Performance Tests

1. **Speedup measurement**:
   - Benchmark 20 downloads with 100ms delay each
   - Sequential (concurrent_downloads=1): ~2 seconds
   - Parallel (concurrent_downloads=5): ~400-500ms
   - Assert speedup >= 3x

### Edge Cases to Cover

1. **concurrent_downloads = 1**: Should work like original sequential code
2. **More workers than items**: e.g., 10 workers but only 3 items to download
3. **All downloads fail**: Verify failed count is correct
4. **Mixed success/failure**: Some downloads succeed, others fail
5. **Keyboard interrupt**: Graceful shutdown of thread pool
6. **Very large concurrent value**: Validation should prevent > max_concurrent_downloads

## Success Criteria

- [x] Configuration schema updated with validation (1-10 range)
- [x] DownloadModeCoordinator refactored to use ThreadPoolExecutor
- [x] All existing unit tests still pass
- [x] New unit tests for parallel execution achieve 90%+ coverage
- [x] Integration tests verify thread-safe database operations
- [x] Performance benchmark shows >= 3x speedup with concurrent_downloads=5
- [x] Sequential mode still works (concurrent_downloads=1)
- [x] No SQLite errors under parallel load
- [x] Progress bar updates smoothly during parallel downloads
- [x] Error handling preserves all existing retry/tracking behavior
- [x] Documentation updated with new configuration option

## Notes and Considerations

### Implementation Notes

1. **Why ThreadPoolExecutor over asyncio?**
   - Existing code is synchronous (requests library)
   - Converting to async/await would require refactoring AttachmentDownloader
   - ThreadPoolExecutor integrates with minimal changes
   - Sufficient performance for I/O-bound operations

2. **Why serialize database writes?**
   - Simpler error handling and state management
   - Avoids SQLite write locking complexity
   - Most time is spent in network I/O anyway
   - Single-threaded writes are safer and easier to debug

3. **Memory usage with parallel downloads**:
   - Recent fix: Attachments now stream to disk (not kept in memory)
   - With 5 workers × 8KB chunk size = only ~40KB peak memory
   - Safe to run many parallel downloads without memory concerns

### Potential Challenges

1. **SQLite thread-safety**:
   - Mitigation: Only read in workers, write in main thread
   - Alternative: Use `check_same_thread=False` with caution

2. **requests.Session thread-safety**:
   - Mitigation: Create new AttachmentDownloader per worker (has own session)
   - Each worker gets isolated HTTP session with retry logic

3. **Progress bar accuracy**:
   - Rich Progress.update() is thread-safe
   - Use as_completed() to update progress as each download finishes

### Future Enhancements

1. **Adaptive concurrency**: Auto-tune workers based on network speed
2. **Rate limiting per-domain**: Respect server rate limits across workers
3. **Resume support**: Skip already-downloaded files by hash comparison
4. **Download prioritization**: Process larger files first for better parallelism
5. **Bandwidth throttling**: Limit total download speed across all workers

---

**This plan is ready for execution with `/execute-plan PRPs/parallel-attachment-downloads.md`**
