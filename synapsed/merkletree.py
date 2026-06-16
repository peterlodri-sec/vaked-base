"""Merkle tree over the capability graph — enables delta-sync between nodes.

Structure::

    MerkleNode {
        path: str           # e.g. "genesis.vaked.dev/network/egress"
        hash: str           # sha256(content || children hashes)
        children: {str: MerkleNode}   # sorted by key
        leaf_value: dict | None       # present only at leaves
    }

The Merkle root hash uniquely identifies the full capability graph state.
A difference in root hashes between two nodes triggers a subtree diff to
find exactly which capabilities diverged — enabling O(log N) delta sync.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


def _canonical_json(obj: dict) -> bytes:
    """Canonical JSON for hash computations."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


@dataclass
class MerkleNode:
    """A node in the capability-graph Merkle tree."""

    path: str
    hash: str = ""
    children: dict[str, "MerkleNode"] = field(default_factory=dict)
    leaf_value: Optional[dict] = None

    def compute_hash(self) -> str:
        """Compute and cache this node's hash from its children."""
        h = hashlib.sha256()
        # Include path
        h.update(self.path.encode("utf-8"))
        # Include leaf value if present
        if self.leaf_value is not None:
            h.update(_canonical_json(self.leaf_value))
        # Include children in sorted order
        for key in sorted(self.children.keys()):
            child = self.children[key]
            child_hash = child.compute_hash()
            h.update(key.encode("utf-8"))
            h.update(child_hash.encode("ascii"))
        self.hash = h.hexdigest()
        return self.hash

    def to_dict(self) -> dict:
        """Serialize for wire transfer."""
        d: dict = {"path": self.path, "hash": self.hash}
        if self.leaf_value is not None:
            d["leaf_value"] = self.leaf_value
        if self.children:
            d["children"] = {k: v.to_dict() for k, v in sorted(self.children.items())}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MerkleNode":
        """Deserialize from wire transfer."""
        node = cls(path=d["path"], hash=d.get("hash", ""), leaf_value=d.get("leaf_value"))
        for key, child_d in d.get("children", {}).items():
            node.children[key] = cls.from_dict(child_d)
        return node


class CapabilityMerkleTree:
    """A Merkle tree over the full capability graph.

    The tree is built from a flat dict of capability paths → values.
    ``/`` separates path segments.
    """

    def __init__(self):
        self.root = MerkleNode(path="/")
        self._leaf_count = 0

    @classmethod
    def from_capabilities(cls, capabilities: dict[str, dict]) -> "CapabilityMerkleTree":
        """Build a Merkle tree from a flat capability dict.

        ``capabilities`` maps paths like ``"genesis.vaked.dev/network/egress"``
        to their payload dicts.
        """
        tree = cls()
        for path, value in capabilities.items():
            tree._insert(path, value)
        tree.root.compute_hash()
        tree._leaf_count = len(capabilities)
        return tree

    def _insert(self, path: str, value: dict):
        """Insert a capability at ``path`` into the tree."""
        parts = path.strip("/").split("/")
        node = self.root
        for i, part in enumerate(parts):
            if part not in node.children:
                new_path = "/" + "/".join(parts[: i + 1])
                node.children[part] = MerkleNode(path=new_path)
            node = node.children[part]
        node.leaf_value = value

    def insert(self, path: str, value: dict) -> str:
        """Insert or update a capability and return the new root hash."""
        self._insert(path, value)
        self._leaf_count += 1
        return self.root.compute_hash()

    @property
    def root_hash(self) -> str:
        """Current Merkle root hash."""
        if not self.root.hash:
            self.root.compute_hash()
        return self.root.hash

    @property
    def leaf_count(self) -> int:
        return self._leaf_count

    def diff(self, other: "CapabilityMerkleTree", prefix: str = ""
             ) -> list[tuple[str, dict]]:
        """Compute the diff between this tree and ``other``.

        Returns list of ``(path, value)`` for capabilities that exist in
        ``self`` but not in ``other``, or whose hashes differ.
        """
        diffs: list[tuple[str, dict]] = []
        self._diff_recursive(self.root, other.root if other else MerkleNode(path="/"), prefix, diffs)
        return diffs

    def _diff_recursive(self, a: MerkleNode, b: MerkleNode, prefix: str, diffs: list):
        """Recursive diff helper."""
        # Check if the node exists in b
        if b.path == "/" and not b.children:
            # b is empty — everything in a is new
            if a.leaf_value is not None:
                diffs.append((a.path, a.leaf_value))
            for key in sorted(a.children.keys()):
                self._diff_recursive(a.children[key], MerkleNode(path=""), prefix, diffs)
            return

        if a.hash == b.hash:
            return  # Subtree identical

        # Hashes differ — recurse into children
        if a.leaf_value is not None:
            diffs.append((a.path, a.leaf_value))

        all_keys = set(a.children.keys()) | set(b.children.keys())
        for key in sorted(all_keys):
            child_a = a.children.get(key, MerkleNode(path=""))
            child_b = b.children.get(key, MerkleNode(path=""))
            self._diff_recursive(child_a, child_b, prefix, diffs)

    def to_dict(self) -> dict:
        """Full serialization for wire transfer."""
        return self.root.to_dict()

    @classmethod
    def from_dict(cls, d: dict) -> "CapabilityMerkleTree":
        """Deserialize from wire transfer."""
        tree = cls()
        tree.root = MerkleNode.from_dict(d)
        tree._count_leaves()
        return tree

    def _count_leaves(self):
        """Recount leaf nodes."""
        count = 0

        def _walk(node: MerkleNode):
            nonlocal count
            if node.leaf_value is not None:
                count += 1
            for child in node.children.values():
                _walk(child)

        _walk(self.root)
        self._leaf_count = count

    def verify_integrity(self) -> bool:
        """Recompute all hashes and verify the tree is self-consistent."""
        try:
            computed = self.root.compute_hash()
            return computed == self.root_hash
        except Exception:
            return False
