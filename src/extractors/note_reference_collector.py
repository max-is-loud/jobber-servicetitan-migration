"""Note reference collector for deferred note processing.

This module provides the NoteReferenceCollector class for collecting note ID
references during parent entity processing, enabling deferred note loading
to resolve GraphQL throttling issues in TightBeam v2 Jobber API operations.
"""

import threading
import time
from typing import List

from ..interfaces import Logger
from ..repositories import Repository


class NoteReferenceCollector:
    """Thread-safe collector for note ID references during entity processing.

    Collects note ID references along with their parent entity relationships
    during client, invoice, quote, job, and request processing. This enables
    deferred note processing to avoid the nested GraphQL query complexity
    that causes API throttling.

    The collector maintains parent-child relationships needed for proper note
    processing while keeping memory usage minimal by storing only IDs and
    relationships, not full note content.

    Thread-safe design allows concurrent collection from multiple processing
    threads while maintaining data integrity.
    """

    def __init__(
        self,
        repository: Repository,
        logger: Logger,
        enable_persistence: bool = False,
        batch_size: int = 1000,
    ) -> None:
        """Initialize the note reference collector.

        Args:
            repository: Repository instance for potential future persistence
            logger: Logger instance for operation tracking
            enable_persistence: Whether to use database storage for large collections
            batch_size: Number of references to collect before flushing to storage
        """
        self._repository = repository
        self._logger = logger
        self._enable_persistence = enable_persistence
        self._batch_size = batch_size
        self._note_references: List[dict[str, str]] = []
        self._lock = threading.Lock()

    def collect_note_id(self, note_id: str, entity_type: str, entity_id: str) -> None:
        """Collect a note ID reference with its parent entity relationship.

        Thread-safe method to store note references for later processing.
        Each reference includes the note ID and its parent entity context.
        Automatically flushes to persistent storage when batch size is reached.

        Args:
            note_id: The unique identifier of the note
            entity_type: Type of parent entity (client, invoice, quote, job, request)
            entity_id: The unique identifier of the parent entity
        """
        with self._lock:
            self._note_references.append(
                {
                    "note_id": note_id,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                }
            )

            # Auto-flush to persistent storage if batch size reached
            if self._enable_persistence and len(self._note_references) >= self._batch_size:
                self._flush_to_storage()

    def collect_note_ids_from_edges(self, note_edges: List[dict], entity_type: str, entity_id: str) -> None:
        """Collect multiple note IDs from GraphQL edges structure.

        Convenience method for processing the common GraphQL edges/node pattern
        returned by the simplified note queries.

        Args:
            note_edges: List of GraphQL edge objects containing node.id
            entity_type: Type of parent entity (client, invoice, quote, job, request)
            entity_id: The unique identifier of the parent entity
        """
        if not note_edges:
            return

        for edge in note_edges:
            node = edge.get("node", {})
            note_id = node.get("id")
            if note_id:
                self.collect_note_id(note_id, entity_type, entity_id)

    def _flush_to_storage(self) -> None:
        """Flush current note references to persistent storage.

        Internal method to save collected references to the repository
        and clear the in-memory collection. Should be called with lock held.
        """
        if not self._note_references:
            return

        try:
            self._repository.save_note_references(self._note_references)
            self._note_references.clear()
            # No logging on success - only log errors to keep logs clean
        except Exception as e:
            self._logger.error(f"Failed to flush note references to storage: {e}")
            # Don't raise - keep references in memory as fallback

    def flush_to_storage(self) -> None:
        """Public method to manually flush note references to persistent storage.

        Thread-safe method to force flush of current in-memory references
        to persistent storage. Useful for ensuring data is saved before
        critical operations.
        """
        with self._lock:
            self._flush_to_storage()

    def get_references(self) -> List[dict[str, str]]:
        """Get a copy of all collected note references.

        Thread-safe method to retrieve all note references for processing
        by the notes extractor. Includes both in-memory and persistent storage
        when persistence is enabled.

        Returns:
            List of dictionaries containing note_id, entity_type, entity_id
        """
        with self._lock:
            references = self._note_references.copy()
            # No logging - routine operation

            # If persistence is enabled, also get references from storage
            if self._enable_persistence:
                try:
                    storage_count = self._repository.get_note_references_count()
                    # Get all references from storage using efficient cursor-based batches
                    last_id = 0
                    batch_size = 1000
                    total_from_storage = 0
                    batch_count = 0
                    estimated_batches = (storage_count // batch_size) + 1

                    while True:
                        batch_count += 1
                        batch_start = time.time()
                        storage_refs, last_id = self._repository.get_note_references_cursor_based(
                            limit=batch_size, last_id=last_id
                        )
                        batch_elapsed = time.time() - batch_start
                        if not storage_refs:
                            break
                        references.extend(storage_refs)
                        total_from_storage += len(storage_refs)
                        # Only log slow batches (potential problems)
                        if batch_elapsed > 0.5:
                            self._logger.warning(
                                f"Slow batch loading: batch {batch_count} took {batch_elapsed:.2f}s for {len(storage_refs)} references"
                            )
                except Exception as e:
                    self._logger.error(f"Failed to retrieve references from storage: {e}")

            # Return silently on success - only errors need logging
            return references

    def get_reference_count(self) -> int:
        """Get the total number of collected note references.

        Includes both in-memory and persistent storage when persistence is enabled.

        Returns:
            Integer count of collected note references
        """
        with self._lock:
            count = len(self._note_references)

            # Add count from persistent storage if enabled
            if self._enable_persistence:
                try:
                    count += self._repository.get_note_references_count()
                except Exception as e:
                    self._logger.error(f"Failed to get storage reference count: {e}")

            return count

    def get_references_by_entity_type(self, entity_type: str) -> List[dict[str, str]]:
        """Get note references filtered by entity type.

        Args:
            entity_type: Entity type to filter by (client, invoice, quote, etc.)

        Returns:
            List of note references for the specified entity type
        """
        with self._lock:
            return [ref for ref in self._note_references if ref["entity_type"] == entity_type]

    def clear_references(self) -> None:
        """Clear all collected note references.

        Thread-safe method to reset the collector, typically called after
        successful note processing or for cleanup between migration phases.
        Clears both in-memory and persistent storage when persistence is enabled.
        """
        with self._lock:
            references_count = len(self._note_references)
            self._note_references.clear()

            # Clear persistent storage if enabled
            if self._enable_persistence:
                try:
                    storage_count = self._repository.get_note_references_count()
                    self._repository.clear_note_references()
                    references_count += storage_count
                except Exception as e:
                    self._logger.error(f"Failed to clear storage references: {e}")

            # No logging on success - only errors are worth capturing

    def get_unique_note_ids(self) -> List[str]:
        """Get list of unique note IDs from all collected references.

        Returns:
            List of unique note IDs for batch processing
        """
        with self._lock:
            return list({ref["note_id"] for ref in self._note_references})

    def get_summary(self) -> dict[str, int]:
        """Get summary statistics of collected references.

        Returns:
            Dictionary with counts by entity type and total
        """
        with self._lock:
            summary = {"total": len(self._note_references)}

            # Count by entity type
            for ref in self._note_references:
                entity_type = ref["entity_type"]
                key = f"{entity_type}_notes"
                summary[key] = summary.get(key, 0) + 1

            return summary

    def __repr__(self) -> str:
        """Return string representation of the collector."""
        count = self.get_reference_count()
        return f"NoteReferenceCollector(references={count})"
