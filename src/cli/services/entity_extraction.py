"""Shared entity extraction functionality for CLI commands."""

import sqlite3
import time
from pathlib import Path
from typing import Optional

from src.auth import AuthProvider, OAuth2Manager
from src.clients import HttpClient
from src.config import ConfigManagerImpl
from src.exceptions import ConfigurationError
from src.loggers import RichLogger
from src.mappers import EntityMapper
from src.repositories import Repository
from .factories import ServiceFactory


def _execute_entity_extraction(
    entity_type: str,
    db: Path,
    verbose: bool = False,
    page_limit: Optional[int] = None,
    download_path: str = "./attachments",
    optimization_level: str = "moderate",
    resume: bool = False,
) -> None:
    """
    Common entity extraction workflow for all supported entity types.

    Args:
        entity_type: Type of entity to extract ('quotes', 'notes', 'attachments',
                    'users', 'expenses', 'visits', 'timesheet-entries', 'products', 'tax-rates')
        db: Path to SQLite database file
        verbose: Enable verbose logging
        page_limit: Optional limit on number of pages to process
        download_path: Base directory for attachment downloads (attachments only)
        optimization_level: Rate limiting optimization level ('conservative', 'moderate', 'aggressive')
        resume: Skip entities that already exist in database
    """
    connection = None
    repository = None

    try:
        # Create database connection and logger
        logger = RichLogger(verbose=verbose, console=ServiceFactory.get_console())
        logger.info(f"Starting {entity_type} extraction to database: {db}")

        # Ensure parent directory exists
        db.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.Connection(str(db))

        # Initialize repository
        repository = Repository(connection)

        # Create OAuth2 components with error handling
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
                "Please ensure JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, and JOBBER_REDIRECT_URI "
                "are set and run 'tightbeam oauth init' to authorize."
            ) from None

        # Initialize configuration manager for consistent settings
        config_manager = ConfigManagerImpl()

        # Create JobberClient with rate limiting via ServiceFactory
        # This centralizes rate limiting setup and eliminates code duplication
        jobber_client = ServiceFactory.create_rate_limited_jobber_client(
            auth_provider=auth_provider,
            repository=repository,
            config_manager=config_manager,
            optimization_level=optimization_level,
            enable_cost_monitoring=True,  # Always enable for entity extraction
        )

        # Log rate limiting configuration for visibility
        rate_config = config_manager.get_rate_limit_config(optimization_level)
        requests_per_second = rate_config["refill_rate"] / 60
        logger.info(
            f"Rate limiting configured: {optimization_level.upper()} optimization level "
            f"({rate_config['capacity']} tokens, {rate_config['refill_rate']}/minute, "
            f"~{requests_per_second:.0f} req/sec)"
        )

        # Create entity mapper
        entity_mapper = EntityMapper()

        # Import and create appropriate extractor based on entity type
        if entity_type == "quotes":
            from src.extractors import QuotesExtractor

            extractor = QuotesExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
                config_manager=config_manager,
                skip_existing_entities=resume,
            )

        elif entity_type == "attachments":
            from src.extractors import AttachmentDownloader

            extractor = AttachmentDownloader(
                jobber_client,
                entity_mapper,
                repository,
                logger,
                base_download_path=download_path,
                config_manager=config_manager,
                skip_existing_entities=resume,
            )

        elif entity_type == "users":
            from src.extractors import UsersExtractor

            extractor = UsersExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
                skip_existing_entities=resume,
            )

        elif entity_type == "expenses":
            from src.extractors import ExpensesExtractor

            extractor = ExpensesExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
                skip_existing_entities=resume,
            )

        elif entity_type == "visits":
            from src.extractors import VisitsExtractor

            extractor = VisitsExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
                skip_existing_entities=resume,
            )

        elif entity_type == "timesheet-entries":
            from src.extractors import TimesheetEntriesExtractor

            extractor = TimesheetEntriesExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
            )

        elif entity_type == "products":
            from src.extractors import ProductServicesExtractor

            extractor = ProductServicesExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
            )

        elif entity_type == "tax-rates":
            from src.extractors import TaxRatesExtractor

            extractor = TaxRatesExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
            )

        else:
            raise ValueError(f"Unsupported entity type: {entity_type}")

        # Validate dependencies
        logger.debug("Validating extractor dependencies")
        extractor.validate_dependencies()

        # Execute extraction
        logger.info(f"Starting {entity_type} extraction workflow")
        logger.info("🔍 Initial Token Status:")
        logger.info(f"   • Available tokens: {rate_limiter.get_available_tokens():.1f}/{rate_limiter.get_capacity()}")
        start_time = time.time()

        result = extractor.extract(page_limit=page_limit)

        extraction_time = time.time() - start_time

        # Get extraction summary and enhanced performance metrics
        extraction_summary = extractor.get_extraction_summary()

        # Enhanced performance logging
        logger.info(f"\n📊 {entity_type.title()} Extraction Analysis:")
        if extraction_time > 0:
            entities_per_minute = (result["entities_processed"] / extraction_time) * 60
            logger.info(f"   • Extraction speed: {entities_per_minute:.1f} entities/minute")
            logger.info(f"   • Total entities: {result['entities_processed']} in {extraction_time:.1f}s")

        # Create default rate metrics if metrics_collector is None (moderate default)
        rate_metrics = {
            "throttle_rate": "0.0%",
            "throttled_requests": 0,
            "requests_per_minute": "N/A",
            "total_requests": 0,
            "rate_limit_errors": 0,
            "average_response_time": 0.0,
        }

        # Build comprehensive summary
        summary_data = {
            "entity_type": entity_type,
            "entities_processed": result["entities_processed"],
            "pages_processed": result["pages_processed"],
            "extraction_time": extraction_time,
            "has_next_page": result["has_next_page"],
            "status": ("SUCCESS" if extraction_summary["error_count"] == 0 else "COMPLETED_WITH_ERRORS"),
            "errors_count": extraction_summary["error_count"],
            "rate_limiting": {
                "requests_per_minute": rate_metrics["requests_per_minute"],
                "total_requests": rate_metrics["total_requests"],
                "throttled_requests": rate_metrics["throttled_requests"],
                "rate_limit_errors": rate_metrics["rate_limit_errors"],
                "average_response_time": rate_metrics["average_response_time"],
                "throttle_rate": rate_metrics["throttle_rate"],
            },
        }

        # Add attachment-specific metrics
        if entity_type == "attachments":
            summary_data.update(
                {
                    "files_downloaded": result.get("files_downloaded", 0),
                    "total_bytes_downloaded": result.get("total_bytes_downloaded", 0),
                    "download_failures": result.get("download_failures", 0),
                    "download_path": download_path,
                }
            )

        # Display final token status and rate limiting effectiveness
        logger.info("🔍 Final Token Status:")
        logger.info(f"   • Tokens remaining: {rate_limiter.get_available_tokens():.1f}/{rate_limiter.get_capacity()}")
        logger.info(
            f"   • Throttling rate: {rate_metrics['throttle_rate']} ({rate_metrics['throttled_requests']} throttled)"
        )
        if float(rate_metrics["throttle_rate"].rstrip("%")) < 1.0:
            logger.info("   ✅ Jobber-optimized rate limiting working effectively!")
        elif float(rate_metrics["throttle_rate"].rstrip("%")) < 5.0:
            logger.info("   ⚠️  Minor throttling - rate limiting working well")
        else:
            logger.info("   🔴 Significant throttling - consider further rate limit tuning")

        # Display results
        logger.log_summary(summary_data)

        # Log entity-specific success messages
        if entity_type == "quotes":
            logger.info(f"✅ Quote extraction completed: {result['entities_processed']} quotes processed")
        elif entity_type == "notes":
            logger.info(f"✅ Note extraction completed: {result['entities_processed']} notes processed")
        elif entity_type == "attachments":
            files_downloaded = result.get("files_downloaded", 0)
            total_bytes = result.get("total_bytes_downloaded", 0)
            logger.info(
                f"✅ Attachment extraction completed: {result['entities_processed']} attachments processed, "
                f"{files_downloaded} files downloaded ({total_bytes} bytes)"
            )
        elif entity_type == "users":
            logger.info(f"✅ User extraction completed: {result['entities_processed']} users processed")
        elif entity_type == "expenses":
            logger.info(f"✅ Expense extraction completed: {result['entities_processed']} expenses processed")
        elif entity_type == "visits":
            logger.info(f"✅ Visit extraction completed: {result['entities_processed']} visits processed")
        elif entity_type == "timesheet-entries":
            logger.info(
                f"✅ Timesheet entry extraction completed: {result['entities_processed']} timesheet entries processed"
            )
        elif entity_type == "products":
            logger.info(
                f"✅ Product/service extraction completed: {result['entities_processed']} products/services processed"
            )
        elif entity_type == "tax-rates":
            logger.info(f"✅ Tax rate extraction completed: {result['entities_processed']} tax rates processed")

        # Handle continuation if more pages available
        if result["has_next_page"] and page_limit is None:
            logger.info(f"📄 More {entity_type} pages available. Run again to continue extraction.")
            logger.info(f"Next cursor: {result.get('end_cursor', 'N/A')}")

        # Exit with appropriate code
        exit_code = 0 if extraction_summary["error_count"] == 0 else 1

    except Exception as e:
        logger = RichLogger(verbose=verbose, console=ServiceFactory.get_console())
        logger.error(f"Error during {entity_type} extraction: {e}")
        exit_code = 1
    finally:
        if repository:
            repository.close()
        elif connection:
            connection.close()
