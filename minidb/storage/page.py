"""
Slotted Page Implementation for MiniDB.

Fixed-size page layout (default 4096 bytes):
+-----------------------------------------------------------------------+
| Page Header:                                                          |
|   page_id (4B), page_type (1B), num_slots (2B), free_space_ptr (2B)   |
+-----------------------------------------------------------------------+
| Slot Array:                                                           |
|   Slot 0 (offset 2B, len 2B) | Slot 1 (offset 2B, len 2B) | ...      |
+-------------------------------+---------------------------------------+
|                       <--- Free Space --->                            |
+-----------------------------------------------------------------------+
| Tuple Data N-1 ...                        Tuple Data 1 | Tuple Data 0 |
+-----------------------------------------------------------------------+
"""

import struct
from typing import Optional, List, Tuple

PAGE_SIZE = 4096
HEADER_FORMAT = "!IBHH"  # page_id (I), page_type (B), num_slots (H), free_space_ptr (H)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 4 + 1 + 2 + 2 = 9 bytes
SLOT_FORMAT = "!HH"  # offset (H), length (H)
SLOT_SIZE = struct.calcsize(SLOT_FORMAT)  # 4 bytes

# Page types
PAGE_TYPE_DATA = 1
PAGE_TYPE_INDEX_LEAF = 2
PAGE_TYPE_INDEX_INTERNAL = 3
PAGE_TYPE_HEADER = 4


class SlottedPage:
    """Manages a single 4096-byte slotted page buffer."""

    def __init__(self, page_id: int = 0, page_type: int = PAGE_TYPE_DATA, data: Optional[bytes] = None):
        self.page_id = page_id
        self.page_type = page_type
        
        if data is not None and len(data) == PAGE_SIZE:
            self.data = bytearray(data)
            self._unpack_header()
        else:
            self.data = bytearray(PAGE_SIZE)
            self.num_slots = 0
            self.free_space_ptr = PAGE_SIZE
            self._pack_header()

    def _unpack_header(self):
        page_id, page_type, num_slots, free_space_ptr = struct.unpack_from(HEADER_FORMAT, self.data, 0)
        self.page_id = page_id
        self.page_type = page_type
        self.num_slots = num_slots
        self.free_space_ptr = free_space_ptr

    def _pack_header(self):
        struct.pack_into(HEADER_FORMAT, self.data, 0, self.page_id, self.page_type, self.num_slots, self.free_space_ptr)

    def get_free_space(self) -> int:
        """Calculate bytes available for new tuples + slot entry."""
        used_by_slots = HEADER_SIZE + (self.num_slots * SLOT_SIZE)
        return self.free_space_ptr - used_by_slots

    def insert_tuple(self, tuple_bytes: bytes) -> Optional[int]:
        """
        Insert tuple byte array into the page.
        Returns slot_id on success, or None if page full.
        """
        needed = len(tuple_bytes) + SLOT_SIZE
        if self.get_free_space() < needed:
            return None

        # Calculate new tuple offset (grows downward from free_space_ptr)
        tuple_offset = self.free_space_ptr - len(tuple_bytes)
        
        # Check if there is a reused tombstoned slot
        slot_id = None
        for i in range(self.num_slots):
            slot_offset, slot_len = self.get_slot(i)
            if slot_len == 0:  # Deleted slot
                slot_id = i
                break

        if slot_id is None:
            slot_id = self.num_slots
            self.num_slots += 1

        # Write tuple content
        self.data[tuple_offset : tuple_offset + len(tuple_bytes)] = tuple_bytes
        self.free_space_ptr = tuple_offset

        # Write slot entry
        slot_entry_offset = HEADER_SIZE + (slot_id * SLOT_SIZE)
        struct.pack_into(SLOT_FORMAT, self.data, slot_entry_offset, tuple_offset, len(tuple_bytes))

        # Update page header
        self._pack_header()
        return slot_id

    def get_slot(self, slot_id: int) -> Tuple[int, int]:
        """Returns (offset, length) for slot_id."""
        if slot_id < 0 or slot_id >= self.num_slots:
            return 0, 0
        slot_entry_offset = HEADER_SIZE + (slot_id * SLOT_SIZE)
        return struct.unpack_from(SLOT_FORMAT, self.data, slot_entry_offset)

    def read_tuple(self, slot_id: int) -> Optional[bytes]:
        """Reads tuple bytes at slot_id."""
        offset, length = self.get_slot(slot_id)
        if length == 0:
            return None  # Tombstoned/deleted
        return bytes(self.data[offset : offset + length])

    def delete_tuple(self, slot_id: int) -> bool:
        """Mark a tuple slot as deleted (length 0)."""
        if slot_id < 0 or slot_id >= self.num_slots:
            return False
        offset, length = self.get_slot(slot_id)
        if length == 0:
            return False
        
        # Tombstone slot
        slot_entry_offset = HEADER_SIZE + (slot_id * SLOT_SIZE)
        struct.pack_into(SLOT_FORMAT, self.data, slot_entry_offset, 0, 0)
        self._pack_header()
        return True

    def update_tuple(self, slot_id: int, new_bytes: bytes) -> bool:
        """Update an existing slot with new data if space permits."""
        offset, length = self.get_slot(slot_id)
        if length == 0:
            return False

        if len(new_bytes) <= length:
            # Overwrite in-place
            self.data[offset : offset + len(new_bytes)] = new_bytes
            slot_entry_offset = HEADER_SIZE + (slot_id * SLOT_SIZE)
            struct.pack_into(SLOT_FORMAT, self.data, slot_entry_offset, offset, len(new_bytes))
            self._pack_header()
            return True
        else:
            # Mark old deleted, re-insert
            self.delete_tuple(slot_id)
            new_slot = self.insert_tuple(new_bytes)
            return new_slot is not None

    def serialize(self) -> bytes:
        """Return full 4096-byte page payload."""
        self._pack_header()
        return bytes(self.data)

    def get_inspector_info(self) -> dict:
        """Return visual data breakdown for page UI rendering."""
        slots_info = []
        for i in range(self.num_slots):
            off, length = self.get_slot(i)
            slots_info.append({
                "slot_id": i,
                "offset": off,
                "length": length,
                "is_deleted": length == 0
            })
        return {
            "page_id": self.page_id,
            "page_type": "DATA" if self.page_type == PAGE_TYPE_DATA else "INDEX",
            "num_slots": self.num_slots,
            "free_space_ptr": self.free_space_ptr,
            "free_space_bytes": self.get_free_space(),
            "slots": slots_info
        }
