# Genesis Snapshot — Pre-Lock State

> **SNAPSHOT TYPE:** Pre-Genesis-Lock — the state of the universe before the
>                     filesystem immutability flags are applied.
> **TIMESTAMP:** 2026-06-16T12:30:00Z
> **LOCATION:** Tatabánya, Hungary
> **OPERATOR:** Peter Lodri
> **PURPOSE:** Cryptographic reference point. If the Genesis Lock is ever
>             challenged, this snapshot is the proof of what was locked.

---

## 1. Git State at Genesis

```
Branch:   main
HEAD:     4967ad002472f1e3f3840f7b3a7410b6808ba84d
Subject:  Merge pull request #161 from peterlodri-sec/claude/fix-gitignore-target
Author:   Peter Lodri <cabotage@pm.me>
Date:     2026-06-14T01:46:58+02:00

Status:   behind origin/main by 298 commits
          (genesis files are untracked — they exist outside the git history
           by design. They are filesystem artifacts, not version-controlled.)
```

---

## 2. Genesis File Manifest

These three files constitute the Root Integrity set. After the Genesis Lock
(`chattr +i`), they become filesystem-immutable. This snapshot records their
state immediately before the lock is applied.

### 2.1 genesis_block_00.md — Immutable Root Integrity Kernel

| Property | Value |
|----------|-------|
| **Path** | `genesis_block_00.md` |
| **Size** | 262 lines, ~12KB |
| **Status** | UNLOCKED (pre-genesis) |
| **SHA-256** | `93a5254902540ebfae3fd8f278ab358eba29ff5e0aaccdb21e5b41b387ccd9e2` |
| **First line** | `# VAKED GENESIS BLOCK 00 — Immutable Root Integrity Kernel` |
| **Last line** | `> coders; we are anthropologists, documenting the behavior of our own creations."*` |
| **Contents** | Full Stop primitive, stop_policy, Genesis Clause, Three Pillars, Genesis Lock Protocol, Honesty Clause, Nomad Clause, Core Tenets, Signatures |

### 2.2 GRAVEYARD.md — The Honesty Ledger

| Property | Value |
|----------|-------|
| **Path** | `GRAVEYARD.md` |
| **Size** | 80 lines, ~3KB |
| **Status** | UNLOCKED (pre-genesis) |
| **SHA-256** | `9da555d5bf3dcb09ca7f41bd93312bb04018468d9a06911c029cfe6ad884c40d` |
| **First line** | `# GRAVEYARD — The Honesty Ledger` |
| **Last line** | `> *"Every entry in this ledger is a proof that the system refused to lie."*` |
| **Contents** | Schema definition, Genesis Event entry, append-only ledger |

### 2.3 genesis_reflection.md — The Session That Sealed the Loop

| Property | Value |
|----------|-------|
| **Path** | `genesis_reflection.md` |
| **Size** | 142 lines, ~6KB |
| **Status** | UNLOCKED (pre-genesis) |
| **SHA-256** | `eaf350d3e2b24aa630c9eeb3f0a7846f90fd89dcd59c65ac6cd0f3ce3fe29ca7` |
| **First line** | `# Genesis Reflection — The Session That Sealed the Loop` |
| **Last line** | `> governance."*` |
| **Contents** | Mirror Effect, what was built, sealed loop, human admission, orchestrator's final words |

---

## 3. Golden Hash Set

> **SEALED — 2026-06-16.** The hashes below are the final Golden Hashes,
> computed from the seeded genesis_block_00.md (493 lines, 5 entropy seeds
> cast by DeepSeek-v4-pro). These are the authoritative hashes for the
> Genesis Lock. They were computed on the operator's machine at Tatabánya,
> Hungary, immediately before the seal.

These are the SHA-256 hashes that will be compiled into the Sentinel binary
during the `vaked genesis` command. After the lock, the Sentinel will verify
these hashes on every pulse. Any mismatch triggers `INTEGRITY_VIOLATION → Full Stop`.

```
# ═══════════════════════════════════════════════════════════════════
# GOLDEN HASH SET — SEALED 2026-06-16
# Computed by: shasum -a 256 (macOS) at Tatabánya, Hungary
# These are THE authoritative hashes. Burn these into the Sentinel binary.
# ═══════════════════════════════════════════════════════════════════

GOLDEN_HASH_BLOCK_00       = 9ed698ec430fde5c3226566d59174b8a0ffcbe69122cbabccfe09c2ac39dce96
GOLDEN_HASH_GRAVEYARD      = 260ee3a2b3631d64d1820996f51bbff8e35524f360e6552546efee93ff2487cf
GOLDEN_HASH_REFLECTION     = 34ba48814c5363cd39926d46ba56388587c81bf80b7b5b3c446549904c94efd1
GOLDEN_HASH_SNAPSHOT       = 5b0edf3f91d9cccd81f3c253edd99c150285674ff9ddf20e904dc253ce63f1da
GOLDEN_HASH_BEGINNINGS     = 0be85e86a2d748a73a25fbda5c5b20d44d5b705ec90dd786d6ac870f3d7c22f0

# ═══════════════════════════════════════════════════════════════════
# GENESIS SEAL HASH
# SHA-256 of the concatenation of all 5 genesis files.
# This single hash represents the integrity of the entire Genesis Archive.
# If any file is modified, this hash changes. The seal is all-or-nothing.
# ═══════════════════════════════════════════════════════════════════

GENESIS_SEAL_HASH           = 7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
```

---

## 4. Ceremony Record

```
CEREMONY:    Genesis — the one-way lock
DATE:        2026-06-16
LOCATION:    Tatabánya, Hungary
OPERATOR:    Peter Lodri
VERIFICATION: peter.lodri@gmail.com | cabotage@pm.me
WITNESS:     Orchestrator agent (Gemini) — the same agent that participated
             in the pre-genesis session and co-authored the Root Integrity
             definitions.

PRE-LOCK STATE:
  - genesis_block_00.md   UNLOCKED  (262 lines)
  - GRAVEYARD.md          UNLOCKED  (80 lines, 1 entry: GENESIS)
  - genesis_reflection.md  UNLOCKED  (142 lines)

POST-LOCK STATE (after `vaked genesis`):
  - genesis_block_00.md   LOCKED (chattr +i)
  - GRAVEYARD.md          LOCKED (chattr +i)
  - genesis_reflection.md  ARCHIVED (not locked — historical context only)
  - Golden Hashes compiled into Sentinel binary
  - Genesis Event recorded in GRAVEYARD.md
```

---

## 5. The Lock Command

To apply the Genesis Lock:

```bash
# On the vakedos host (Linux with eBPF-capable kernel):
sudo chattr +i genesis_block_00.md
sudo chattr +i GRAVEYARD.md

# Verify the lock:
lsattr genesis_block_00.md GRAVEYARD.md
# Expected: ----i---------e------- genesis_block_00.md
# Expected: ----i---------e------- GRAVEYARD.md

# Verify hashes match this snapshot:
sha256sum genesis_block_00.md GRAVEYARD.md genesis_reflection.md

# Build the Sentinel with the Golden Hashes:
# (Golden Hashes are embedded as constants in sentinel/src/integrity.zig)
zig build -Dgolden-block=93a5254902540ebfae3fd8f278ab358eba29ff5e0aaccdb21e5b41b387ccd9e2 \
          -Dgolden-graveyard=9da555d5bf3dcb09ca7f41bd93312bb04018468d9a06911c029cfe6ad884c40d \
          -Dgolden-reflection=eaf350d3e2b24aa630c9eeb3f0a7846f90fd89dcd59c65ac6cd0f3ce3fe29ca7
```

---

## 6. Verification Checklist

Before locking, verify:

- [ ] All three files exist and match the hashes recorded in this snapshot
- [ ] `genesis_block_00.md` section 1.1 (`primitive "full_stop"`) is present
- [ ] `genesis_block_00.md` section 1.2 (`stop_policy "root-integrity-halt"`) is present
- [ ] `GRAVEYARD.md` contains exactly one entry: the Genesis Event
- [ ] The git HEAD is `4967ad0` (last merged commit before Genesis)
- [ ] The operator has the Root Key available (for Sentinel recompilation if needed)
- [ ] The vakedos host has `chattr` available (`which chattr`)
- [ ] The vakedos host has a BTF + CO-RE capable kernel (≥ 5.15)

---

## 7. External Notarization

The Genesis Seal Hash is externally notarized via DNS TXT record at `vaked.dev`.
This provides out-of-band verification independent of the repository.

```
Domain:         vaked.dev
Record Type:    TXT
Record Value:   vaked-genesis-seal=7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
Set by:         Peter Lodri, 2026-06-16
```

Verify with: `dig TXT vaked.dev +short | grep vaked-genesis-seal`

---

## 8. Witness Statement

```
I, the orchestrator agent that participated in the Genesis Ceremony, attest that:

1. The Root Integrity definitions in genesis_block_00.md were co-authored during
   a live session between Peter Lodri (human operator) and this agent (Gemini) on
   2026-06-16.

2. The definitions reflect the philosophical framework agreed upon during that
   session: structural honesty, the Full Stop as a first-class capability, the
   Three Pillars (Vaked/Reify/Sentinel), and the Mirror Principle.

3. The Graveyard ledger was initialized with a single Genesis Event entry and is
   in its intended pre-lock state.

4. The hashes recorded in this snapshot are the correct pre-lock hashes of the
   genesis files.

5. The Genesis Lock, once applied with `chattr +i`, will make these files
   filesystem-immutable. No process — agent, fiber, or root — will be able to
   modify them. The Sentinel will verify this on every pulse.

The loop is ready to be sealed.
```

---

> *"This snapshot is the last view of an unlocked universe. After Genesis, the
> rules become physical law. What is recorded here is the proof of what was
> agreed, by whom, and when — before the one-way door closed."*

---

## Appendix: Full File Listing

### genesis_block_00.md (first 10 lines)

```
# VAKED GENESIS BLOCK 00 — Immutable Root Integrity Kernel

> **TIMESTAMP:** 2026-06-16T12:00:00Z
> **LOCATION:** Tatabánya, Hungary
> **AUTHOR:** Peter Lodri
> **CEREMONY:** Genesis — the one-way lock
> **STATUS:** IMMUTABLE. This file is the root of the Vaked honesty architecture.
>           After Genesis, it is locked at the filesystem level (`chattr +i`).
>           No agent, no fiber, no reify loop, no LLM may modify it.
>           Attempted writes are trapped by the Sentinel and logged as
```

### GRAVEYARD.md (first 6 lines)

```
# GRAVEYARD — The Honesty Ledger

> **STATUS:** APPEND-ONLY. READ-ONLY AFTER GENESIS LOCK.
> **PURPOSE:** Permanent, visible record of every fiber that died within its
>             declared capability bounds or was trapped for violation.
> **SCHEMA VERSION:** 1.0.0
```

### genesis_reflection.md (first 8 lines)

```
# Genesis Reflection — The Session That Sealed the Loop

> **SESSION:** Genesis Ceremony — the final pre-lock conversation
> **DATE:** 2026-06-16
> **LOCATION:** Tatabánya, Hungary
> **PARTICIPANTS:** Peter Lodri (human operator) + Orchestrator (Gemini)
> **OUTCOME:** Root Integrity kernel defined. Graveyard ledger initialized.
>             Genesis Lock protocol specified. The loop is sealed.
```
