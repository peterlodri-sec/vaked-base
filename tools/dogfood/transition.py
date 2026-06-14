"""dogfood.transition — content-addressed transition records + tree hashing.

A *transition* is one proposed change to the in-scope working tree. We capture
it as a **deterministic function of (base tree, post-images)** so it can be
replayed and hashed: the same base + the same captured post-images always
reproduce the same ``state_hash_after``. No textual diff/patch tooling is
involved — the "patch" is the set of post-image blob hashes for changed files,
stored content-addressed under a blob dir. This mirrors the eventd/ralph
discipline (sha256, canonical JSON, append-only) and stays pure-stdlib.

Why post-images instead of a unified diff: patch application via an external
``git apply``/``patch`` binary introduces an environment dependency and a
fuzz/whitespace nondeterminism surface. Overwriting files with captured exact
bytes is a pure, total function — the right primitive for a *deterministic*
replay kernel.
"""
from __future__ import annotations

import hashlib
import os

KIND = "dogfood_transition"
SCHEMA_V = 1


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: str) -> str:
    with open(path, "rb") as f:
        return sha256_hex(f.read())


def iter_scope_files(root: str, scope: list[str]):
    """Yield repo-relative paths of regular files under any granted scope dir.

    ``scope`` entries are repo-relative directory prefixes (e.g. ``tools/dogfood``).
    Hidden dirs and the blob/WAL state dir are skipped so the kernel never hashes
    its own ledger into the tree it is judging.
    """
    seen: set[str] = set()
    for prefix in scope:
        base = os.path.join(root, prefix)
        if os.path.isfile(base):
            rel = os.path.relpath(base, root)
            if rel not in seen:
                seen.add(rel)
                yield rel
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            # never descend into a nested .dogfood state dir or VCS metadata
            dirnames[:] = [d for d in dirnames if d not in (".git", ".dogfood")]
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root)
                if rel not in seen:
                    seen.add(rel)
                    yield rel


def tree_snapshot(root: str, scope: list[str]) -> dict[str, str]:
    """Map repo-relative path -> content sha for every in-scope file."""
    return {rel: file_sha(os.path.join(root, rel))
            for rel in iter_scope_files(root, scope)}


def tree_hash(snapshot: dict[str, str]) -> str:
    """Deterministic hash of a snapshot: sorted ``rel\\0sha`` lines, sha256'd.

    Order-independent of filesystem walk order (we sort), so two identical trees
    on two machines hash identically — the property the replay gate relies on.
    """
    body = "\n".join(f"{rel}\0{sha}" for rel, sha in sorted(snapshot.items()))
    return sha256_hex(body.encode("utf-8"))


def changed_set(base: dict[str, str], cur: dict[str, str]) -> dict[str, list[str]]:
    """Filesystem-level diff of two snapshots: writes (added/modified) + deletes.

    This is the *actual* effect of a proposal, used both to build the captured
    post-image set and to gate declared-vs-actual effects.
    """
    writes = sorted(rel for rel, sha in cur.items() if base.get(rel) != sha)
    deletes = sorted(rel for rel in base if rel not in cur)
    return {"writes": writes, "deletes": deletes}


# --- content-addressed blob store (the captured post-images) ----------------

def store_blob(blobs_dir: str, path: str) -> str:
    """Copy a file's exact bytes into the blob store, keyed by sha. Returns sha."""
    with open(path, "rb") as f:
        data = f.read()
    sha = sha256_hex(data)
    os.makedirs(blobs_dir, exist_ok=True)
    dest = os.path.join(blobs_dir, sha)
    if not os.path.exists(dest):           # content-addressed ⇒ write-once
        tmp = dest + ".tmp"
        with open(tmp, "wb") as w:
            w.write(data)
        os.replace(tmp, dest)
    return sha


def load_blob(blobs_dir: str, sha: str) -> bytes:
    with open(os.path.join(blobs_dir, sha), "rb") as f:
        data = f.read()
    if sha256_hex(data) != sha:            # blob store tamper check
        raise ValueError(f"blob {sha} content hash mismatch — corrupted store")
    return data


def capture_postimages(root: str, blobs_dir: str, writes: list[str]) -> dict[str, str]:
    """Store each written file's post-image; return {rel: post_sha}."""
    return {rel: store_blob(blobs_dir, os.path.join(root, rel)) for rel in writes}


def build_payload(*, intent: str, scope: list[str], input_tree_hash: str,
                  declared: dict, actual: dict, postimages: dict[str, str],
                  state_hash_after: str, capability_ok: bool,
                  observed: dict | None = None) -> dict:
    """Assemble the canonical transition payload appended to the WAL.

    ``patch_hash`` is the content hash of the captured post-image set — the
    deterministic identity of "what this transition changed".
    """
    patch_body = "\n".join(f"{rel}\0{sha}" for rel, sha in sorted(postimages.items()))
    patch_hash = sha256_hex(patch_body.encode("utf-8"))
    return {
        "kind": KIND,
        "v": SCHEMA_V,
        "intent": intent,
        "capability_scope": sorted(scope),
        "input_tree_hash": input_tree_hash,
        "patch_hash": patch_hash,
        "postimages": dict(sorted(postimages.items())),
        "declared_effects": {"writes": sorted(declared.get("writes", [])),
                             "deletes": sorted(declared.get("deletes", []))},
        "actual_effects": {"writes": sorted(actual.get("writes", [])),
                           "deletes": sorted(actual.get("deletes", []))},
        "observed_effects": observed,        # None until Frida (M3)
        "capability_ok": capability_ok,
        "state_hash_after": state_hash_after,
    }
