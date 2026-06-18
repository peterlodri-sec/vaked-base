# Security — @vaked/openrouter-ts

## Supply-Chain Posture

| Layer | Mechanism |
|-------|-----------|
| **Lockfile** | `package-lock.json` v3 — exact versions, integrity hashes |
| **Engine strict** | `engine-strict=true` in `.npmrc` — blocks install on wrong Node |
| **Audit gate** | `npm audit --audit-level=high` — fails CI on high/critical vulns |
| **Overrides** | `package.json` overrides pin known-safe versions of common packages |
| **Minimal deps** | 3 runtime deps (`@openrouter/agent`, `zod`, `langfuse`) + 2 dev deps |
| **No install scripts** | All deps are pure JS — no native compilation, no postinstall risk |

## Common Vulnerability Defenses

Our `package.json` `overrides` field pins minimum safe versions for 25+
commonly-vulnerable transitive packages, including:

| Category | Packages |
|----------|----------|
| **Prototype pollution** | `protobufjs`, `json5`, `minimist`, `tough-cookie` |
| **ReDoS** | `semver`, `word-wrap`, `http-cache-semantics`, `debug` |
| **SSRF** | `node-fetch` |
| **Path traversal** | `vite`, `webpack-dev-middleware` |
| **Auth/token leaks** | `jsonwebtoken`, `jose` |
| **General hardening** | `cross-spawn`, `micromatch`, `braces`, `glob`, `glob-parent`, `path-to-regexp` |

These overrides activate even if the vulnerable package enters the tree
through a future dependency addition — defense-in-depth.

## CI Security Checks

```bash
npm run audit          # Fail on high/critical vulns
npm run audit:all      # Show all vulns (info only)
npm run outdated       # Check for stale packages
npm run sbom           # Generate CycloneDX SBOM
```

## Secret Handling

| Secret | Source | Guard |
|--------|--------|-------|
| `OPENROUTER_API_KEY` | GitHub CI Environment `ci` | Throws if unset (required) |
| `CONTEXT7_API_KEY` | GitHub CI Environment `ci` | Tools return error messages, never crash |
| `LANGFUSE_SECRET_KEY` | GitHub CI Environment `ci` | No-op when unset, never crash |
| `LANGFUSE_PUBLIC_KEY` | GitHub CI Environment `ci` | No-op when unset, never crash |

All secrets come from the GitHub CI Environment — never hardcoded, never in
source. The guard pattern ensures agents no-op cleanly when secrets are unset
(except `OPENROUTER_API_KEY` which is required for LLM calls).

## Reporting

Found a vulnerability? Open an issue or email security@vaked.dev.
Do not disclose publicly until patched.

## Genesis

```
GENESIS_SEAL: 7c242080
```
