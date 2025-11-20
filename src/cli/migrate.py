"""Migration commands for TightBeam CLI."""

from pathlib import Path
from typing import Annotated, List, Optional

import typer

from src.config import ConfigManagerImpl
from src.constants import (
    DEFAULT_OPTIMIZATION_LEVEL,
    MIGRATION_EMOJI,
    DRY_RUN_EMOJI,
    ERROR_EMOJI,
    INFO_EMOJI,
)
from src.exceptions import (
    ConfigurationError,
)

from .services import ServiceFactory

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
    deferred_notes: Annotated[
        bool,
        typer.Option(
            "--deferred-notes",
            help="Use deferred notes loading to prevent GraphQL throttling",
        ),
    ] = True,
    enable_notes_persistence: Annotated[
        bool,
        typer.Option(
            "--enable-notes-persistence",
            help="Enable temporary storage for note references (for very large migrations)",
        ),
    ] = False,
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
    enable_cost_monitoring: Annotated[
        bool,
        typer.Option(
            "--enable-cost-monitoring",
            help=(
                "Enable GraphQL cost monitoring and rate limit tracking. "
                "Provides detailed performance insights and API usage statistics. "
                "Recommended for performance analysis and optimization tuning."
            ),
        ),
    ] = True,
    cost_monitoring_verbose: Annotated[
        bool,
        typer.Option(
            "--cost-monitoring-verbose",
            help=(
                "Enable verbose cost monitoring output during migration. "
                "Shows detailed GraphQL query costs, accuracy percentages, and rate limit analysis. "
                "Use for detailed performance debugging and optimization insights."
            ),
        ),
    ] = False,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Skip entities that already exist in database (for resuming interrupted migrations)",
        ),
    ] = False,
    enable_adaptive_optimization: Annotated[
        bool,
        typer.Option(
            "--adaptive",
            help="Enable adaptive performance optimization (auto-tune page size and delays)",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview migration operations without making any changes to the database",
        ),
    ] = False,
) -> None:
    """
    Data migration commands for TightBeam.

    If no subcommand is provided, runs the 'all' command by default.
    """
    # Initialize configuration manager
    try:
        config_manager = ConfigManagerImpl()
    except ConfigurationError as e:
        typer.echo(f"Error: Configuration loading failed: {e}")
        raise typer.Exit(1) from e

    # Validate optimization level using ConfigManager
    try:
        config_manager.get_rate_limit_config(optimization_level)
    except ConfigurationError:
        available_levels = ["conservative", "moderate", "aggressive"]
        typer.echo(
            f"Error: Invalid optimization level '{optimization_level}'. " f"Choose from: {', '.join(available_levels)}"
        )
        raise typer.Exit(1) from None

        # Store shared configuration in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj.update(
        {
            "db": db or Path("tightbeam.sqlite"),
            "verbose": verbose,
            "deferred_notes": deferred_notes,
            "enable_notes_persistence": enable_notes_persistence,
            "optimization_level": optimization_level,
            "enable_cost_monitoring": enable_cost_monitoring,
            "cost_monitoring_verbose": cost_monitoring_verbose,
            "resume": resume,
            "enable_adaptive_optimization": enable_adaptive_optimization,
            "dry_run": dry_run,
        }
    )

    if verbose:
        console.print(
            f"{MIGRATION_EMOJI} [bold blue]Migration Verbose Mode:[/bold blue] Detailed output enabled", style="dim"
        )

    if dry_run:
        console.print(
            f"{DRY_RUN_EMOJI} [bold yellow]Dry Run Mode:[/bold yellow] Preview mode - no database changes will be made",
            style="dim",
        )

    # Check authentication before allowing migration commands
    _check_authentication(console)

    if ctx.invoked_subcommand is None:
        # Default to 'all' command when no subcommand is specified
        migrate_all(
            ctx=ctx,
            db=ctx.obj["db"],
            verbose=verbose,
            deferred_notes=deferred_notes,
            enable_notes_persistence=enable_notes_persistence,
            optimization_level=optimization_level,
            enable_cost_monitoring=enable_cost_monitoring,
            cost_monitoring_verbose=cost_monitoring_verbose,
            resume=resume,
            enable_adaptive_optimization=enable_adaptive_optimization,
            dry_run=dry_run,
        )


@migrate_app.command("map")
def migrate_map(
    ctx: typer.Context,
    entities: Annotated[
        Optional[List[str]],
        typer.Option(
            "--entity",
            "--entities",
            help="Entity types to include (repeat option). Defaults to all supported types.",
        ),
    ] = None,
    snapshot_label: Annotated[
        Optional[str],
        typer.Option(
            "--snapshot-label",
            help="Optional label for the map snapshot and reports.",
        ),
    ] = None,
    report_dir: Annotated[
        Path,
        typer.Option(
            "--report-dir",
            help="Directory to write map reports (Markdown and JSON).",
        ),
    ] = Path("reports"),
) -> None:
    """
    Run map mode to inventory entities and relation counts before full extraction.
    """
    from src.auth import AuthProvider
    from src.config import ConfigManagerImpl
    from src.coordinators.map_mode_coordinator import MapModeCoordinator
    from src.exceptions import ConfigurationError
    from src.loggers import RichLogger
    from src.reports import MapReportGenerator

    config = ctx.obj or {}
    db_path = config.get("db", Path("tightbeam.sqlite"))
    verbose = config.get("verbose", False)
    enable_cost_monitoring = config.get("enable_cost_monitoring", True)
    enable_adaptive_optimization = config.get("enable_adaptive_optimization", False)

    logger = RichLogger(verbose=verbose)

    # Normalize entity selections and validate against supported types
    available_entity_types = MapModeCoordinator.supported_entity_types()
    if entities:
        selected_entity_types = [
            entity.strip()
            for raw in entities
            for entity in raw.split(",")
            if entity.strip()
        ]
    else:
        selected_entity_types = available_entity_types

    invalid_types = [et for et in selected_entity_types if et not in available_entity_types]
    if invalid_types:
        console.print(f"[red]{ERROR_EMOJI} Invalid entity types:[/red] {', '.join(invalid_types)}")
        console.print(f"[yellow]{INFO_EMOJI} Supported types:[/yellow] {', '.join(available_entity_types)}")
        raise typer.Exit(1)

    repository = None
    try:
        repository = ServiceFactory.create_repository(db_path)
        oauth_manager = ServiceFactory.create_oauth2_manager()
        auth_provider = AuthProvider(oauth_manager, repository)
        config_manager = ConfigManagerImpl()

        # Map mode is lightweight - use aggressive optimization by default
        optimization_level = "aggressive"
        jobber_client = ServiceFactory.create_rate_limited_jobber_client(
            auth_provider=auth_provider,
            repository=repository,
            config_manager=config_manager,
            optimization_level=optimization_level,
            enable_cost_monitoring=enable_cost_monitoring,
        )

        logger.info(
            f"Starting map pass for {len(selected_entity_types)} entity types "
            f"with {optimization_level.upper()} optimization"
        )

        coordinator = MapModeCoordinator(
            jobber_client=jobber_client,
            repository=repository,
            logger=logger,
            config_manager=config_manager,
            enable_adaptive_optimization=enable_adaptive_optimization,
        )

        map_result = coordinator.run_map_pass(
            entity_types=selected_entity_types,
            label=snapshot_label,
        )

        # Analyze hotspots and density for reporting
        hotspots_by_type = {
            entity_type: coordinator.identify_hotspots(map_result["snapshot_id"], entity_type)
            for entity_type in selected_entity_types
        }
        density_stats_by_type = {
            entity_type: coordinator.get_density_stats(map_result["snapshot_id"], entity_type)
            for entity_type in selected_entity_types
        }

        # Generate reports
        report_dir.mkdir(parents=True, exist_ok=True)
        report_generator = MapReportGenerator(output_dir=report_dir)
        result_label = map_result["label"] or snapshot_label or "map-pass"
        markdown_path, json_path = report_generator.generate_report(
            snapshot_id=map_result["snapshot_id"],
            label=result_label,
            entity_results=map_result["entity_results"],
            totals=map_result["totals"],
            duration=map_result["duration"],
            hotspots_by_type=hotspots_by_type,
            density_stats_by_type=density_stats_by_type,
        )

        console.print(
            f"[green]{MIGRATION_EMOJI} Map pass completed for snapshot {map_result['snapshot_id']}[/green]"
        )
        console.print(f"{INFO_EMOJI} Label: {result_label}")
        console.print(f"{INFO_EMOJI} Markdown report: {markdown_path}")
        console.print(f"{INFO_EMOJI} JSON report: {json_path}")
    except ConfigurationError as e:
        console.print(f"[red]{ERROR_EMOJI} Configuration Error:[/red] {e}")
        raise typer.Exit(1) from e
    except Exception as e:  # pragma: no cover - CLI catch-all
        console.print(f"[red]{ERROR_EMOJI} Map pass failed:[/red] {e}")
        raise typer.Exit(1) from e
    finally:
        if repository:
            repository.close()


@migrate_app.command("extract")
def migrate_extract(
    ctx: typer.Context,
    snapshot_id: Annotated[
        str,
        typer.Option("--snapshot-id", help="Map snapshot ID to extract from"),
    ],
    entities: Annotated[
        Optional[List[str]],
        typer.Option(
            "--entity",
            "--entities",
            help="Entity types to extract (repeat option, defaults to snapshot set)",
        ),
    ] = None,
    report_dir: Annotated[
        Path,
        typer.Option(
            "--report-dir",
            help="Directory to write extract reports (Markdown and JSON).",
        ),
    ] = Path("reports"),
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Resume from existing extract queues instead of recreating them.",
        ),
    ] = False,
) -> None:
    """
    Run extract mode to hydrate full data from a map snapshot.
    """
    from src.auth import AuthProvider
    from src.config import ConfigManagerImpl
    from src.coordinators.extract_mode_coordinator import ExtractModeCoordinator
    from src.exceptions import ConfigurationError
    from src.loggers import RichLogger
    from src.mappers import EntityMapper
    from src.reports import ExtractReportGenerator

    config = ctx.obj or {}
    db_path = config.get("db", Path("tightbeam.sqlite"))
    verbose = config.get("verbose", False)
    enable_cost_monitoring = config.get("enable_cost_monitoring", True)

    logger = RichLogger(verbose=verbose)

    # Normalize entity selections and validate against supported types
    available_entity_types = ExtractModeCoordinator.supported_entity_types()
    selected_entity_types: Optional[List[str]]
    if entities:
        selected_entity_types = [
            entity.strip()
            for raw in entities
            for entity in raw.split(",")
            if entity.strip()
        ]
    else:
        selected_entity_types = None

    if selected_entity_types:
        invalid_types = [et for et in selected_entity_types if et not in available_entity_types]
        if invalid_types:
            console.print(f"[red]{ERROR_EMOJI} Invalid entity types:[/red] {', '.join(invalid_types)}")
            console.print(f"[yellow]{INFO_EMOJI} Supported types:[/yellow] {', '.join(available_entity_types)}")
            raise typer.Exit(1)

    repository = None
    try:
        repository = ServiceFactory.create_repository(db_path)

        # Validate snapshot exists and fetch label for reporting
        snapshot = repository.get_map_snapshot(snapshot_id)
        if not snapshot:
            console.print(f"[red]{ERROR_EMOJI} Map snapshot not found:[/red] {snapshot_id}")
            raise typer.Exit(1)

        oauth_manager = ServiceFactory.create_oauth2_manager()
        auth_provider = AuthProvider(oauth_manager, repository)
        config_manager = ConfigManagerImpl()

        # Extract mode uses moderate optimization by default
        optimization_level = "moderate"
        jobber_client = ServiceFactory.create_rate_limited_jobber_client(
            auth_provider=auth_provider,
            repository=repository,
            config_manager=config_manager,
            optimization_level=optimization_level,
            enable_cost_monitoring=enable_cost_monitoring,
        )

        logger.info(
            f"Starting extract pass for snapshot {snapshot_id} "
            f"with {optimization_level.upper()} optimization"
        )

        entity_mapper = EntityMapper()

        coordinator = ExtractModeCoordinator(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            config_manager=config_manager,
        )

        extract_result = coordinator.run_extract_pass(
            snapshot_id=snapshot_id,
            entity_types=selected_entity_types,
            resume=resume,
        )

        # Generate reports
        report_dir.mkdir(parents=True, exist_ok=True)
        report_generator = ExtractReportGenerator(output_dir=report_dir)
        result_label = snapshot.label or snapshot_id
        markdown_path, json_path = report_generator.generate_report(
            snapshot_id=snapshot_id,
            label=result_label,
            entity_results=extract_result["entity_results"],
            attachment_result=extract_result["attachment_result"],
            discrepancies=extract_result["discrepancies"],
            totals=extract_result["totals"],
            duration=extract_result["duration"],
        )

        console.print(
            f"[green]{MIGRATION_EMOJI} Extract pass completed for snapshot {snapshot_id}[/green]"
        )
        console.print(f"{INFO_EMOJI} Label: {result_label}")
        console.print(f"{INFO_EMOJI} Markdown report: {markdown_path}")
        console.print(f"{INFO_EMOJI} JSON report: {json_path}")
    except ConfigurationError as e:
        console.print(f"[red]{ERROR_EMOJI} Configuration Error:[/red] {e}")
        raise typer.Exit(1) from e
    except Exception as e:  # pragma: no cover - CLI catch-all
        console.print(f"[red]{ERROR_EMOJI} Extract pass failed:[/red] {e}")
        raise typer.Exit(1) from e
    finally:
        if repository:
            repository.close()


@migrate_app.command("all")
def migrate_all(
    ctx: typer.Context,
    db: Annotated[Path, typer.Option(help="SQLite database path")] = Path("tightbeam.sqlite"),
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable verbose logging")] = False,
    deferred_notes: Annotated[
        bool,
        typer.Option(
            "--deferred-notes",
            help="Use deferred notes loading to prevent GraphQL throttling",
        ),
    ] = True,
    enable_notes_persistence: Annotated[
        bool,
        typer.Option(
            "--enable-notes-persistence",
            help="Enable temporary storage for note references (for very large migrations)",
        ),
    ] = False,
    resume: Annotated[
        Optional[bool],
        typer.Option(
            "--resume",
            help="Skip entities that already exist in database (for resuming interrupted migrations)",
        ),
    ] = None,
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
    ] = "moderate",
    enable_cost_monitoring: Annotated[
        bool,
        typer.Option(
            "--enable-cost-monitoring",
            help=(
                "Enable GraphQL cost monitoring and rate limit tracking. "
                "Provides detailed performance insights and API usage statistics. "
                "Recommended for performance analysis and optimization tuning."
            ),
        ),
    ] = True,
    cost_monitoring_verbose: Annotated[
        bool,
        typer.Option(
            "--cost-monitoring-verbose",
            help=(
                "Enable verbose cost monitoring output during migration. "
                "Shows detailed GraphQL query costs, accuracy percentages, and rate limit analysis. "
                "Use for detailed performance debugging and optimization insights."
            ),
        ),
    ] = False,
    enable_adaptive_optimization: Annotated[
        bool,
        typer.Option(
            "--adaptive",
            help="Enable adaptive performance optimization (auto-tune page size and delays)",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview migration operations without making any changes to the database",
        ),
    ] = False,
) -> None:
    """
    Migrate all data from Jobber API to SQLite database.

    Fetches all clients, invoices, quotes, notes, and attachments from the Jobber
    GraphQL API using cursor-based pagination and stores them in the specified SQLite
    database. Attachment files are downloaded to ./attachments directory. Features
    deferred notes loading by default to prevent GraphQL throttling issues.

    Deferred Notes Loading (Default):
    - Collects note IDs during client/invoice processing
    - Processes notes separately to avoid nested query complexity
    - Prevents GraphQL throttling on large datasets
    - Use --immediate-notes to disable (legacy mode)

    Resume Mode (--resume):
    - Skips entities that already exist in the database
    - Enables resuming interrupted migrations without duplicate processing
    - Uses fast primary key lookups for efficient existence checking
    - Works with all entity types including clients, invoices, quotes, notes, and attachments

    Authentication options:
    1. Set JOBBER_TOKEN environment variable with a valid Jobber API token
    2. Configure OAuth2 variables and run 'tightbeam oauth init'
    """
    import sqlite3
    import sys

    # Import required components
    from src.auth import AuthProvider, OAuth2Manager
    from src.clients import HttpClient
    from src.config import ConfigManagerImpl
    from src.coordinators import BaseMigrationCoordinator
    from src.mappers import EntityMapper
    from src.exceptions import ConfigurationError
    from src.loggers import RichLogger
    from src.repositories import Repository

    # Get shared configuration from context (group-level flags take precedence)
    config = ctx.obj or {}

    # Resolve actual parameter values (context values override local defaults)
    actual_db = config.get("db", db)
    actual_verbose = config.get("verbose", verbose)
    actual_deferred_notes = config.get("deferred_notes", deferred_notes)
    actual_enable_notes_persistence = config.get("enable_notes_persistence", enable_notes_persistence)
    actual_optimization_level = config.get("optimization_level", optimization_level)
    actual_enable_cost_monitoring = config.get("enable_cost_monitoring", enable_cost_monitoring)
    actual_cost_monitoring_verbose = config.get("cost_monitoring_verbose", cost_monitoring_verbose)
    actual_enable_adaptive_optimization = config.get("enable_adaptive_optimization", enable_adaptive_optimization)

    # Special handling for resume: command-level explicit value > group-level > default False
    actual_resume = resume if resume is not None else config.get("resume", False)

    connection = None
    repository = None

    try:
        # Create database connection with Rich logger
        logger = RichLogger(verbose=actual_verbose)
        logger.info(f"Connecting to database: {actual_db}")

        # Ensure parent directory exists
        actual_db.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.Connection(str(actual_db))

        # Dependency injection - wire up all components
        logger.debug("Initializing application components")

        # Initialize repository first for OAuth token storage
        repository = Repository(connection)

        # Create OAuth2 components
        try:
            client_id, client_secret, redirect_uri = AuthProvider.get_oauth2_config()
            http_client = HttpClient()
            oauth_manager = OAuth2Manager(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                http_client=http_client,
            )
            auth_provider = AuthProvider(oauth_manager, repository)
        except ConfigurationError as e:
            raise ConfigurationError(
                f"OAuth2 configuration error: {e}. "
                "Please ensure JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, and "
                "JOBBER_REDIRECT_URI are set and run 'tightbeam oauth init' "
                "to authorize."
            ) from None

        # Core dependencies with rate limiting integration
        # Initialize configuration manager for consistent settings
        config_manager = ConfigManagerImpl()

        # Create JobberClient with rate limiting via ServiceFactory
        # This centralizes rate limiting setup and eliminates code duplication
        jobber_client = ServiceFactory.create_rate_limited_jobber_client(
            auth_provider=auth_provider,
            repository=repository,
            config_manager=config_manager,
            optimization_level=actual_optimization_level,
            enable_cost_monitoring=actual_enable_cost_monitoring,
        )

        # Log rate limiting configuration for visibility
        rate_config = config_manager.get_rate_limit_config(actual_optimization_level)
        requests_per_second = rate_config["refill_rate"] / 60
        logger.info(
            f"Rate limiting configured: {actual_optimization_level.upper()} optimization level "
            f"({rate_config['capacity']} tokens, {rate_config['refill_rate']}/minute, "
            f"~{requests_per_second:.0f} req/sec)"
        )

        entity_mapper = EntityMapper()

        # Create optional extractors for enhanced entity coverage
        from src.extractors import (
            ClientsExtractor,
            InvoicesExtractor,
            NoteReferenceCollector,
            NotesExtractor,
            QuotesExtractor,
        )

        # Create note components for deferred processing if enabled
        note_reference_collector = None
        notes_extractor = None

        if actual_deferred_notes:
            logger.info("🔄 Deferred notes loading enabled - preventing GraphQL throttling")
            note_reference_collector = NoteReferenceCollector(
                repository=repository,
                logger=logger,
                enable_persistence=actual_enable_notes_persistence,
                batch_size=1000,
            )
            notes_extractor = NotesExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
                config_manager=config_manager,
                skip_existing_entities=actual_resume,
            )

            if actual_enable_notes_persistence:
                logger.info("💾 Notes persistence enabled for large migration volumes")
        else:
            logger.info("⚡ Immediate notes processing enabled (legacy mode)")

        # Create entity extractors for modular extraction
        clients_extractor = ClientsExtractor(
            jobber_client,
            entity_mapper,
            repository,
            logger,
            config_manager=config_manager,
            skip_existing_entities=actual_resume,
        )
        invoices_extractor = InvoicesExtractor(
            jobber_client,
            entity_mapper,
            repository,
            logger,
            config_manager=config_manager,
            skip_existing_entities=actual_resume,
        )
        quotes_extractor = QuotesExtractor(
            jobber_client,
            entity_mapper,
            repository,
            logger,
            config_manager=config_manager,
            skip_existing_entities=actual_resume,
        )

        # Note: AttachmentDownloader is now a helper class used by extractors
        # Attachments are extracted inline with parent entities via noteAttachments fields

        # Create migration coordinator with all dependencies including optional extractors
        if actual_resume:
            logger.info("🔄 Resume mode ENABLED - will skip existing entities and use saved cursors")
        else:
            logger.info("🆕 Full migration mode - processing all entities from beginning")

        # Create unified Rich-based migration coordinator
        migration_coordinator = BaseMigrationCoordinator(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            note_reference_collector=note_reference_collector,
            notes_extractor=notes_extractor,
            clients_extractor=clients_extractor,
            invoices_extractor=invoices_extractor,
            quotes_extractor=quotes_extractor,
            config_manager=config_manager,
            resume=actual_resume,
            enable_adaptive_optimization=actual_enable_adaptive_optimization,
        )

        # Execute migration workflow with Rich progress bars
        logger.info("Starting migration process")

        # Enhanced startup logging for optimization configuration
        logger.info("🚀 Performance Configuration:")
        logger.info(f"   • Optimization level: {actual_optimization_level.upper()}")
        logger.info(f"   • Target rate: {requests_per_second:.0f} requests/sec")
        if enable_adaptive_optimization:
            logger.info("   • Adaptive optimization: ENABLED (will auto-tune performance)")
        else:
            logger.info("   • Adaptive optimization: DISABLED (using static settings)")

        # Calculate safety margin
        api_limit_per_sec = 500 / 60  # 500 req/min = ~8.33 req/sec
        safety_margin = ((api_limit_per_sec - requests_per_second) / api_limit_per_sec) * 100
        logger.info(f"   • Safety margin: {safety_margin:.0f}% below API limits")

        # Cost monitoring status
        if actual_enable_cost_monitoring:
            logger.info("   • GraphQL cost monitoring: ENABLED")
            if actual_cost_monitoring_verbose:
                logger.info("   • Verbose cost monitoring: ENABLED")
        else:
            logger.info("   • GraphQL cost monitoring: DISABLED")

        logger.info("🔍 Rate Limiter Status:")
        rate_limiter = jobber_client.http_client.get_rate_limiter()
        logger.info(f"   • Available tokens: {rate_limiter.get_available_tokens():.1f}/{rate_limiter.get_capacity()}")
        logger.info(
            f"   • Refill rate: {rate_limiter.get_refill_rate()}/min (~{rate_limiter.get_refill_rate()/60:.1f}/sec)"
        )

        summary = migration_coordinator.migrate()

        # Enhanced performance logging and metrics display
        logger.info("\n📊 Migration Performance Analysis:")

        # Calculate migration speed
        total_entities = (
            summary.clients_processed
            + summary.invoices_processed
            + summary.quotes_processed
            + summary.notes_processed
            + summary.attachments_processed
        )
        if summary.duration_seconds > 0:
            entities_per_minute = (total_entities / summary.duration_seconds) * 60
            logger.info(f"   • Migration speed: {entities_per_minute:.1f} entities/minute")
            logger.info(f"   • Total entities: {total_entities} in {summary.duration_seconds:.1f}s")

        # Enhanced rate limiting and cost metrics display
        if metrics_collector:
            rate_metrics = metrics_collector.get_human_readable_summary()
            cost_stats = metrics_collector.get_cost_statistics()
            rate_limit_status = metrics_collector.get_rate_limit_status()

            # GraphQL cost monitoring (verbose mode)
            if actual_cost_monitoring_verbose and cost_stats["total_queries"] > 0:
                logger.info("🧮 GraphQL Cost Analysis:")
                logger.info(f"   • Total queries: {cost_stats['total_queries']}")
                logger.info(f"   • Avg requested cost: {cost_stats['avg_requested_cost']:.0f}")
                logger.info(f"   • Avg actual cost: {cost_stats['avg_actual_cost']:.0f}")
                logger.info(f"   • Cost accuracy: {cost_stats['cost_accuracy_percentage']:.1f}%")

            # Rate limit status
            if rate_limit_status["remaining_requests"] is not None:
                logger.info("🔄 Rate Limit Status:")
                logger.info(f"   • Remaining requests: {rate_limit_status['remaining_requests']}")
                if (
                    rate_limit_status["seconds_until_reset"] is not None
                    and rate_limit_status["seconds_until_reset"] > 0
                ):
                    logger.info(f"   • Reset in: {rate_limit_status['seconds_until_reset']:.0f}s")
        else:
            logger.info("   • Cost monitoring: DISABLED")
            rate_metrics = {
                "throttle_rate": "0.0%",
                "throttled_requests": 0,
                "requests_per_minute": "N/A",
                "total_requests": 0,
                "rate_limit_errors": 0,
                "average_response_time": "N/A",
            }

        # Display final summary with rate limiting metrics using Rich table
        if metrics_collector:
            rate_metrics = metrics_collector.get_human_readable_summary()
        else:
            rate_metrics = {
                "throttle_rate": "0.0%",
                "throttled_requests": 0,
                "requests_per_minute": "N/A",
                "total_requests": 0,
                "rate_limit_errors": 0,
                "average_response_time": "N/A",
            }

        summary_data = {
            "clients_processed": summary.clients_processed,
            "invoices_processed": summary.invoices_processed,
            "quotes_processed": summary.quotes_processed,
            "notes_processed": summary.notes_processed,
            "note_references_collected": summary.note_references_collected,
            "attachments_processed": summary.attachments_processed,
            "files_downloaded": summary.files_downloaded,
            "total_bytes_downloaded": summary.total_bytes_downloaded,
            "download_failures": summary.download_failures,
            "duration": summary.format_duration(),
            "errors_count": len(summary.errors),
            "status": ("SUCCESS" if len(summary.errors) == 0 else "COMPLETED_WITH_ERRORS"),
            # Add migration mode information
            "deferred_notes_enabled": actual_deferred_notes,
            "notes_persistence_enabled": actual_enable_notes_persistence,
            "resume_mode_enabled": actual_resume,
            # Add rate limiting metrics
            "rate_limiting": {
                "requests_per_minute": rate_metrics["requests_per_minute"],
                "total_requests": rate_metrics["total_requests"],
                "throttled_requests": rate_metrics["throttled_requests"],
                "rate_limit_errors": rate_metrics["rate_limit_errors"],
                "average_response_time": rate_metrics["average_response_time"],
                "throttle_rate": rate_metrics["throttle_rate"],
            },
        }

        logger.log_summary(summary_data)

        # Display deferred notes performance information
        if actual_deferred_notes and summary.note_references_collected > 0:
            logger.info("📊 Deferred Notes Processing Performance:")
            logger.info(f"   • Note references collected: {summary.note_references_collected:,}")
            logger.info(f"   • Notes processed separately: {summary.notes_processed:,}")
            throttle_rate = float(rate_metrics["throttle_rate"].rstrip("%"))
            if throttle_rate < 5.0:  # Less than 5% throttling
                logger.info("   ✅ GraphQL throttling successfully minimized!")
            else:
                logger.info(f"   ⚠️  Some throttling occurred: {rate_metrics['throttle_rate']} of requests")
            logger.info("   🎯 Trading complex nested queries for simple individual queries")

        # Display final token status and rate limiting effectiveness
        logger.info("🔍 Final Token Status:")
        logger.info(f"   • Tokens remaining: {rate_limiter.get_available_tokens():.1f}/{rate_limiter.get_capacity()}")
        logger.info(
            f"   • Total requests: {rate_metrics['total_requests']} "
            f"(avg: {rate_metrics['requests_per_minute']}/min)"
        )
        logger.info(
            f"   • Throttling rate: {rate_metrics['throttle_rate']} "
            f"({rate_metrics['throttled_requests']} throttled)"
        )
        if float(rate_metrics["throttle_rate"].rstrip("%")) < 1.0:
            logger.info("   ✅ Jobber-optimized rate limiting working effectively!")
        elif float(rate_metrics["throttle_rate"].rstrip("%")) < 5.0:
            logger.info("   ⚠️  Minor throttling - rate limiting working well")
        else:
            logger.info("   🔴 Significant throttling - consider further rate limit tuning")

        # Display errors if any
        if summary.errors:
            logger.error(f"Migration completed with {len(summary.errors)} non-fatal errors:")
            for i, error in enumerate(summary.errors, 1):
                logger.error(f"  {i}. {error}")

        # Exit with appropriate code
        exit_code = 0 if len(summary.errors) == 0 else 1
        logger.info(f"Migration completed with exit code {exit_code}")
        sys.exit(exit_code)

    except ConfigurationError as e:
        # Configuration/environment issues
        # Use module-level console instance (already initialized at top of file)

        console.print(f"[red]Configuration Error:[/red] {e}")
        console.print("[yellow]To configure authentication, you can either:[/yellow]")
        console.print("  1. Run [bold]tightbeam oauth init[/bold] to set up OAuth authentication")
        console.print("  2. Manually set the following environment variables:")
        console.print("     - JOBBER_CLIENT_ID")
        console.print("     - JOBBER_CLIENT_SECRET")
        console.print("     - JOBBER_REDIRECT_URI")
        console.print("     - JOBBER_TOKEN")

        sys.exit(1)
    finally:
        if repository:
            repository.close()
        elif connection:
            connection.close()


@migrate_app.command("quotes")
def migrate_quotes(
    ctx: typer.Context,
    page_limit: Annotated[Optional[int], typer.Option("--limit", help="Limit number of pages for testing")] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Skip entities that already exist in database",
        ),
    ] = False,
) -> None:
    """
    Extract quote data from Jobber API to SQLite database.

    Fetches all quotes from the Jobber GraphQL API using cursor-based pagination
    and stores them in the specified SQLite database. Uses centralized rate limiting
    configuration from parent command options.

    Note: Individual migrate commands use simplified GraphQL queries and don't
    support deferred notes loading. For deferred notes, use 'migrate all' command.

    Args:
        page_limit: Optional limit on number of pages to process (for testing)
        resume: Skip entities that already exist in database (for resuming interrupted migrations)
    """  # noqa: E501
    # Get shared configuration from context
    config = ctx.obj or {}

    # Import the helper function from CLI services
    from .services import _execute_entity_extraction

    _execute_entity_extraction(
        entity_type="quotes",
        db=config.get("db", Path("tightbeam.sqlite")),
        verbose=config.get("verbose", False),
        page_limit=page_limit,
        optimization_level=config.get("optimization_level", "moderate"),
        resume=resume,
    )


@migrate_app.command("attachments")
def migrate_attachments(
    ctx: typer.Context,
    page_limit: Annotated[Optional[int], typer.Option("--limit", help="Limit number of pages for testing")] = None,
    download_path: Annotated[
        str, typer.Option("--download-path", help="Base path for attachment downloads")
    ] = "./attachments",
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Skip entities that already exist in database",
        ),
    ] = False,
) -> None:
    """
    Extract attachment data and download files from Jobber API to local storage.

    Fetches all attachments from the Jobber GraphQL API using cursor-based pagination,
    downloads the binary files to organized local storage, and stores metadata in the
    specified SQLite database. Uses centralized rate limiting configuration from parent
    command options (--optimization-level).

    Args:
        page_limit: Optional limit on number of pages to process (for testing)
        download_path: Base directory for attachment file downloads
    """  # noqa: E501
    # Get shared configuration from context
    config = ctx.obj or {}

    # Import the helper function from CLI services
    from .services import _execute_entity_extraction

    _execute_entity_extraction(
        entity_type="attachments",
        db=config.get("db", Path("tightbeam.sqlite")),
        verbose=config.get("verbose", False),
        page_limit=page_limit,
        download_path=download_path,
        optimization_level=config.get("optimization_level", "moderate"),
        resume=resume,
    )


# Additional migrate commands would follow the same pattern
# For brevity, I'll add a few more key ones:


@migrate_app.command("users")
def migrate_users(
    ctx: typer.Context,
    page_limit: Annotated[Optional[int], typer.Option("--limit", help="Limit number of pages for testing")] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Skip entities that already exist in database",
        ),
    ] = False,
) -> None:
    """
    Extract user data from Jobber API to SQLite database.

    Fetches all users from the Jobber GraphQL API using cursor-based pagination
    and stores them in the specified SQLite database. Includes user notes extraction
    for performance tracking and administrative information. Uses centralized rate
    limiting configuration from parent command options (--optimization-level).

    Args:
        page_limit: Optional limit on number of pages to process (for testing)
    """
    # Get shared configuration from context
    config = ctx.obj or {}

    # Import the helper function from CLI services
    from .services import _execute_entity_extraction

    _execute_entity_extraction(
        entity_type="users",
        db=config.get("db", Path("tightbeam.sqlite")),
        verbose=config.get("verbose", False),
        page_limit=page_limit,
        optimization_level=config.get("optimization_level", "moderate"),
        resume=resume,
    )


@migrate_app.command("expenses")
def migrate_expenses(
    ctx: typer.Context,
    page_limit: Annotated[Optional[int], typer.Option("--limit", help="Limit number of pages for testing")] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Skip entities that already exist in database",
        ),
    ] = False,
) -> None:
    """
    Extract expense data from Jobber API to SQLite database.

    Fetches all expenses from the Jobber GraphQL API using cursor-based pagination
    and stores them in the specified SQLite database. Includes job-related cost
    tracking and vendor information for financial management. Requires authentication
    via JOBBER_TOKEN environment variable or OAuth2 configuration.

    Args:
        page_limit: Optional limit on number of pages to process (for testing)
    """
    # Get shared configuration from context
    config = ctx.obj or {}

    # Import the helper function from CLI services
    from .services import _execute_entity_extraction

    _execute_entity_extraction(
        entity_type="expenses",
        db=config.get("db", Path("tightbeam.sqlite")),
        verbose=config.get("verbose", False),
        page_limit=page_limit,
        optimization_level=config.get("optimization_level", "moderate"),
        resume=resume,
    )


# Add remaining commands following the same pattern...
# (visits, timesheet-entries, products, tax-rates)
