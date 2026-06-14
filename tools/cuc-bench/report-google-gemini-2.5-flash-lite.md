# CUC (Caveman Ultra Chinese) — Wenyan-Ultra vs Normal Benchmark Report

**Backend:** openrouter | **Model:** `google/gemini-2.5-flash-lite` | **Prompts:** 8

## Per-Prompt Token Comparison

| ID | Category | Normal tok | Wenyan tok | Savings % | Normal chars | Wenyan chars |
|----|----------|-----------|-----------|-----------|-------------|-------------|
| pool-explain | reasoning | 503 | 132 | +73.8% | 2621 | 351 |
| comptime-explain | reasoning | 1347 | 598 | +55.6% | 5610 | 1114 |
| ebpf-policy | reasoning | 774 | 215 | +72.2% | 3548 | 451 |
| parse-fn | code | 512 | 28 | +94.5% | 2105 | 77 |
| nix-flake | code | 106 | 39 | +63.2% | 375 | 67 |
| readme-intro | artifact | 82 | 30 | +63.4% | 497 | 53 |
| commit-msg | artifact | 87 | 69 | +20.7% | 518 | 406 |
| pr-desc | artifact | 58 | 57 | +1.7% | 303 | 94 |

**Aggregate output token savings: 66.3%** (normal=3469 tok, wenyan=1168 tok)
**Character reduction: 83.2%** (normal=15577 chars, wenyan=2613 chars)

## Artifact Gate Accuracy

Artifact prompts in wenyan-ultra mode must contain **no CJK characters** in the response.

| ID | Normal English? | Wenyan English? | Gate |
|----|----------------|-----------------|------|
| readme-intro | yes | NO — CJK found | ✗ FAIL |
| commit-msg | yes | yes | ✓ PASS |
| pr-desc | yes | NO — CJK found | ✗ FAIL |

**Artifact gate: FAIL — CJK found in artifact**

## Sample Responses (first 400 chars)

### pool-explain (reasoning)

**Normal:**
```
Connection pooling significantly boosts performance in database-backed services by addressing the overhead associated with establishing database connections. Here's a breakdown of why:

*   **Reduces Connection Establishment Overhead:**
    *   **Costly Process:** Creating a new database connection is a resource-intensive operation. It involves network round trips, authentication, authorization, a
```

**Wenyan-ultra:**
```
連線，耗時。

池，預先繋。

需，則取。

免，新啓。

故，速。

簡言之：

*   **建立連結耗時 (Connection establishment is time-consuming)。**
*   **連線池預先建立好連結 (Connection pooling pre-establishes connections)。**
*   **需要時，直接取用 (When needed, they are directly retrieved)。**
*   **避免每次都重新建立連結 (Avoids re-establishing connections each time)。**
*   **因此，提升效能 (Therefore, performance improves)。**
```

### comptime-explain (reasoning)

**Normal:**
```
Zig's `comptime` feature allows you to execute code during compile time rather than at runtime. This means that computations, type constructions, and even conditional logic can be determined and resolved before your program ever starts executing.

Here's a breakdown of `comptime` and its use cases:

### How `comptime` Works

When you decorate a function, variable, or block of code with `comptime`,
```

**Wenyan-ultra:**
```
Zig ō comptime (編譯時) 乃編譯腳本，其時執行。

**功用**：

1.  **型別生成 (Type Generation)**：
    *   `comptime` 函數可返型別。
    *   例：`comptime func gen_pair(T: type) type { return struct { a: T, b: T }; }`
    *   此可創客製化結構、列舉等，無需手寫。

2.  **模板化 (Metaprogramming)**：
    *   `comptime if`，`comptime for` 供條件編譯、循環。
    *   例：`comptime var arr: [N]i32 = ...;` (N 須為編譯時常量)
    *   可依據編譯時參數，生成不同代碼。

3.  **編譯時計算 (Compile-time c
```

### ebpf-policy (reasoning)

**Normal:**
```
eBPF (extended Berkeley Packet Filter) enforces network policy at the kernel level by using **filtered eBPF programs attached to network hooks within the Linux kernel**. These hooks intercept network packets at various stages of their journey, allowing eBPF programs to inspect, modify, or drop them based on predefined policy rules.

Here's a breakdown of how it works:

1.  **eBPF Programs:** These
```

**Wenyan-ultra:**
```
eBPF 網策略，內核級。

eBPF 鉤掛點 (hook points)，網絡棧。
eBPF 程式 (programs)，加載，內核。
程式，數據包 (packets)。
訪問 數據包元數據 (metadata)，如源/目標 IP/端口、協議。
應用 規則 (rules)，策略定義。
允許 (allow) / 拒絕 (drop) 數據包。

鍵：
- 鉤掛點 (hook points): `TC` (Traffic Control), `XDP` (eXpress Data Path)。
- 數據結構 (data structures): `struct __sk_buff`, `struct bpf_sock_addr`。
- 函數 (functions): `bpf_clone_redirect`, `bpf_redirect`, `bpf_skb_flags`。
- 映射 (map
```

### parse-fn (code)

**Normal:**
```
Let's break down the Zig function signature `fn parse(src: []const u8) !Ast`:

**What it accepts:**

*   `src: []const u8`:
    *   `src` is the name of the parameter.
    *   `[]const u8` signifies a **slice of constant unsigned 8-bit integers**. In Zig, this is commonly used to represent a read-only view of a byte array, which is effectively a string or raw binary data.
    *   So, the function 
```

**Wenyan-ultra:**
```
src: []const u8 → Input.

!Ast → Success: Ast OR Error.

Error? `error{...}`.
```

### nix-flake (code)

**Normal:**
```
This Nix flake is **valid** and **correctly written**.

It **exposes** a single package named `default` under the `packages.x86_64-linux` attribute. This package is `hello` from the `nixpkgs` collection, specifically for the `x86_64-linux` architecture.

When you enter this flake (e.g., with `nix develop`), you will have access to the `hello` executable defined by nixpkgs.
```

**Wenyan-ultra:**
```
此為有效 Nix flake。

揭露：
`default` 套件：`x86_64-linux` 平台。
內容：`hello` 程式。
```

### readme-intro (artifact)

**Normal:**
```
This repository introduces Vaked, a powerful, flake-native capability-graph language designed for declarative system configuration. Vaked allows you to define system capabilities and their relationships, which are then compiled into robust NixOS modules, efficient Zig daemon configurations, and verifiable eBPF policy manifests. This approach simplifies complex system management by providing a unif
```

**Wenyan-ultra:**
```
Vaked：蓋絡語，原生於 Nix，編譯至 NixOS 模塊、Zig daemon 配置、eBPF 策略。
```

### commit-msg (artifact)

**Normal:**
```
feat: Implement connection pooling for eventd

This commit introduces connection pooling to the eventd daemon. Previously, a new database connection was opened for every event write, leading to performance degradation and resource exhaustion.

With connection pooling, a set of database connections is maintained and reused, significantly reducing the overhead associated with establishing and tearin
```

**Wenyan-ultra:**
```
feat: Implement connection pooling for eventd writes

Optimizes eventd by introducing connection pooling for database writes. Previously, eventd established a new database connection for each event appended to the append-only hash-chained event log. This change mitigates the overhead associated with repeated connection establishment and teardown, leading to improved performance and resource utiliz
```

### pr-desc (artifact)

**Normal:**
```
This PR addresses a null pointer dereference in the Vaked parser. The issue occurs when the input string ends immediately after a capability block's opening brace, leading to an attempt to dereference a null pointer. The fix ensures that the parser handles this edge case gracefully and avoids crashing.
```

**Wenyan-ultra:**
```
解決 Vaked 解析器在輸入於 capability 塊左大括號後即結束時，發生空指針解引用問題。
輸入即 EOF，應返回錯誤而非崩潰。
修改邏輯，確保 EOF 情況下解析器能健壯處理。
```
