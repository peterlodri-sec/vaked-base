# Integrating CrabCC Indexing & MCP Server

This plan outlines the architecture, setup steps, and verification procedures to integrate `crabcc` (a private, high-performance symbol indexing tool) into another repository and organization of yours, enabling LLM-based CI/CD agents to perform deep code symbol resolution (references, definitions, and callers) via the Model Context Protocol (MCP).

## User Review Required

> [!IMPORTANT]
> Since `crabcc-labs/crabcc` is a private repository, the integration relies on the `CRABCC_INSTALL_TOKEN` secret. Please verify that:
> 1. The machine user or GitHub App has been added to [crabcc-labs/teams/vaked/members](https://github.com/orgs/crabcc-labs/teams/vaked/members) with read permission.
> 2. The secret `CRABCC_INSTALL_TOKEN` is populated in your target repository's GitHub Action Secrets (under the `ci` environment or repository-wide).

## Proposed Integration Plan

The integration is split into three main parts: private installation, repository indexing with cache support, and connecting the MCP server to your AI agent.

---

### 1. Installation & Caching in GitHub Actions

Add the following steps to your CI workflow (e.g., `.github/workflows/ci.yml`).

#### A. Cache the Symbol Index
To prevent indexing the entire repository on every commit, cache the `.crabcc` directory. If the directory exists, `crabcc` will automatically perform a fast incremental update (`refresh`) instead of a full rebuild.

```yaml
- name: Cache crabcc index
  uses: actions/cache@v5
  with:
    path: .crabcc
    key: crabcc-index-${{ github.repository }}-${{ github.ref_name }}
    restore-keys: |
      crabcc-index-${{ github.repository }}-
```

#### B. Cache the `crabcc` Binary
Compile `crabcc` from source only when the version changes.

```yaml
- name: Cache crabcc binary (v6.5.1)
  id: crabcc-bin-cache
  uses: actions/cache@v5
  with:
    path: ~/.cargo/bin/crabcc
    key: crabcc-bin-v6.5.1-${{ runner.os }}
```

#### C. Install `crabcc-cli` privately
Configure git to use the PAT token when pulling from `crabcc-labs` on GitHub, then install the binary.

```yaml
- name: Install crabcc v6.5.1 (optional)
  if: ${{ env.CRABCC_INSTALL_TOKEN != '' && steps.crabcc-bin-cache.outputs.cache-hit != 'true' }}
  env:
    CRABCC_INSTALL_TOKEN: ${{ secrets.CRABCC_INSTALL_TOKEN }}
  run: |
    git config --global url."https://x-access-token:${CRABCC_INSTALL_TOKEN}@github.com/".insteadOf "https://github.com/"
    CARGO_NET_GIT_FETCH_WITH_CLI=true \
      cargo install --git https://github.com/crabcc-labs/crabcc --tag v6.5.1 crabcc-cli --force || \
      echo "crabcc install failed — workflow will degrade gracefully to diff-only"
```

---

### 2. Local/CI Indexing Lifecycle

To update the symbol index, run the following commands in the root of your repository:

* **Initialization (First Run):**
  If `.crabcc` does not exist, initialize it:
  ```bash
  mkdir .crabcc
  crabcc index build
  ```
  *(Creating the `.crabcc` directory in the repository root instructs the CLI to store the database locally in the workspace instead of the global `~/.crabcc/repos/` store, enabling GitHub Actions cache to capture it).*

* **Incremental Update:**
  On subsequent runs, refresh the index:
  ```bash
  crabcc index refresh
  ```

---

### 3. Connecting the MCP Server to the Agent

When your custom review/agent binary runs, it should spawn `crabcc --mcp` as a subprocess and establish an MCP stdio transport connection:

```rust
// Example connection logic in Rust (mimicking your pr-review agent)
pub(crate) async fn connect_crabcc() -> Result<McpToolset> {
    let bin = std::env::var("CRABCC_BIN").unwrap_or_else(|_| "crabcc".to_string());
    
    // Ensure index is ready/refreshed
    let sub = if std::path::Path::new(".crabcc").is_dir() { "refresh" } else { "build" };
    std::process::Command::new(&bin).args(["index", sub]).status()?;

    // Spawn the MCP server
    let mut command = tokio::process::Command::new(&bin);
    command.arg("--mcp");
    
    let transport = TokioChildProcess::new(command)?;
    let client = McpClient::serve(transport).await?;
    
    Ok(McpToolset::new(client).with_name("crabcc"))
}
```

---

## Verification Plan

### Automated Local Verification
To test the integration locally before running in CI:
1. Ensure the `crabcc` binary is installed:
   ```bash
   crabcc --version
   ```
2. Build a local index inside a test folder:
   ```bash
   mkdir -p test-index/.crabcc
   cd test-index
   crabcc index build
   ```
3. Verify the generated database exists:
   ```bash
   ls -la .crabcc/index.db
   ```
4. Test running the MCP server locally over stdio:
   ```bash
   crabcc --mcp
   ```
   *(It should start and wait for an MCP handshake).*

### Manual CI Verification
1. Push the updated workflow to a branch.
2. Verify the `Cache crabcc index` step restores successfully on subsequent commits.
3. Check workflow logs to ensure `crabcc index build` or `crabcc index refresh` finishes with status `0`.
