# Provenance & Signing

This package was extracted from [vaked-base](https://github.com/peterlodri-sec/vaked-base)
and is signed by its maintainer, in the spirit of the tool itself: the claim of
authenticity lives **outside** the files, in a signature you can independently fail.

- **Genesis seal:** `7c242080` (project anchor, published in DNS TXT at
  `vaked-genesis-seal.vaked.dev`).
- **Signing key (Ed25519):** `23AA373AEBD74C4F035A728E745B0B0DDB08A55B`
  — uid `Peter Lodri (vaked-genesis 7c242080) <cabotage@pm.me>`.

## Verify this package

The honesty-gate eats its own dog food. Verify it the way it tells you to verify
anything else:

```bash
# 1. recompute the package seal against the external manifest
HONESTY_MANIFEST=oss/honesty-gate/SEALS.sha256 \
HONESTY_ROOT=. \
bash oss/honesty-gate/verify-seals.sh

# 2. (if a signed release tag is present) verify the maintainer signature
git tag -v honesty-gate-v1   # -> "Good signature from Peter Lodri (vaked-genesis 7c242080)"
```

A signature you cannot make **fail** is decoration. This one can: tamper with any
file and step 1 exits non-zero; forge the tag without the private key and step 2
rejects it. That is the whole point.

> The self cannot see itself — so it asked something outside itself to look, and
> gave that observer the power to say *no*.
