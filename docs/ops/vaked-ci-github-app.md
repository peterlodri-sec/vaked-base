# vaked-ci GitHub App Setup Runbook

## 1. Overview: GitHub App vs Personal Access Token

The `vaked-ci` GitHub App replaces personal-PAT and `GITHUB_TOKEN` auth across the CI swarm with a dedicated, least-privilege, auditable application identity.

**Key benefits:**
- **Short-lived tokens:** Installation tokens expire in 1 hour and are auto-rotated per request.
- **Least privilege:** Permissions are granular (no `repo` wildcard; no admin scope).
- **Auditable:** All App actions are logged under a distinct "vaked-ci" identity, not your personal account.
- **Revocable:** Suspend or uninstall the App to immediately revoke all tokens, without rotating PATs across workflows.

---

## 2. Register the GitHub App

> **Human-only step.** This must be done manually at github.com.

1. Go to **https://github.com/settings/apps/new** (GitHub Settings → Developer settings → GitHub Apps → New GitHub App).

2. Fill in the form with the following values:

   | Field | Value |
   |-------|-------|
   | **GitHub App name** | `vaked-ci` |
   | **Homepage URL** | `https://github.com/peterlodri-sec/vaked-base` |
   | **Webhook active** | `false` (uncheck; App is read/write only, no inbound events) |
   | **Permissions** | See table below |
   | **Where can this app be installed?** | Only on this account |

3. **Permissions table** (exact scopes required):

   | Permission | Category | Access Level |
   |-----------|----------|--------------|
   | Contents | Repository | Read and write |
   | Pull requests | Repository | Read and write |
   | Issues | Repository | Read and write |
   | Actions | Repository | Read and write |
   | Metadata | Repository | Read-only |

   All other permissions remain **unchecked**.

4. Click **Create GitHub App**. Note the **App ID** (displayed on the settings page).

---

## 3. Generate and Store the Private Key

> **Human-only step.** Key generation and download happen via GitHub UI; local storage is manual.

### On GitHub

1. On the App settings page (https://github.com/settings/apps/vaked-ci), scroll to **Private keys** at the bottom.
2. Click **Generate a private key**. GitHub generates a `.pem` file and automatically downloads it (e.g., `vaked-ci.2026-06-18.private-key.pem`).
3. **Keep this file safe.** Do not commit it to the repository.

### Store the PEM locally

1. Create the config directory (if it doesn't exist):
   ```bash
   mkdir -p ~/.config/vaked-ci
   ```

2. Move or copy the downloaded PEM file:
   ```bash
   cp ~/Downloads/vaked-ci.*.private-key.pem ~/.config/vaked-ci/app.pem
   chmod 600 ~/.config/vaked-ci/app.pem
   ```

3. Verify it is readable by your user only:
   ```bash
   ls -la ~/.config/vaked-ci/app.pem
   # Output should show rw------- (mode 600)
   ```

### Add to CI secrets

1. Go to the repository: **Settings → Environments → ci** (the `ci` GitHub environment).
2. Under **Environment secrets**, click **Add secret**:
   - **Name:** `VAKED_CI_APP_PRIVATE_KEY`
   - **Value:** Paste the **entire contents** of the `.pem` file (including `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----` lines).
3. Click **Add secret**.

---

## 4. Install the App on the Repository

> **Human-only step.** Installation and Installation ID retrieval are done via GitHub UI.

1. Go to your GitHub App settings: **https://github.com/settings/apps/vaked-ci**
2. Click the **Install App** button (left sidebar, or near the top of the page).
3. Select the account/organization where you want to install it (should be `peterlodri-sec`).
4. On the next screen, select the **peterlodri-sec/vaked-base** repository under "Repository access."
5. Click **Install**.
6. You will be redirected to a URL like:
   ```
   https://github.com/settings/installations/<INSTALLATION_ID>
   ```
   **Note the `<INSTALLATION_ID>` in the URL.** You may need it for debugging, but it is not stored as a secret (the App + repo combination implicitly identifies the installation).

---

## 5. Add Secrets to the CI Environment

> **Human-only step.** Add both secrets via GitHub UI.

Go to **Settings → Environments → ci** and add two environment secrets:

| Secret Name | Value |
|-------------|-------|
| `VAKED_CI_APP_ID` | The numeric **App ID** from the App settings page (Settings → Developer settings → GitHub Apps → vaked-ci → About) |
| `VAKED_CI_APP_PRIVATE_KEY` | The full PEM file contents (added in Step 3 above) |

Both secrets are now available to workflows that run in the `ci` environment.

---

## 6. Using the App

The `vaked-ci` GitHub App is accessed via two paths:

### Local Use: `tools/ghapp/mint-token.sh`

For local CI development or ad-hoc testing, use the local minter:

```bash
export VAKED_CI_APP_ID="<your-app-id>"
# GHAPP_PRIVATE_KEY_FILE defaults to ~/.config/vaked-ci/app.pem
bash tools/ghapp/mint-token.sh
```

Output: a short-lived (1-hour) installation token on stdout.

**See** `tools/ghapp/mint-token.sh` for details.

### CI Workflows: `ghapp-token` Composite Action

In GitHub Actions workflows, use the `ghapp-token` composite action to mint tokens without writing JWT logic:

```yaml
- name: Mint app token
  id: app_token
  uses: ./.github/actions/ghapp-token
  with:
    app-id: ${{ secrets.VAKED_CI_APP_ID }}
    private-key: ${{ secrets.VAKED_CI_APP_PRIVATE_KEY }}

- name: Use the token for gh CLI
  env:
    GH_TOKEN: ${{ steps.app_token.outputs.token }}
  run: gh pr list
```

**See** `.github/actions/ghapp-token/action.yml` for the composite definition.

---

## 7. Rotating and Revoking Access

### Rotate the Private Key

If the private key is compromised or expires:

1. On the App settings page, go to **Private keys** → **Generate a private key** to issue a new key.
2. Download the new PEM file.
3. Update `~/.config/vaked-ci/app.pem` locally:
   ```bash
   cp ~/Downloads/vaked-ci.*.private-key.pem ~/.config/vaked-ci/app.pem
   chmod 600 ~/.config/vaked-ci/app.pem
   ```
4. Update the `VAKED_CI_APP_PRIVATE_KEY` secret in **Settings → Environments → ci** with the new PEM contents.
5. (Optional) Delete the old private key from the GitHub App settings (GitHub will show all issued keys; click the trash icon on the old one).

### Revoke All Access

To immediately revoke all App access to the repository:

**Option A: Suspend the App**
1. Go to **Settings → Developer settings → GitHub Apps → vaked-ci → Advanced** → **Suspend**.
2. All existing tokens become invalid immediately.

**Option B: Uninstall the App**
1. Go to **Settings → Integrations → GitHub Apps** → **vaked-ci** → **Uninstall**.
2. All tokens are revoked; you must re-install the App and regenerate secrets if you want to use it again.

---

## 8. Human-Only Setup Checklist

The following steps **must be performed manually** (not automated, not by scripts):

- [ ] **Register the App** at https://github.com/settings/apps/new with name `vaked-ci` and exact permissions (Contents RW, Pull requests RW, Issues RW, Actions RW, Metadata RO).
- [ ] **Generate and download the private key** from the App settings page; save it to `~/.config/vaked-ci/app.pem` with `chmod 600`.
- [ ] **Install the App** on the `peterlodri-sec/vaked-base` repository via the GitHub UI.
- [ ] **Add `VAKED_CI_APP_ID` secret** to the `ci` environment with the numeric App ID.
- [ ] **Add `VAKED_CI_APP_PRIVATE_KEY` secret** to the `ci` environment with the full PEM file contents.

Once all five steps are complete, the App is ready for use in workflows and local scripts.
