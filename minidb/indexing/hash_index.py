"""
Extendible Hash Index Implementation for MiniDB.

Provides O(1) exact match lookups, bucket directory management,
local/global depth tracking, bucket splitting, and visual breakdown.
"""

from typing import List, Tuple, Any, Dict
import hashlib

RecordID = Tuple[int, int]


class HashBucket:
    """A bucket holding a fixed number of key-RID pairs."""

    def __init__(self, local_depth: int = 1, capacity: int = 4):
        self.local_depth: int = local_depth
        self.capacity: int = capacity
        self.entries: List[Tuple[Any, RecordID]] = []

    def is_full(self) -> bool:
        return len(self.entries) >= self.capacity


class HashIndex:
    """Extendible Hash Index with dynamic directory expansion."""

    def __init__(self, bucket_capacity: int = 4):
        self.global_depth: int = 1
        self.capacity: int = bucket_capacity
        # Directory: bit string string representation -> HashBucket
        b1 = HashBucket(local_depth=1, capacity=bucket_capacity)
        b2 = HashBucket(local_depth=1, capacity=bucket_capacity)
        self.directory: List[HashBucket] = [b1, b2]

    def _hash_key(self, key: Any) -> int:
        """Compute integer hash for any Python value."""
        s = str(key).encode('utf-8')
        return int(hashlib.md5(s).hexdigest()[:8], 16)

    def _get_index(self, key: Any) -> int:
        h = self._hash_key(key)
        return h & ((1 << self.global_depth) - 1)

    def search(self, key: Any) -> List[RecordID]:
        """Exact match lookup in O(1) time."""
        idx = self._get_index(key)
        bucket = self.directory[idx]
        return [rid for k, rid in bucket.entries if k == key]

    def insert(self, key: Any, rid: RecordID):
        """Insert key-RID pair into Extendible Hash Index."""
        idx = self._get_index(key)
        bucket = self.directory[idx]

        if not bucket.is_full():
            bucket.entries.append((key, rid))
            return

        # Bucket is full -> Split bucket
        if bucket.local_depth == self.global_depth:
            self._double_directory()

        self._split_bucket(idx)
        # Re-try insert after split
        self.insert(key, rid)

    def _double_directory(self):
        """Double size of the directory array."""
        self.directory += self.directory
        self.global_depth += 1

    def _split_bucket(self, bucket_idx: int):
        old_bucket = self.directory[bucket_idx]
        old_local_depth = old_bucket.local_depth
        new_local_depth = old_local_depth + 1
        old_bucket.local_depth = new_local_depth

        new_bucket = HashBucket(local_depth=new_local_depth, capacity=self.capacity)

        # Update directory pointers
        mask = 1 << old_local_depth
        for i in range(len(self.directory)):
            if self.directory[i] == old_bucket:
                if (i & mask) != 0:
                    self.directory[i] = new_bucket

        # Re-hash existing entries
        old_entries = old_bucket.entries
        old_bucket.entries = []

        for k, rid in old_entries:
            idx = self._get_index(k)
            self.directory[idx].entries.append((k, rid))

    def get_visual_hash(self) -> dict:
        """Export hash index structure for UI inspector."""
        unique_buckets = {}
        for idx, bucket in enumerate(self.directory):
            bid = id(bucket)
            if bid not in unique_buckets:
                unique_buckets[bid] = {
                    "bucket_id": f"Bucket_{bid % 10000}",
                    "local_depth": bucket.local_depth,
                    "count": len(bucket.entries),
                    "capacity": bucket.capacity,
                    "entries": [{"key": str(k), "rid": rid} for k, rid in bucket.entries]
                }
        
        dir_pointers = []
        for i, b in enumerate(self.directory):
            binary_repr = format(i, f'0{self.global_depth}b')
            dir_pointers.append({
                "index": i,
                "binary": binary_repr,
                "target_bucket": f"Bucket_{id(b) % 10000}"
            })

        return {
            "global_depth": self.global_depth,
            "directory_size": len(self.directory),
            "directory": dir_pointers,
            "buckets": list(unique_buckets.values())
        }
