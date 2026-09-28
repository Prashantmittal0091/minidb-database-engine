"""
Disk Manager for MiniDB.

Handles file system operations, reading/writing fixed 4096-byte pages
to/from table `.db` binary files.
"""

import os
from typing import Optional
from minidb.storage.page import PAGE_SIZE, SlottedPage, PAGE_TYPE_DATA


class DiskManager:
    """Manages disk file I/O for fixed-size database pages."""

    def __init__(self, db_filepath: str):
        self.db_filepath = db_filepath
        # Ensure parent directories exist
        dirname = os.path.dirname(db_filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        if not os.path.exists(db_filepath):
            # Create empty file
            with open(db_filepath, "wb") as f:
                pass
            self.num_pages = 0
        else:
            file_size = os.path.getsize(db_filepath)
            self.num_pages = file_size // PAGE_SIZE

    def allocate_page(self, page_type: int = PAGE_TYPE_DATA) -> SlottedPage:
        """Allocate a new page at the end of the file."""
        page_id = self.num_pages
        self.num_pages += 1
        page = SlottedPage(page_id=page_id, page_type=page_type)
        self.write_page(page)
        return page

    def read_page(self, page_id: int) -> Optional[SlottedPage]:
        """Read 4096-byte page from disk at offset page_id * PAGE_SIZE."""
        if page_id < 0 or page_id >= self.num_pages:
            return None
        with open(self.db_filepath, "rb") as f:
            f.seek(page_id * PAGE_SIZE)
            data = f.read(PAGE_SIZE)
            if len(data) < PAGE_SIZE:
                return None
            return SlottedPage(page_id=page_id, data=data)

    def write_page(self, page: SlottedPage):
        """Write page bytes to disk file at offset page.page_id * PAGE_SIZE."""
        page_bytes = page.serialize()
        with open(self.db_filepath, "r+b" if os.path.exists(self.db_filepath) and os.path.getsize(self.db_filepath) > 0 else "wb") as f:
            f.seek(page.page_id * PAGE_SIZE)
            f.write(page_bytes)
            f.flush()

    def close(self):
        """Close disk manager handle."""
        pass
