"""Migration commands for TightBeam CLI."""

import atexit
import tempfile
from pathlib import Path
from typing import Annotated, List, Optional

import typer

from src.constants import (
    DEFAULT_OPTIMIZATION_LEVEL,
    ERROR_EMOJI,
    INFO_EMOJI,
    MIGRATION_EMOJI,
)
from src.exceptions import (
    ConfigurationError,
)
from src.utils import ProcessLock, ProcessLockError

from .services import ServiceFactory, SharedServices

# Get shared console instance
console = ServiceFactory.get_console()


def _check_authentication(console) -> None:
    """Check if user is authenticated before allowing migration operations."""
    import os
    import sys

    from src.auth import AuthProvider
    from src.exceptions import OAuth2Error

    # Check for environment token first
    jobber_token = os.environ.get("JOBBER_TOKEN")
    # Simple validation - make sure it's not empty
    if jobber_token and jobber_token.strip():
        return  # Authentication via environment token is valid

    # Check OAuth2 authentication
    try:
        oauth_manager = ServiceFactory.create_oauth2_manager()
        repository = ServiceFactory.create_repository()

        # Check for stored tokens
        stored_tokens = repository.get_oauth_tokens()
        if stored_tokens:
            # Try to validate the stored tokens
            auth_provider = AuthProvider(oauth_manager, repository)
            auth_provider.get_token()  # This will validate and refresh if needed
            return  # OAuth2 authentication is valid
    except ConfigurationError:
        pass  # OAuth2 not configured
    except OAuth2Error:
        pass  # OAuth2 tokens invalid
    except Exception:
        pass  # Other OAuth2 issues

    # No valid authentication found
    console.print(f"\n[red]{ERROR_EMOJI} Authentication Required[/red]")
    console.print("Migration commands require authentication to access the Jobber API.")
    console.print(f"\n[bold cyan]{INFO_EMOJI} Choose one of the following authentication methods:[/bold cyan]")
    console.print("1. [green]Environment Token:[/green] Set JOBBER_TOKEN environment variable")
    console.print("2. [green]OAuth2 Setup:[/green] Run 'tightbeam oauth init' to authenticate")
    console.print(
        f"\n[yellow]{INFO_EMOJI} For more information:[/yellow] "
        "Run 'tightbeam oauth status' to check your current authentication"
    )
    sys.exit(1)


# Create migrate subcommand group
migrate_app = typer.Typer(
    name="migrate",
    help="Data migration commands",
    add_completion=False,
    invoke_without_command=True,
)


@migrate_app.callback()
def migrate_callback(
    ctx: typer.Context,
    db: Annotated[Optional[Path], typer.Option(help="SQLite database path")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable verbose logging")] = False,
    optimization_level: Annotated[
        str,
        typer.Option(
            help=(
                "Rate limiting optimization level:\n"
                "• conservative (4 req/s): Safest option with 52% safety margin, recommended for production\n"
                "• moderate (6 req/s): Balanced performance with 28% safety margin, default recommended\n"
                "• aggressive (8 req/s): Maximum speed with 4% safety margin, requires active monitoring"
            )
        ),
    ] = DEFAULT_OPTIMIZATION_LEVEL,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Skip entities that already exist in database (for resuming interrupted migrations)",
        ),
    ] = False,
) -> None:
    """
    Data migration commands for TightBeam.

    Two-pass ETL pattern:
    - max-extract: Extract all metadata (Pass 1)
    - download-attachments: Download binary files (Pass 2)
    """
    # Initialize configuration manager
    try:
        config_manager = ServiceFactory.create_config_manager()
    except ConfigurationError as e:
        typer.echo(f"Error: Configuration loading failed: {e}")
        raise typer.Exit(1) from e

    # Validate optimization level using ConfigManager
    try:
        config_manager.get_rate_limit_config(optimization_level)
    except ConfigurationError:
        available_levels = ["conservative", "moderate", "aggressive"]
        typer.echo(
            f"Error: Invalid optimization level '{optimization_level}'. Choose from: {', '.join(available_levels)}"
        )
        raise typer.Exit(1) from None

    # Store shared configuration in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj.update(
        {
            "db": SharedServices.resolve_db_path(db),
            "verbose": verbose,
            "optimization_level": optimization_level,
            "resume": resume,
        }
    )

    if verbose:
        console.print(
            f"{MIGRATION_EMOJI} [bold blue]Migration Verbose Mode:[/bold blue] Detailed output enabled", style="dim"
        )

    # Check authentication before allowing migration commands
    _check_authentication(console)

    # Acquire process lock to prevent concurrent migrations
    lock_file = Path(tempfile.gettempdir()) / "tightbeam_migration.lock"
    process_lock = ProcessLock(lock_file, "migration")

    try:
        process_lock.acquire()
    except ProcessLockError as e:
        console.print(f"\n[red]{ERROR_EMOJI} {e}[/red]")
        console.print(f"\n[yellow]{INFO_EMOJI} Tip:[/yellow] Use 'ps aux | grep tightbeam' to find running processes\n")
        raise typer.Exit(1) from None

    # Store lock in context and register cleanup
    ctx.obj["process_lock"] = process_lock
    atexit.register(process_lock.release)



@migrate_app.command(name="download-attachments")
def download_attachments(
    db: Annotated[
        Optional[Path],
        typer.Option(
            "--db",
            help="Path to SQLite database file",
            show_default=True,
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            help="Directory for downloaded attachment files",
            show_default=True,
        ),
    ] = Path("./attachments"),
) -> None:
    """Download pending attachment files from Jobber with parallel downloads.

    Phase 2 of the two-phase ETL pattern for binary file downloads.
    Fetches all attachments with download_status='pending' and saves them
    to hash-based storage: {sha256_hash}.{original_extension}

    Uses parallel downloads with multi-progress display showing individual
    download progress and aggregate stats.

    The database must already contain attachment metadata from Phase 1
    (entity extraction).

    Examples:
        # Download all pending attachments
        tightbeam migrate download-attachments

        # Specify custom database and output directory
        tightbeam migrate download-attachments --db ./data/export.db --output-dir ./files
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from src.extractors.attachment_downloader import AttachmentDownloader
    from src.ui.migration_ui import MigrationUI

    # Resolve database path with environment variable and config fallback
    db = SharedServices.resolve_db_path(db)

    console.print(f"\n{INFO_EMOJI} Starting parallel attachment downloads")
    console.print(f"   Database: {db}")
    console.print(f"   Output directory: {output_dir}\n")

    # Validate database exists
    if not db.exists():
        console.print(f"{ERROR_EMOJI} Database not found: {db}", style="bold red")
        console.print("   Run 'tightbeam migrate max-extract' first to extract metadata\n")
        raise typer.Exit(code=1)

    try:
        # Initialize services
        repository = ServiceFactory.create_repository(db)
        # Don't use verbose logger - it conflicts with Rich Live display
        # Debug logs will go to file if configured
        logger = ServiceFactory.create_logger(verbose=False)
        config_manager = ServiceFactory.create_config_manager()

        # Get concurrent downloads and performance settings from config
        attachment_config = config_manager.get_attachment_config()
        max_workers = attachment_config.get("concurrent_downloads", 3)
        chunk_size = attachment_config.get("chunk_size", 65536)  # 64KB default
        pool_connections = attachment_config.get("http_pool_connections", 50)
        pool_maxsize = attachment_config.get("http_pool_maxsize", 50)

        # Validate max_workers against configured maximum
        max_allowed = attachment_config.get("max_concurrent_downloads", 50)
        max_workers = max(1, min(max_workers, max_allowed))

        # Get all pending attachments
        pending_attachments = repository.get_pending_attachments()

        if not pending_attachments:
            console.print(f"{INFO_EMOJI} No pending attachments found", style="yellow")
            console.print("   All attachments already downloaded or no attachments in database\n")
            return

        console.print(f"{INFO_EMOJI} Found {len(pending_attachments)} pending attachment(s)")
        console.print(f"{INFO_EMOJI} Using {max_workers} concurrent downloads\n")

        # Calculate total bytes
        total_bytes = sum(att.file_size or 0 for att in pending_attachments)

        # Track results
        downloaded_count = 0
        failed_count = 0
        total_bytes_downloaded = 0

        # Create a logger wrapper that suppresses output during progress display
        class DisplayLogger:
            """Logger wrapper that suppresses output to avoid conflicting with MigrationUI."""
            def info(self, msg):
                pass  # Suppress info messages

            def debug(self, msg):
                pass  # Suppress debug messages

            def success(self, msg):
                pass  # Success logged separately

            def warning(self, msg):
                pass  # Suppress warnings during display

            def error(self, msg):
                pass  # Errors shown in summary

            def log_summary(self, summary):
                pass  # Suppress summary output

        display_logger = DisplayLogger()

        # Create a null repository that prevents worker threads from writing to SQLite
        # This avoids "cannot commit - no transaction is active" errors
        class NullRepository:
            """No-op repository for worker threads - prevents SQLite threading issues."""
            def update_attachment_download(self, **kwargs):
                pass  # Database updates handled by main thread

        null_repository = NullRepository()

        # Worker function for parallel downloads
        def download_worker(attachment, migration_ui, _unused_task_id):
            try:
                # Create progress task when worker starts (not upfront for all 30k files)
                file_size = attachment.file_size or 0
                task_name = attachment.file_name or attachment.id[:12]
                task_id = migration_ui.add_download_task(task_name, file_size)

                # Create progress callback
                def progress_callback(bytes_chunk: int):
                    migration_ui.update_download_task(task_id, bytes_chunk)

                # Create downloader for this thread - use null repository and display logger
                # to prevent SQLite threading issues (main thread handles all DB writes)
                # Use configured chunk_size and pool settings for optimal performance
                downloader = AttachmentDownloader(
                    repository=null_repository,  # Prevents worker thread DB writes
                    logger=display_logger,  # Use wrapper instead of verbose logger
                    base_download_path=str(output_dir),
                    max_retries=3,
                    chunk_size=chunk_size,  # Use configured chunk size
                    progress_callback=progress_callback,
                )
                # Update HTTP adapter with configured pool settings for high-speed connections
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry

                retry_strategy = Retry(
                    total=3,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["HEAD", "GET", "OPTIONS"],
                    backoff_factor=1,
                )
                adapter = HTTPAdapter(
                    max_retries=retry_strategy,
                    pool_connections=pool_connections,  # From config
                    pool_maxsize=pool_maxsize,  # From config
                )
                downloader._session.mount("http://", adapter)
                downloader._session.mount("https://", adapter)

                # Download file
                result = downloader.download_attachment(attachment)

                # Hide progress bar immediately when download completes
                # (Don't wait for main thread DB write - that causes "jammed" appearance)
                migration_ui.complete_download_task(task_id, task_name)

                return {
                    "attachment": attachment,
                    "success": result["success"],
                    "result": result,
                    "task_id": task_id,
                }
            except Exception as e:
                logger.error(f"Worker exception for {attachment.id}: {e}")
                return {
                    "attachment": attachment,
                    "success": False,
                    "result": {"error_message": str(e)},
                    "task_id": None,
                }

        # Download with MigrationUI progress display
        migration_ui = MigrationUI(console)
        start_time = time.time()

        try:
            # Start download progress tracking
            migration_ui.start_download_progress(
                total_files=len(pending_attachments),
                total_bytes=total_bytes,
            )

            # Submit all downloads (but don't create progress tasks yet - worker will handle that)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}

                for attachment in pending_attachments:
                    task_name = attachment.file_name or attachment.id[:12]

                    # Note: We create the progress task inside the worker function
                    # to avoid creating 30,000 tasks upfront
                    # Submit worker WITHOUT pre-creating task
                    future = executor.submit(download_worker, attachment, migration_ui, None)
                    futures[future] = (attachment, None, task_name)

                # Process results as they complete
                try:
                    for future in as_completed(futures):
                        attachment, _, task_name = futures[future]
                        result = future.result()

                        if result["success"]:
                            # Update database in main thread (thread-safe)
                            repository.update_attachment_download(
                                attachment_id=attachment.id,
                                local_file_path=result["result"].get("local_file_path", ""),
                                hash=result["result"].get("hash", ""),
                                download_status="completed",
                                downloaded_at=result["result"].get("downloaded_at"),
                            )

                            downloaded_count += 1
                            total_bytes_downloaded += result["result"].get("bytes_downloaded", 0)
                        else:
                            # Update database with failure in main thread (thread-safe)
                            error_msg = result["result"].get("error_message", "Unknown error")
                            repository.update_attachment_download(
                                attachment_id=attachment.id,
                                download_status="failed",
                                download_error=error_msg,
                            )

                            failed_count += 1

                        # Note: Task is already hidden by worker thread (no need to call complete_task here)

                except KeyboardInterrupt:
                    # Cancel all pending futures immediately
                    for future in futures:
                        future.cancel()
                    # Executor context manager will clean up
                    raise  # Re-raise to outer except

        except KeyboardInterrupt:
            # Show keyboard interrupt message with MigrationUI
            migration_ui.show_keyboard_interrupt()
            # Fall through to show partial summary
        finally:
            # Finalize the MigrationUI display
            migration_ui.finalize()

        # Calculate duration
        duration = time.time() - start_time

        # Display summary using MigrationUI (unless completely interrupted)
        if downloaded_count > 0 or failed_count > 0:
            migration_ui.show_download_summary(
                total_files=downloaded_count,
                total_bytes=total_bytes_downloaded,
                duration=duration,
                failures=failed_count,
            )

            if failed_count > 0:
                console.print(f"\n{INFO_EMOJI} Check database download_error field for failure details:")
                console.print(
                    "   SELECT id, file_name, download_error FROM attachments "
                    "WHERE download_status = 'failed'\n"
                )

    except ConfigurationError as e:
        console.print(f"{ERROR_EMOJI} Configuration error: {e}", style="bold red")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"{ERROR_EMOJI} Unexpected error: {e}", style="bold red")
        raise typer.Exit(code=1) from None


def _format_bytes(bytes_count: int) -> str:
    """Format byte count as human-readable string.

    Args:
        bytes_count: Number of bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} TB"


@migrate_app.command(name="max-extract")
def max_extract(
    db: Annotated[
        Optional[Path],
        typer.Option(
            "--db",
            help="Path to SQLite database file",
            show_default=True,
        ),
    ] = None,
    entities: Annotated[
        Optional[List[str]],
        typer.Option(
            "--entities",
            help="Specific entities to extract (default: all)",
        ),
    ] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Resume from last checkpoint",
        ),
    ] = False,
    optimization_level: Annotated[
        str,
        typer.Option(
            "--optimization-level",
            help="Rate limiting optimization level (conservative/moderate/aggressive)",
            show_default=True,
        ),
    ] = "moderate",
) -> None:
    """Extract all Jobber data (Pass 1: metadata extraction with resumable checkpoints).

    Phase 7 orchestrated extraction that processes all entities in dependency order.
    Supports selective extraction and resume from checkpoint for interrupted migrations.

    This is Pass 1 of the two-phase ETL pattern - it extracts all metadata including
    attachment URLs but does not download binary files. Use 'download-attachments'
    after this command to fetch binaries (Pass 2).

    Examples:
        # Extract all entities
        tightbeam migrate max-extract

        # Extract specific entities only
        tightbeam migrate max-extract --entities clients --entities invoices

        # Resume interrupted extraction
        tightbeam migrate max-extract --resume

        # Use aggressive rate limiting for faster extraction
        tightbeam migrate max-extract --optimization-level aggressive
    """
    from src.coordinators.max_extract_coordinator import MaxExtractCoordinator
    from src.ui.migration_ui import MigrationUI

    # Resolve database path with environment variable and config fallback
    db = SharedServices.resolve_db_path(db)

    # Brief startup message (MigrationUI will show the detailed header)
    console.print(f"\n{MIGRATION_EMOJI} Starting Jobber Max Extract (Pass 1: Metadata)")
    console.print(f"   Optimization level: {optimization_level}")
    if entities:
        console.print(f"   Entities: {', '.join(entities)}")
    console.print()

    try:
        # Initialize services with optimization level
        repository = ServiceFactory.create_repository(db)
        logger = ServiceFactory.create_logger(verbose=True)
        config_manager = ServiceFactory.create_config_manager()

        # Create MigrationUI for Rich-based progress display (before JobberClient)
        migration_ui = MigrationUI(console)

        # Create authenticated Jobber client with rate limiting and UI integration
        auth_provider = ServiceFactory.create_auth_provider(repository, logger)
        jobber_client = ServiceFactory.create_rate_limited_jobber_client(
            auth_provider=auth_provider,
            repository=repository,
            config_manager=config_manager,
            optimization_level=optimization_level,
            migration_ui=migration_ui,
        )

        # Create entity mapper
        entity_mapper = ServiceFactory.create_entity_mapper()

        # Initialize coordinator with MigrationUI
        coordinator = MaxExtractCoordinator(
            jobber_client=jobber_client,
            repository=repository,
            logger=logger,
            entity_mapper=entity_mapper,
            migration_ui=migration_ui,
            db_path=str(db),
            config_manager=config_manager,
        )

        # Execute extraction (UI is handled by coordinator)
        summary = coordinator.extract_all(
            entities=entities,
            resume=resume,
        )

        # Simple completion message (detailed summary shown by MigrationUI during extraction)
        console.print(f"\n{MIGRATION_EMOJI} Extraction Complete!")
        console.print(f"   Total entities extracted: {summary['total_entities']}")

        # Show errors if any
        if summary['errors']:
            console.print(f"\n{ERROR_EMOJI} Errors ({len(summary['errors'])}):")
            for error in summary['errors']:
                console.print(f"   ✗ {error['entity_type']}: {error['error']}", style="bold red")

        console.print(
            f"\n{INFO_EMOJI} Next step: Run 'tightbeam migrate download-attachments' "
            "to fetch binaries (Pass 2)\n"
        )

    except KeyboardInterrupt:
        # Graceful shutdown already handled by MigrationUI
        console.print()  # Add spacing
        raise typer.Exit(code=130) from None
    except ConfigurationError as e:
        console.print(f"{ERROR_EMOJI} Configuration error: {e}", style="bold red")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"{ERROR_EMOJI} Extraction failed: {e}", style="bold red")
        raise typer.Exit(code=1) from None
