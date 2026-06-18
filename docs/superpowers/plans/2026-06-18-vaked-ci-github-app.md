# Plan — `vaked-ci` GitHub App (fleet auth)

Replace personal-PAT / `GITHUB_TOKEN` auth across the swarm with one least-privilege
GitHub App installation. Short-lived (1h) auto-rotating installation tokens, fine-grained
per-repo scopes, auditable, revocable.

## Global Constraints (bind every task + reviewer)
- **No compile on the dev machine.** Scripts are bash/python (stdlib + `openssl`/`curl`); GHA runs remote.
- **Secrets never in repo or logs.** App ID, Installation ID, and the private-key PEM live ONLY as `ci`-env GitHub secrets (`VAKED_CI_APP_ID`, `VAKED_CI_APP_PRIVATE_KEY`) and, for local use, a gitignored PEM path (`$GHAPP_PRIVATE_KEY_FILE`, default `~/.config/vaked-ci/app.pem`). Never echo a key or token. Tokens printed by the minter go to stdout only for capture, never logged.
- **CI uses the official `actions/create-github-app-token@v1`** — do NOT hand-roll JWT minting inside workflows.
- **Least privilege:** App permissions = Contents RW, Pull requests RW, Issues RW, Actions RW, Metadata RO. Nothing else.
- **Human-only steps are documented, not automated:** App registration, private-key generation, repo installation, secret upload. The runbook must flag these explicitly.
- Idempotent, `set -euo pipefail`, shellcheck-clean bash. Pure-stdlib python if used.

## Human prerequisites (out of scope for code; Task 1 documents them)
Register App → set permissions → generate PEM → install on `peterlodri-sec/vaked-base` →
add `VAKED_CI_APP_ID` + `VAKED_CI_APP_PRIVATE_KEY` to the `ci` Environment.

---

## Task 1 — Runbook `docs/ops/vaked-ci-github-app.md`
**Deliverable:** a single markdown runbook. No code execution.
**Must contain, in order:**
1. What/why (App vs PAT; short-lived tokens; least privilege).
2. **Register** (github.com/settings/apps/new): exact field values — name `vaked-ci`, homepage = repo URL, webhook OFF, permissions table (Contents RW, Pull requests RW, Issues RW, Actions RW, Metadata RO), "Only on this account".
3. **Generate private key** → download PEM. Where it goes: `ci` secret `VAKED_CI_APP_PRIVATE_KEY` (full PEM) + local `~/.config/vaked-ci/app.pem` (chmod 600, gitignored).
4. **Install** the App on `peterlodri-sec/vaked-base`; note the Installation ID.
5. **Secrets**: `VAKED_CI_APP_ID`, `VAKED_CI_APP_PRIVATE_KEY` in the `ci` Environment (Settings → Environments → ci).
6. **Use**: link to `tools/ghapp/mint-token.sh` (local) and the `ghapp-token` composite (CI).
7. **Rotate / revoke**: regenerate PEM, update secret; suspend/uninstall to revoke.
8. A "human-only steps" callout box listing 1–5 as manual.
**Done = file exists, all 8 sections present, permissions table exact.**

## Task 2 — Local minter `tools/ghapp/mint-token.sh`
**Deliverable:** executable bash that mints a 1h installation token.
**Spec:**
- Inputs (env): `VAKED_CI_APP_ID` (required), `GHAPP_PRIVATE_KEY_FILE` (default `~/.config/vaked-ci/app.pem`), `GHAPP_REPO` (default `peterlodri-sec/vaked-base`).
- Build RS256 JWT with `openssl`: header `{"alg":"RS256","typ":"JWT"}`, payload `{"iat":now-60,"exp":now+540,"iss":APP_ID}`, base64url (url-safe, no padding), sign payload with `openssl dgst -sha256 -sign "$PEM"`.
- `GET /repos/$GHAPP_REPO/installation` with `Authorization: Bearer <JWT>` → `.id`.
- `POST /app/installations/<id>/access_tokens` with the JWT → `.token`.
- Print ONLY the token to stdout. All diagnostics to stderr. `set -euo pipefail`. Fail clearly if PEM missing or `VAKED_CI_APP_ID` unset. Never echo the PEM or JWT.
- Header comment: usage + that the token expires in 1h.
**Tests:** `tools/ghapp/mint-token.test.sh` — unit-tests the JWT base64url encoder against a known vector and asserts the script fails fast (exit ≠ 0) when `VAKED_CI_APP_ID` is unset and when the PEM file is absent. No network in tests (mock/guard the curl calls or test only the pre-network failure paths + the encoder).
**Done = script + tests, tests pass, no secret ever printed.**

## Task 3 — CI composite `.github/actions/ghapp-token/action.yml` + migrate one workflow
**Deliverable:**
- A composite action `.github/actions/ghapp-token/action.yml` wrapping `actions/create-github-app-token@v1`, inputs `app-id`/`private-key`, output `token`. Documented.
- Migrate exactly ONE low-risk reference workflow to use it: replace its `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` (or PAT) with a `Mint app token` step (`uses: ./.github/actions/ghapp-token` with `app-id: ${{ secrets.VAKED_CI_APP_ID }}`, `private-key: ${{ secrets.VAKED_CI_APP_PRIVATE_KEY }}`) and `GH_TOKEN: ${{ steps.<id>.outputs.token }}`. Pick the lowest-risk candidate (e.g. `label-tagger.yml` if present; else the smallest gh-using workflow). Do NOT migrate `nocturne.yml` (cost-sensitive) or `swe-af.yml` (complex).
- Leave a one-line comment in each non-migrated gh-using workflow pointing to the runbook for later migration.
**Done = composite parses (yaml valid), one workflow migrated + still yaml-valid, others annotated.**
