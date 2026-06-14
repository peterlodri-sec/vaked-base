# CUC (Caveman Ultra Chinese) — Wenyan-Ultra vs Normal Benchmark Report

**Backend:** openrouter | **Model:** `meta-llama/llama-3.3-70b-instruct` | **Prompts:** 8

## Per-Prompt Token Comparison

| ID | Category | Normal tok | Wenyan tok | Savings % | Normal chars | Wenyan chars |
|----|----------|-----------|-----------|-----------|-------------|-------------|
| pool-explain | reasoning | 287 | 19 | +93.4% | 1672 | 20 |
| comptime-explain | reasoning | 444 | 78 | +82.4% | 2027 | 99 |
| ebpf-policy | reasoning | 417 | 111 | +73.4% | 1995 | 486 |
| parse-fn | code | 298 | 42 | +85.9% | 1347 | 62 |
| nix-flake | code | 215 | 36 | +83.3% | 776 | 107 |
| readme-intro | artifact | 126 | 101 | +19.8% | 752 | 588 |
| commit-msg | artifact | 69 | 58 | +15.9% | 380 | 343 |
| pr-desc | artifact | 71 | 71 | +0.0% | 385 | 379 |

**Aggregate output token savings: 73.2%** (normal=1927 tok, wenyan=516 tok)
**Character reduction: 77.7%** (normal=9334 chars, wenyan=2084 chars)

## Artifact Gate Accuracy

Artifact prompts in wenyan-ultra mode must contain **no CJK characters** in the response.

| ID | Normal English? | Wenyan English? | Gate |
|----|----------------|-----------------|------|
| readme-intro | yes | yes | ✓ PASS |
| commit-msg | yes | yes | ✓ PASS |
| pr-desc | yes | yes | ✓ PASS |

**Artifact gate: PASS — all artifacts in English**

## Sample Responses (first 400 chars)

### pool-explain (reasoning)

**Normal:**
```
Connection pooling helps performance in a database-backed service by reducing the overhead of creating and closing database connections. Here's why:

1. **Creating a connection is expensive**: Establishing a new database connection involves several steps, such as authentication, allocating resources, and initializing the connection. This process can be time-consuming, especially if the database is
```

**Wenyan-ultra:**
```
連接數→少，創建連接成本→低，性能→佳。
```

### comptime-explain (reasoning)

**Normal:**
```
### Zig's Comptime Feature

Zig's `comptime` feature allows you to evaluate expressions at compile-time. It provides a way to perform computations that do not depend on runtime data during the compilation process.

**What can be evaluated at comptime?**

* Constants and constant expressions
* Enum values
* Type calculations (e.g., calculating the size of a struct)
* Function calls (if all argument
```

**Wenyan-ultra:**
```
`comptime`乃編譯期評估之標誌。用於常數計算、型別推導、MetaData処理。適用於：數組初始值計算、型別參數評估、`enum`值生成。則可減少運行時計算，提升效率。故於性能關鍵代碼中使用。
```

### ebpf-policy (reasoning)

**Normal:**
```
eBPF (extended Berkeley Packet Filter) enforces network policy at the kernel level through the following steps:

1. **Program loading**: eBPF programs are loaded into the kernel, which are small pieces of code written in a specialized language (eBPF bytecode).
2. **Attachment to hooks**: eBPF programs are attached to specific hooks in the kernel's networking stack, such as the `tc` (traffic contro
```

**Wenyan-ultra:**
```
eBPFریب Programmable datapath→Network traffic Tarih	calibration、 Classification、ACTION施行。 Program Load于 kernel、attach于 tc、iptablessfHOOK點。versations_INGRESS、EGRESS Trafford audit Trail babyoker Policies lawmaker traffic Classify extravaganzasshield nutrit quirky Patchost富_SIGNATURE richبال optimizeIntArray>xpathHere's a rewritten response in classical Chinese ultra-compression:

eBPFdatapath→ traf
```

### parse-fn (code)

**Normal:**
```
**Function Signature Breakdown**

The given Zig function signature is:
'''zig
fn parse(src: []const u8) !Ast
'''
Here's what it tells us:

* **Input**: The function accepts a single argument `src` of type `[]const u8`, which is a **slice of immutable bytes**. This means it expects a contiguous sequence of bytes, usually a string or byte array.
* **Output**: The function can return a value of type 
```

**Wenyan-ultra:**
```
`[]const u8` → 字節串. `!` → 錯誤可能. `Ast` → 解析結果. 可以返回 `Ast` 或 錯誤.
```

### nix-flake (code)

**Normal:**
```
The provided Nix flake output is valid. 

It exposes a single output:
- `packages.x86_64-linux.default`: This refers to the `hello` package from the `nixpkgs` repository, specifically the version available on the `x86_64-linux` platform. 

However, it's worth noting that using `legacyPackages` is generally discouraged in favor of using the `pkgs` attribute instead, which points to the `default` pa
```

**Wenyan-ultra:**
```
nixpkgs.legacyPackages → nixpkgs.pkgs. 
自之NELF → Nix Expression Language Format, 
其exposes package之default。
```

### readme-intro (artifact)

**Normal:**
```
Welcome to Vaked, a revolutionary capability-graph language designed to simplify and streamline system configuration and policy management. As a flake-native language, Vaked allows developers to define complex relationships between system components in a concise and expressive way. With its unique compilation capabilities, Vaked can generate a wide range of outputs, including NixOS modules for dec
```

**Wenyan-ultra:**
```
Vaked is a cutting-edge, flake-native capability-graph language designed to streamline system configuration and policy management. By compiling to multiple targets, including NixOS modules, Zig daemon configurations, and eBPF policy manifests, Vaked provides a unified and expressive framework for defining and enforcing system capabilities. This multifaceted approach enables developers to author co
```

### commit-msg (artifact)

**Normal:**
```
Here's a draft commit message:

Subject: Implement connection pooling for eventd DB connections

Body: Added connection pooling to eventd to improve performance by reusing existing DB connections for event writes, rather than opening a new connection for each event. This reduces the overhead of frequent DB connections and improves the overall efficiency of the event log daemon.
```

**Wenyan-ultra:**
```
Subject: Implement connection pooling in eventd for efficient database interactions

The eventd daemon now utilizes connection pooling to manage its database connections, eliminating the need to establish a new connection for each event write to the append-only hash-chained event log, thus enhancing overall performance and reducing overhead.
```

### pr-desc (artifact)

**Normal:**
```
This pull request addresses a null pointer dereference issue in the Vaked parser that occurs when the input ends abruptly after opening a capability block with a brace. The fix ensures that the parser correctly handles this edge case and prevents the null pointer dereference. By applying this change, the Vaked parser will become more robust and resilient to unexpected input formats.
```

**Wenyan-ultra:**
```
This pull request addresses a null pointer dereference issue in the Vaked parser. The bug occurs when the input stream ends immediately after a capability block opening brace, causing the parser to dereference a null pointer. The changes in this pull request fix this issue, ensuring the Vaked parser correctly handles such edge cases and preventing the null pointer dereference.
```
