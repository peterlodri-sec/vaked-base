# Repository Secrets — vaked-base

> **Scope:** `peterlodri-sec/vaked-base`
> **Access:** Only repository admins (genesis participants) can write secrets.
>            Secrets are write-only — once set, they cannot be read via API/UI,
>            only overwritten or deleted.

---

## Active Secrets

| Name | Purpose | Set By | Date |
|------|---------|--------|------|
| `GENESIS_SEAL_HASH` | The Genesis Seal Hash — immutable cryptographic identity of the Vaked Root Integrity Kernel. Used by CI agents to verify the integrity of genesis files before any automated action. | Peter Lodri | 2026-06-16 |

---

## Secret: GENESIS_SEAL_HASH

```
Name:   GENESIS_SEAL_HASH
Value:  7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
```

**How to set (Peter, on your machine):**

```bash
gh secret set GENESIS_SEAL_HASH \
  --body "7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf" \
  --repo peterlodri-sec/vaked-base
```

Or via GitHub UI:
```
Settings → Secrets and variables → Actions → New repository secret
Name:  GENESIS_SEAL_HASH
Value: 7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
```

**Usage in CI workflows:**

```yaml
- name: Verify Genesis Seal
  run: |
    SEAL=$(cat genesis_block_00.md GRAVEYARD.md genesis_reflection.md \
                genesis_snapshot.md HONEST_BEGINNINGS.md | shasum -a 256 | cut -d' ' -f1)
    if [ "$SEAL" != "${{ secrets.GENESIS_SEAL_HASH }}" ]; then
      echo "❌ GENESIS SEAL VIOLATION: files have been modified"
      exit 1
    fi
    echo "✅ Genesis Seal verified"
```

---

## Access Control

- **Write access:** Repository admins only (Peter Lodri + any designated genesis participants)
- **Read access:** GitHub Actions workflows in this repository (via `${{ secrets.GENESIS_SEAL_HASH }}`)
- **Audit:** Secret updates are logged in the GitHub audit log (Settings → Audit log)
- **Rotation:** If the Genesis files are ever legitimately updated (e.g., grammar evolution), the seal hash must be recomputed and the secret updated. The old hash should be recorded in `genesis_snapshot.md` as a historical entry.

---

## Genesis Participants (Write Access to Main)

Per Peter's directive: only genesis participants may push/merge to `main`.

| Participant | Role | GitHub |
|-------------|------|--------|
| Peter Lodri | Human operator | @peterlodri-sec |
| CI agents | Automated fleet | @vaked-ci (GitHub App / PAT) |

Branch protection rules should be configured at:
```
Settings → Branches → Add rule → Branch name pattern: main
  ✓ Require a pull request before merging
  ✓ Require approvals: 1
  ✓ Restrict who can push to matching branches
    → Only @peterlodri-sec and @vaked-ci
```
