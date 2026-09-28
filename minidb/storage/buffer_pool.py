"""
Buffer Pool Manager for MiniDB.

Maintains fixed-size frame pool in RAM, LRU eviction policy,
page pinning/unpinning, and dirty page writebacks to DiskManager.
"""

from collections import OrderedDict
from typing import Dict, Optional, Set
from minidb.storage.disk_manager import DiskManager
from minidb.storage.page import SlottedPage


class BufferPoolManager:
    """Manages in-memory page frame cache with LRU eviction."""

    def __init__(self, disk_manager: DiskManager, capacity: int = 16):
        self.disk_manager = disk_manager
        self.capacity = capacity
        
        # Frame table: page_id -> SlottedPage
        self.page_table: Dict[int, SlottedPage] = {}
        # Pin count tracking: page_id -> int
        self.pin_counts: Dict[int, int] = {}
        # Dirty flag tracking: page_id -> bool
        self.dirty_flags: Dict[int, bool] = {}
        # LRU ordering: page_id -> None (Keys ordered by access time)
        self.lru_queue: OrderedDict = OrderedDict()
        
        # Performance Statistics
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def fetch_page(self, page_id: int) -> Optional[SlottedPage]:
        """
        Fetch page by ID. If in buffer pool, mark as hit & pin.
        If missing, evict an unpinned frame if full, load from disk, and pin.
        """
        if page_id in self.page_table:
            self.hits += 1
            self.pin_counts[page_id] += 1
            # Move to end of LRU (most recently used)
            self.lru_queue.move_to_end(page_id)
            return self.page_table[page_id]

        # Cache Miss
        self.misses += 1

        # Check capacity limit
        if len(self.page_table) >= self.capacity:
            evicted_id = self._evict()
            if evicted_id is None:
                # All pages pinned! Fall back to temporary direct disk fetch
                page = self.disk_manager.read_page(page_id)
                return page

        # Read from disk
        page = self.disk_manager.read_page(page_id)
        if page is None:
            return None

        self.page_table[page_id] = page
        self.pin_counts[page_id] = 1
        self.dirty_flags[page_id] = False
        self.lru_queue[page_id] = None
        return page

    def new_page(self, page_type: int) -> SlottedPage:
        """Allocate a new page on disk and bring into buffer pool."""
        page = self.disk_manager.allocate_page(page_type)
        page_id = page.page_id
        
        if len(self.page_table) >= self.capacity:
            self._evict()

        self.page_table[page_id] = page
        self.pin_counts[page_id] = 1
        self.dirty_flags[page_id] = True
        self.lru_queue[page_id] = None
        return page

    def unpin_page(self, page_id: int, is_dirty: bool = False):
        """Unpin a page and record if it was modified."""
        if page_id not in self.page_table:
            return

        if is_dirty:
            self.dirty_flags[page_id] = True

        if self.pin_counts[page_id] > 0:
            self.pin_counts[page_id] -= 1

    def _evict(self) -> Optional[int]:
        """Evict least recently used unpinned page from pool."""
        evict_candidate = None
        for pid in list(self.lru_queue.keys()):
            if self.pin_counts.get(pid, 0) == 0:
                evict_candidate = pid
                break

        if evict_candidate is None:
            return None

        # Write to disk if dirty
        if self.dirty_flags.get(evict_candidate, False):
            self.disk_manager.write_page(self.page_table[evict_candidate])

        # Remove from pool
        del self.page_table[evict_candidate]
        del self.pin_counts[evict_candidate]
        del self.dirty_flags[evict_candidate]
        del self.lru_queue[evict_candidate]
        self.evictions += 1
        return evict_candidate

    def flush_all(self):
        """Flush all dirty pages to disk."""
        for page_id, is_dirty in list(self.dirty_flags.items()):
            if is_dirty and page_id in self.page_table:
                self.disk_manager.write_page(self.page_table[page_id])
                self.dirty_flags[page_id] = False

    def get_inspector_info(self) -> dict:
        """Return buffer pool frame breakdown for live visualizer GUI."""
        frames = []
        for pid, page in self.page_table.items():
            frames.append({
                "page_id": pid,
                "page_type": "DATA" if page.page_type == 1 else "INDEX",
                "pin_count": self.pin_counts.get(pid, 0),
                "is_dirty": self.dirty_flags.get(pid, False),
                "num_slots": page.num_slots,
                "free_bytes": page.get_free_space()
            })
        
        total_requests = self.hits + self.misses
        hit_ratio = round((self.hits / total_requests * 100), 2) if total_requests > 0 else 100.0

        return {
            "capacity": self.capacity,
            "used_frames": len(self.page_table),
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_ratio_percent": hit_ratio,
            "frames": frames,
            "lru_order": list(self.lru_queue.keys())
        }
