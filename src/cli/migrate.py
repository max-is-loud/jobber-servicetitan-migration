"""Migration commands for TightBeam CLI."""

from pathlib import Path
from typing import Annotated, List, Optional

import typer

from src.constants import (
    DEFAULT_OPTIMIZATION_LEVEL,
    MIGRATION_EMOJI,
    ERROR_EMOJI,
    INFO_EMOJI,
)
from src.exceptions import (
    ConfigurationError,
)

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
    if jobber_token:
        # Simple validation - make sure it's not empty
        if jobber_token.strip():
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
        f"\n[yellow]{INFO_EMOJI} For more information:[/yellow] Run 'tightbeam oauth status' to check your current authentication"
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
    batch_size: Annotated[
        int,
        typer.Option(
            "--batch-size",
            help="Number of attachments to fetch per batch",
            min=1,
            max=1000,
            show_default=True,
        ),
    ] = 100,
) -> None:
    """Download pending attachment files from Jobber.

    Phase 2 of the two-phase ETL pattern for binary file downloads.
    Fetches all attachments with download_status='pending' and saves them
    to hash-based storage: {sha256_hash}.{original_extension}

    The database must already contain attachment metadata from Phase 1
    (entity extraction).

    Examples:
        # Download all pending attachments
        tightbeam migrate download-attachments

        # Specify custom database and output directory
        tightbeam migrate download-attachments --db ./data/export.db --output-dir ./files

        # Control batch size for large datasets
        tightbeam migrate download-attachments --batch-size 50
    """
    from src.extractors.attachment_downloader import AttachmentDownloader
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

    # Resolve database path with environment variable and config fallback
    db = SharedServices.resolve_db_path(db)

    console.print(f"\n{INFO_EMOJI} Starting attachment download")
    console.print(f"   Database: {db}")
    console.print(f"   Output directory: {output_dir}")
    console.print(f"   Batch size: {batch_size}\n")

    # Validate database exists
    if not db.exists():
        console.print(f"{ERROR_EMOJI} Database not found: {db}", style="bold red")
        console.print(f"   Run 'tightbeam migrate jobber' first to extract metadata\n")
        raise typer.Exit(code=1)

    try:
        # Initialize services
        repository = ServiceFactory.create_repository(db)
        logger = ServiceFactory.create_logger(verbose=True)

        # Check for pending attachments
        pending_count_query = repository._connection.cursor()
        pending_count_query.execute("SELECT COUNT(*) FROM attachments WHERE download_status = 'pending'")
        total_pending = pending_count_query.fetchone()[0]
        pending_count_query.close()

        if total_pending == 0:
            console.print(f"{INFO_EMOJI} No pending attachments found", style="yellow")
            console.print(f"   All attachments already downloaded or no attachments in database\n")
            return

        console.print(f"{INFO_EMOJI} Found {total_pending} pending attachment(s)\n")

        # Initialize downloader
        downloader = AttachmentDownloader(
            repository=repository,
            logger=logger,
            base_download_path=str(output_dir),
            max_retries=3,
        )

        # Validate dependencies
        downloader.validate_dependencies()

        # Download with progress tracking
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading attachments...", total=total_pending)

            # Get initial stats
            stats = {"success": 0, "failed": 0, "total_bytes": 0}

            # Process in batches
            while True:
                batch = repository.get_pending_attachments()
                if not batch:
                    break

                # Limit batch size
                batch = batch[:batch_size]

                for attachment in batch:
                    result = downloader.download_attachment(attachment)

                    if result["success"]:
                        stats["success"] += 1
                        stats["total_bytes"] += result["bytes_downloaded"]
                    else:
                        stats["failed"] += 1

                    # Update progress
                    progress.update(task, advance=1)

                # If we got fewer than batch_size, we're done
                if len(batch) < batch_size:
                    break

        # Display summary
        console.print()
        console.print("📊 Download Summary:", style="bold cyan")
        console.print(f"   ✓ Success: {stats['success']} files ({_format_bytes(stats['total_bytes'])})")
        if stats["failed"] > 0:
            console.print(f"   ✗ Failed: {stats['failed']} files", style="bold red")
        console.print()

        if stats["failed"] > 0:
            console.print(f"{INFO_EMOJI} Check database download_error field for failure details:")
            console.print(f"   SELECT id, file_name, download_error FROM attachments WHERE download_status = 'failed'\n")

    except ConfigurationError as e:
        console.print(f"{ERROR_EMOJI} Configuration error: {e}", style="bold red")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"{ERROR_EMOJI} Unexpected error: {e}", style="bold red")
        raise typer.Exit(code=1)


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

    # Resolve database path with environment variable and config fallback
    db = SharedServices.resolve_db_path(db)

    console.print(f"\n{MIGRATION_EMOJI} Starting Jobber Max Extract (Pass 1: Metadata)")
    console.print(f"   Database: {db}")
    console.print(f"   Optimization level: {optimization_level}")
    console.print(f"   Resume: {resume}")
    if entities:
        console.print(f"   Entities: {', '.join(entities)}")
    else:
        console.print(f"   Entities: ALL (in dependency order)")
    console.print()

    try:
        # Initialize services with optimization level
        repository = ServiceFactory.create_repository(db)
        logger = ServiceFactory.create_logger(verbose=True)
        config_manager = ServiceFactory.create_config_manager()

        # Create authenticated Jobber client with rate limiting
        auth_provider = ServiceFactory.create_auth_provider(repository, logger)
        jobber_client = ServiceFactory.create_rate_limited_jobber_client(
            auth_provider=auth_provider,
            repository=repository,
            config_manager=config_manager,
            optimization_level=optimization_level,
        )

        # Create entity mapper
        entity_mapper = ServiceFactory.create_entity_mapper()

        # Initialize coordinator
        coordinator = MaxExtractCoordinator(
            jobber_client=jobber_client,
            repository=repository,
            logger=logger,
            entity_mapper=entity_mapper,
        )

        # Execute extraction
        console.print(f"{INFO_EMOJI} Beginning extraction...\n")

        summary = coordinator.extract_all(
            entities=entities,
            resume=resume,
        )

        # Display results
        console.print(f"\n{MIGRATION_EMOJI} Extraction Complete!")
        console.print(f"\n📊 Summary:")
        console.print(f"   Total entities extracted: {summary['total_entities']}")
        console.print(f"   Entity types processed: {len(summary['results'])}")

        # Show per-entity breakdown
        console.print(f"\n📦 By Entity Type:")
        for entity_type, count in summary['results'].items():
            # Special handling for notes - they're extracted inline, not as a separate entity
            if entity_type == "notes":
                # Query actual note count from database
                try:
                    note_count = repository._connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
                    status_icon = "✓" if note_count > 0 else "○"
                    console.print(f"   {status_icon} {entity_type}: {note_count} (extracted inline)")
                except Exception:
                    # If query fails, skip notes entirely
                    continue
            else:
                status_icon = "✓" if count > 0 else "○"
                console.print(f"   {status_icon} {entity_type}: {count}")

        # Show errors if any
        if summary['errors']:
            console.print(f"\n{ERROR_EMOJI} Errors ({len(summary['errors'])}):")
            for error in summary['errors']:
                console.print(f"   ✗ {error['entity_type']}: {error['error']}", style="bold red")

        console.print(f"\n{INFO_EMOJI} Next step: Run 'tightbeam migrate download-attachments' to fetch binaries (Pass 2)\n")

    except ConfigurationError as e:
        console.print(f"{ERROR_EMOJI} Configuration error: {e}", style="bold red")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"{ERROR_EMOJI} Extraction failed: {e}", style="bold red")
        raise typer.Exit(code=1)
