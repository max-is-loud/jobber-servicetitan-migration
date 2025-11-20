"""Map mode coordinator for orchestrating lightweight entity discovery."""

import uuid
from datetime import datetime
from typing import Any, List, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..extractors.map_mode import (
    ClientsMapExtractor,
    ExpensesMapExtractor,
    InvoicesMapExtractor,
    JobsMapExtractor,
    ProductsServicesMapExtractor,
    PropertiesMapExtractor,
    QuotesMapExtractor,
    RequestsMapExtractor,
    TaxRatesMapExtractor,
    TimesheetEntriesMapExtractor,
    UsersMapExtractor,
    VisitsMapExtractor,
)
from ..interfaces import Logger
from ..models import MapSnapshot
from ..performance import AdaptivePerformanceOptimizer
from ..repositories import Repository


class MapModeCoordinator:
    """
    Coordinator for map mode extraction orchestration.

    Handles the discovery pass of multi-pass migration strategy, creating
    lightweight entity inventory with relation counts and density analysis.
    Generates map report to estimate extraction effort before full data retrieval.
    """

    # Map entity type names to extractor classes
    _EXTRACTOR_MAP = {
        "clients": ClientsMapExtractor,
        "invoices": InvoicesMapExtractor,
        "quotes": QuotesMapExtractor,
        "jobs": JobsMapExtractor,
        "properties": PropertiesMapExtractor,
        "requests": RequestsMapExtractor,
        "users": UsersMapExtractor,
        "expenses": ExpensesMapExtractor,
        "visits": VisitsMapExtractor,
        "timesheetEntries": TimesheetEntriesMapExtractor,
        "productsAndServices": ProductsServicesMapExtractor,
        "taxRates": TaxRatesMapExtractor,
    }

    @classmethod
    def supported_entity_types(cls) -> List[str]:
        """Return supported entity types for map mode."""
        return sorted(cls._EXTRACTOR_MAP.keys())

    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        config_manager: Optional[ConfigManagerImpl] = None,
        enable_adaptive_optimization: bool = False,
    ) -> None:
        """Initialize MapModeCoordinator.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            config_manager: Optional configuration manager for pagination/delay settings
            enable_adaptive_optimization: Enable adaptive paging/delay tuning
        """
        self._jobber_client = jobber_client
        self._repository = repository
        self._logger = logger
        self._console = Console()
        self._config_manager = config_manager or ConfigManagerImpl()
        self._adaptive_optimizer: Optional[AdaptivePerformanceOptimizer] = None
        if enable_adaptive_optimization:
            self._adaptive_optimizer = AdaptivePerformanceOptimizer(
                config_manager=self._config_manager,
                logger=self._logger,
                target_throttle_rate=0.05,
                optimization_interval=10,
            )

    def run_map_pass(
        self,
        entity_types: List[str],
        label: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute map mode extraction pass for specified entity types.

        Creates a map snapshot, runs lightweight extraction for each entity type,
        and collects entity counts and relation density information.

        Args:
            entity_types: List of entity type names to extract (e.g., ["clients", "invoices"])
            label: Optional human-friendly label for this map snapshot

        Returns:
            Dictionary with map pass results:
            - snapshot_id: UUID of created map snapshot
            - label: Snapshot label
            - entity_results: Dict mapping entity type to extraction results
            - totals: Dict with aggregate statistics
            - duration: Total execution time in seconds

        Raises:
            ValueError: If invalid entity types are provided
        """
        self._logger.info(f"Starting map mode extraction for entity types: {entity_types}")
        if self._adaptive_optimizer:
            self._logger.info("🤖 Adaptive optimization enabled for map pass (auto-tuning page size/delays)")

        # Validate entity types
        invalid_types = [et for et in entity_types if et not in self._EXTRACTOR_MAP]
        if invalid_types:
            raise ValueError(f"Invalid entity types: {invalid_types}")

        # Create map snapshot
        snapshot = self._create_snapshot(entity_types, label)
        self._logger.success(f"Created map snapshot: {snapshot.id} (label: {snapshot.label})")

        start_time = datetime.utcnow()
        entity_results = {}
        total_entities = 0
        mapped_counts: dict[TaskID, int] = {}

        # Add a spacer line so subsequent progress output doesn't overlap prior logs
        self._console.print()

        # Run extraction with Rich progress display
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TextColumn("[cyan]{task.fields[mapped]} mapped"),
            TimeElapsedColumn(),
            console=self._console,
            transient=True,
        ) as progress:
            for entity_type in entity_types:
                # Create progress task
                task_id = progress.add_task(f"Mapping {entity_type}...", total=None, mapped=0)
                mapped_counts[task_id] = 0

                def _increment(count: int, tid: TaskID = task_id) -> None:
                    mapped_counts[tid] = mapped_counts.get(tid, 0) + count
                    progress.update(tid, mapped=mapped_counts[tid])

                # Run extractor
                extractor = self._create_extractor(entity_type, snapshot.id, progress_cb=_increment)
                # Add a blank line to keep log output from colliding with progress row
                self._console.line()
                result = extractor.extract()

                # Update progress line for completed task
                mapped_counts[task_id] = result["total_entities"]
                progress.update(
                    task_id,
                    total=result["total_entities"] or 1,
                    completed=result["total_entities"],
                    mapped=result["total_entities"],
                    description=f"Mapped {entity_type} (done)",
                    visible=True,
                )

                # Track results
                entity_results[entity_type] = result
                total_entities += result["total_entities"]

                self._logger.success(
                    f"Completed {entity_type}: {result['total_entities']} entities in {result['total_pages']} pages"
                )

        # Calculate duration
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        self._logger.success(
            f"Map pass completed: {total_entities} total entities across "
            f"{len(entity_types)} types in {duration:.1f}s"
        )

        if self._adaptive_optimizer:
            perf_summary = self._adaptive_optimizer.get_performance_summary()
            self._logger.info(
                "Adaptive optimization summary: "
                f"page_size={perf_summary['current_page_size']}, "
                f"page_delay={perf_summary['current_page_delay']}, "
                f"throttle_rate={perf_summary['throttle_rate']}, "
                f"throughput={perf_summary['current_throughput']}"
            )

        return {
            "snapshot_id": snapshot.id,
            "label": snapshot.label or "",
            "entity_results": entity_results,
            "totals": {"total_entities": total_entities, "entity_types_count": len(entity_types)},
            "duration": duration,
        }

    def _create_snapshot(self, entity_types: List[str], label: Optional[str]) -> MapSnapshot:
        """Create and save a new map snapshot.

        Args:
            entity_types: List of entity types included in this snapshot
            label: Optional human-friendly label

        Returns:
            Created MapSnapshot instance
        """
        import json

        snapshot_id = str(uuid.uuid4())
        current_time = datetime.utcnow().isoformat() + "Z"

        # Generate label if not provided
        if not label:
            label = f"map-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

        snapshot = MapSnapshot(
            id=snapshot_id,
            created_at=current_time,
            pass1_cutoff=current_time,
            label=label,
            entities_included=json.dumps(entity_types),
        )

        self._repository.save_map_snapshot(snapshot)
        return snapshot

    def _create_extractor(self, entity_type: str, snapshot_id: str, progress_cb=None):
        """Create map mode extractor for the specified entity type.

        Args:
            entity_type: Name of entity type (e.g., "clients")
            snapshot_id: ID of map snapshot

        Returns:
            Initialized map extractor instance
        """
        extractor_class = self._EXTRACTOR_MAP[entity_type]
        return extractor_class(
            jobber_client=self._jobber_client,
            repository=self._repository,
            logger=self._logger,
            map_snapshot_id=snapshot_id,
            adaptive_optimizer=self._adaptive_optimizer,
            progress_callback=progress_cb,
        )

    def identify_hotspots(
        self,
        snapshot_id: str,
        entity_type: str,
        top_n: int = 10,
    ) -> List[dict[str, Any]]:
        """
        Identify entities with highest relation counts (hotspots).

        Args:
            snapshot_id: Map snapshot ID to analyze
            entity_type: Entity type to analyze (e.g., "clients")
            top_n: Number of top entities to return

        Returns:
            List of dicts with entity_id and relation counts, sorted by total relations descending
        """
        import json

        # Get all inventory items for this entity type and snapshot
        inventory_items = self._repository.get_entity_inventory(snapshot_id, entity_type)

        # Calculate total relations for each entity
        hotspots = []
        for item in inventory_items:
            relations = json.loads(item.estimated_relations_json)
            total_relations = sum(relations.values())

            hotspots.append(
                {
                    "entity_id": item.entity_id,
                    "entity_type": entity_type,
                    "total_relations": total_relations,
                    "relations": relations,
                }
            )

        # Sort by total relations (descending) and return top N
        hotspots.sort(key=lambda x: x["total_relations"], reverse=True)
        return hotspots[:top_n]

    def get_density_stats(
        self,
        snapshot_id: str,
        entity_type: str,
    ) -> dict[str, Any]:
        """
        Calculate relation density statistics for an entity type.

        Args:
            snapshot_id: Map snapshot ID to analyze
            entity_type: Entity type to analyze

        Returns:
            Dict with density statistics:
            - total_entities: Number of entities
            - avg_relations: Average relations per entity
            - max_relations: Maximum relations for any entity
            - entities_with_relations: Count of entities with at least one relation
        """
        import json

        inventory_items = self._repository.get_entity_inventory(snapshot_id, entity_type)

        if not inventory_items:
            return {
                "total_entities": 0,
                "avg_relations": 0.0,
                "max_relations": 0,
                "entities_with_relations": 0,
            }

        relation_counts = []
        entities_with_relations = 0

        for item in inventory_items:
            relations = json.loads(item.estimated_relations_json)
            total = sum(relations.values())
            relation_counts.append(total)
            if total > 0:
                entities_with_relations += 1

        return {
            "total_entities": len(inventory_items),
            "avg_relations": sum(relation_counts) / len(relation_counts) if relation_counts else 0.0,
            "max_relations": max(relation_counts) if relation_counts else 0,
            "entities_with_relations": entities_with_relations,
        }
