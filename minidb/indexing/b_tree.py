"""
B+ Tree Index Implementation for MiniDB.

Supports exact lookups (O(log N)), range queries via leaf node pointers,
node splitting, and JSON visual export for visual debugging.
"""

from typing import List, Tuple, Any, Optional

RecordID = Tuple[int, int]  # (page_id, slot_id)


class BTreeNode:
    """Represents an internal or leaf node in the B+ Tree."""

    def __init__(self, is_leaf: bool = False):
        self.is_leaf: bool = is_leaf
        self.keys: List[Any] = []
        # For internal nodes: list of child BTreeNode references
        self.children: List['BTreeNode'] = []
        # For leaf nodes: list of List[RecordID] corresponding to each key
        self.rids: List[List[RecordID]] = []
        # Doubly-linked leaf pointers for fast range scans
        self.next_leaf: Optional['BTreeNode'] = None
        self.prev_leaf: Optional['BTreeNode'] = None
        self.node_id: int = id(self) % 100000  # Unique label for visualization


class BTreeIndex:
    """Disk/Memory aligned B+ Tree index with configurable max keys (order)."""

    def __init__(self, max_keys: int = 4):
        self.max_keys: int = max_keys
        self.min_keys: int = max_keys // 2
        self.root: BTreeNode = BTreeNode(is_leaf=True)

    def search(self, key: Any) -> List[RecordID]:
        """Search for exact key, return list of RecordIDs."""
        leaf = self._find_leaf(self.root, key)
        for idx, k in enumerate(leaf.keys):
            if k == key:
                return list(leaf.rids[idx])
        return []

    def range_search(self, low_key: Optional[Any], high_key: Optional[Any]) -> List[Tuple[Any, RecordID]]:
        """
        Perform range scan [low_key, high_key].
        Returns list of (key, RecordID).
        """
        results = []
        # Find starting leaf
        leaf = self._find_leftmost_leaf(self.root) if low_key is None else self._find_leaf(self.root, low_key)

        curr = leaf
        done = False
        while curr and not done:
            for idx, k in enumerate(curr.keys):
                if low_key is not None and k < low_key:
                    continue
                if high_key is not None and k > high_key:
                    done = True
                    break
                for rid in curr.rids[idx]:
                    results.append((k, rid))
            curr = curr.next_leaf
        return results

    def insert(self, key: Any, rid: RecordID):
        """Insert a key and RecordID into the B+ Tree."""
        leaf = self._find_leaf(self.root, key)

        # Check if key already exists in leaf
        for idx, k in enumerate(leaf.keys):
            if k == key:
                if rid not in leaf.rids[idx]:
                    leaf.rids[idx].append(rid)
                return

        # Insert key in sorted order
        insert_idx = 0
        while insert_idx < len(leaf.keys) and leaf.keys[insert_idx] < key:
            insert_idx += 1

        leaf.keys.insert(insert_idx, key)
        leaf.rids.insert(insert_idx, [rid])

        # Check if leaf split needed
        if len(leaf.keys) > self.max_keys:
            self._split_leaf(leaf)

    def _split_leaf(self, leaf: BTreeNode):
        mid = len(leaf.keys) // 2
        new_leaf = BTreeNode(is_leaf=True)

        new_leaf.keys = leaf.keys[mid:]
        new_leaf.rids = leaf.rids[mid:]

        leaf.keys = leaf.keys[:mid]
        leaf.rids = leaf.rids[:mid]

        # Link leaves
        new_leaf.next_leaf = leaf.next_leaf
        if leaf.next_leaf:
            leaf.next_leaf.prev_leaf = new_leaf
        leaf.next_leaf = new_leaf
        new_leaf.prev_leaf = leaf

        # Promote mid key to parent
        promoted_key = new_leaf.keys[0]
        self._insert_into_parent(leaf, promoted_key, new_leaf)

    def _insert_into_parent(self, left_child: BTreeNode, key: Any, right_child: BTreeNode):
        if left_child == self.root:
            new_root = BTreeNode(is_leaf=False)
            new_root.keys = [key]
            new_root.children = [left_child, right_child]
            self.root = new_root
            return

        parent = self._find_parent(self.root, left_child)
        if not parent:
            return

        idx = parent.children.index(left_child)
        parent.keys.insert(idx, key)
        parent.children.insert(idx + 1, right_child)

        if len(parent.keys) > self.max_keys:
            self._split_internal(parent)

    def _split_internal(self, node: BTreeNode):
        mid = len(node.keys) // 2
        promoted_key = node.keys[mid]

        new_node = BTreeNode(is_leaf=False)
        new_node.keys = node.keys[mid + 1:]
        new_node.children = node.children[mid + 1:]

        node.keys = node.keys[:mid]
        node.children = node.children[:mid + 1]

        self._insert_into_parent(node, promoted_key, new_node)

    def _find_leaf(self, node: BTreeNode, key: Any) -> BTreeNode:
        if node.is_leaf:
            return node
        for idx, k in enumerate(node.keys):
            if key < k:
                return self._find_leaf(node.children[idx], key)
        return self._find_leaf(node.children[-1], key)

    def _find_leftmost_leaf(self, node: BTreeNode) -> BTreeNode:
        if node.is_leaf:
            return node
        return self._find_leftmost_leaf(node.children[0])

    def _find_parent(self, curr: BTreeNode, child: BTreeNode) -> Optional[BTreeNode]:
        if curr.is_leaf or not curr.children:
            return None
        if child in curr.children:
            return curr
        for c in curr.children:
            res = self._find_parent(c, child)
            if res:
                return res
        return None

    def get_visual_tree(self) -> dict:
        """Export B+ tree node hierarchy into JSON schema for UI graphing."""
        def export_node(node: BTreeNode) -> dict:
            if node.is_leaf:
                return {
                    "id": f"Node_{node.node_id}",
                    "type": "LEAF",
                    "keys": [str(k) for k in node.keys],
                    "rid_count": sum(len(r) for r in node.rids),
                    "children": []
                }
            else:
                return {
                    "id": f"Node_{node.node_id}",
                    "type": "INTERNAL",
                    "keys": [str(k) for k in node.keys],
                    "children": [export_node(c) for c in node.children]
                }
        return export_node(self.root)
