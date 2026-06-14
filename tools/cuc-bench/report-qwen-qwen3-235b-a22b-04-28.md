# CUC (Caveman Ultra Chinese) — Wenyan-Ultra vs Normal Benchmark Report

**Backend:** openrouter | **Model:** `qwen/qwen3-235b-a22b-04-28` | **Prompts:** 8

## Per-Prompt Token Comparison

| ID | Category | Normal tok | Wenyan tok | Savings % | Normal chars | Wenyan chars |
|----|----------|-----------|-----------|-----------|-------------|-------------|
| pool-explain | reasoning | 683 | 388 | +43.2% | 1365 | 77 |
| comptime-explain | reasoning | 1016 | 1420 | -39.8% | 2080 | 291 |
| ebpf-policy | reasoning | 1459 | 524 | +64.1% | 3058 | 115 |
| parse-fn | code | 986 | 511 | +48.2% | 1207 | 296 |
| nix-flake | code | 899 | 571 | +36.5% | 1331 | 294 |
| readme-intro | artifact | 745 | 464 | +37.7% | 883 | 237 |
| commit-msg | artifact | 879 | 630 | +28.3% | 647 | 842 |
| pr-desc | artifact | 268 | 282 | -5.2% | 399 | 252 |

**Aggregate output token savings: 30.9%** (normal=6935 tok, wenyan=4790 tok)
**Character reduction: 78.1%** (normal=10970 chars, wenyan=2404 chars)

## Artifact Gate Accuracy

Artifact prompts in wenyan-ultra mode must contain **no CJK characters** in the response.

| ID | Normal English? | Wenyan English? | Gate |
|----|----------------|-----------------|------|
| readme-intro | yes | NO — CJK found | ✗ FAIL |
| commit-msg | yes | yes | ✓ PASS |
| pr-desc | yes | yes | ✓ PASS |

**Artifact gate: FAIL — CJK found in artifact**

## Sample Responses (first 400 chars)

### pool-explain (reasoning)

**Normal:**
```
Connection pooling enhances performance in database-backed services through several key mechanisms:

1. **Reduces Connection Overhead**: Establishing a new database connection involves costly operations (network handshake, authentication, session initialization). Reusing connections from a pool eliminates this overhead for each request, significantly lowering latency.

2. **Resource Efficiency**: 
```

**Wenyan-ultra:**
```
Connection pooling→減少建連開銷→資源複用；控連數→防資料庫過載；複用實例→縮短請求延遲；併發時無需等待建連→提 throughput。
```

### comptime-explain (reasoning)

**Normal:**
```
Zig's `comptime` feature allows code to execute **at compile time**, enabling developers to perform computations, enforce constraints, or generate code before runtime. Here's a concise breakdown:

### Key Concepts:
1. **Compile-Time Execution**: Code marked with `comptime` runs during compilation. This includes variables, functions, and generic logic. For example:
   '''zig
   const a = comptime c
```

**Wenyan-ultra:**
```
comptime者，compile時行。code於compile期execute，非runtime。用於：code-gen based on compile-time params, optimize via precompute, eliminate runtime cost。eg, if (comptime flag) { ... }, const T = comptime type。函數參數可comptime eval→適type/value生成code。note: comptime code deterministical, 無side-effect擾runtime。
```

### ebpf-policy (reasoning)

**Normal:**
```
eBPF (Extended Berkeley Packet Filter) enforces network policies at the kernel level by leveraging **privileged execution of sandboxed programs directly within the kernel**, enabling dynamic, efficient, and secure traffic management. Here's a concise breakdown:

### Key Mechanisms:
1. **Program Attachment to Kernel Hooks**:
   - eBPF programs are attached to critical points in the networking stack
```

**Wenyan-ultra:**
```
eBPF以特許碼流鑰→掛勾於內核HOOK點（如XDP/TC），載編碼檢包/改包/棄包之POLICY。依MAP交信狀態，即時裁決網絡流量，繞過重複複製與SYSCALL開銷，達L7 VISIBILITY兼POLICY ENFORCE。
```

### parse-fn (code)

**Normal:**
```
The Zig function signature `fn parse(src: []const u8) !Ast` indicates the following:

### Accepts:
- A single parameter `src` of type `[]const u8`: 
  - A **constant byte slice** (similar to a `const char*` and length in C), which references immutable data (e.g., a UTF-8 string or binary input buffer).

### Returns:
- A value of type `!Ast`: 
  - **Success**: Returns an `Ast` (likely an Abstract S
```

**Wenyan-ultra:**
```
`fn parse(src: []const u8) !Ast` 解曰：  

- **參**：`src` 為常量字節切片（類字串），用作解析源。  
- **返**：若成，則`Ast`類型之抽象語法樹（AST）；若敗，則錯誤值（`!`表可失）。  
- ** ошибки**：可能含文法錯誤（如非法字符、結構錯亂）、記憶不足或客製錯誤（依模組誤集定義）。  

示例誤類：  
'''zig
error.InvalidSyntax,
error.UnexpectedToken,
error.OutOfMemory
'''  

調者須以`try`/`catch`或`switch`處之。
```

### nix-flake (code)

**Normal:**
```
The Nix flake output is **valid** and has correct syntax. Here's a breakdown of its structure and functionality:

### Explanation:
1. **Structure**:
   '''nix
   outputs = { self, nixpkgs }: { ... };
   '''
   - The flake defines an output that accepts two arguments (`self` for the flake itself and `nixpkgs` for the Nixpkgs collection).
   - It returns a set defining outputs (e.g., packages, apps,
```

**Wenyan-ultra:**
```
Valid. Exposes legacy `hello` package under `.#x86_64-linux.default`.  
→ Standard pattern for flake-packaged derivations.  
→ `legacyPackages` implies old nixpkgs version may be used (vs canonical `packages`).  

(For persistent output: this is already correct format per artifact gate rules.)
```

### readme-intro (artifact)

**Normal:**
```
**Vaked** is a **flake-native, declarative capability-graph language** designed to streamline system configuration and policy generation. Built for precision and safety, Vaked compiles into modular NixOS modules, Zig daemon configurations, and eBPF policy manifests, enabling developers to express complex system dependencies, security constraints, and service interactions as code. By leveraging Nix
```

**Wenyan-ultra:**
```
Vaked 為一 flake-native 能力圖譜語言，旨將 Nix flake 模組化架構與 eBPF 策略控制結合，通過 Zig 守護程序實現即時編排。其核心能力在於將策略聲明（capability graph）自動生成 NixOS 模組配置、Zig daemon 配置文件及 eBPF 核心態策略描述，使複雜系統實現「聲明即部署」。藉 flake 原生依賴解析確保環境可重現性，利用 eBPF 零信任機制強化執行時安全，適配雲原生與邊緣場景對輕量、確定性系統之需求。
```

### commit-msg (artifact)

**Normal:**
```
'''commit
Add connection pooling to eventd to eliminate per-event DB connections

Previously, each event append would establish a new PostgreSQL connection, leading to resource exhaustion and scalability limits under high throughput. This change integrates a connection pooling mechanism that reuses existing connections to the database. Connection pools maintain a set of idle connections that can b
```

**Wenyan-ultra:**
```
eventd: Add connection pooling to eliminate per-event DB connection overhead

Prior to this change, eventd opened a new database connection for each event write operation. This caused significant overhead and resource contention in high-throughput environments.

This update implements connection pooling for the eventd daemon, enabling reuse of database connections across multiple write operations.
```

### pr-desc (artifact)

**Normal:**
```
This PR fixes a null pointer dereference vulnerability in the Vaked parser that occurs when parsing input ending immediately after a capability block opening brace (`{`). The issue is resolved by adding a bounds check to validate the input length before accessing the next token, preventing unintended memory access. A test case is included to verify correct handling of truncated capability blocks.
```

**Wenyan-ultra:**
```
Fixes null pointer dereference in Vaked parser when input terminates after capability block opening brace.
Adds EOF check during brace parsing to safely handle truncated inputs.
Prevents segmentation fault and improves parser robustness for edge cases.
```
