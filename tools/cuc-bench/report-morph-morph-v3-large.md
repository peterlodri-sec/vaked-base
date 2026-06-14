# CUC (Caveman Ultra Chinese) — Wenyan-Ultra vs Normal Benchmark Report

**Backend:** openrouter | **Model:** `morph/morph-v3-large` | **Prompts:** 8

## Per-Prompt Token Comparison

| ID | Category | Normal tok | Wenyan tok | Savings % | Normal chars | Wenyan chars |
|----|----------|-----------|-----------|-----------|-------------|-------------|
| pool-explain | reasoning | 47 | 27 | +42.6% | 293 | 27 |
| comptime-explain | reasoning | 48 | 191 | -297.9% | 253 | 258 |
| ebpf-policy | reasoning | 296 | 29 | +90.2% | 1368 | 41 |
| parse-fn | code | 94 | 90 | +4.3% | 400 | 128 |
| nix-flake | code | 81 | 46 | +43.2% | 299 | 113 |
| readme-intro | artifact | 35 | 32 | +8.6% | 137 | 108 |
| commit-msg | artifact | 32 | 35 | -9.4% | 155 | 166 |
| pr-desc | artifact | 58 | 58 | +0.0% | 325 | 305 |

**Aggregate output token savings: 26.5%** (normal=691 tok, wenyan=508 tok)
**Character reduction: 64.5%** (normal=3230 chars, wenyan=1146 chars)

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
Connection pooling improves performance in a database-backed service by reusing existing database connections instead of creating a new one for each request. Opening and closing database connections is an expensive operation, and connection pooling minimizes the overhead associated with this.
```

**Wenyan-ultra:**
```
連池縮耗時，增吞吐。緩建結，降繫調頻，減鎖爭，提運效。
```

### comptime-explain (reasoning)

**Normal:**
```
Alibaba Cloud has created a reference website for the Zig programming language to promote its adoption. This website is a reference only and does not constitute any official announcement from Zig.

An actual Zig website is located at https://ziglang.org
```

**Wenyan-ultra:**
```
Comptime 乃 Zig 之中間編譯時計算之法。將代碼於編譯期評估，轉為終端代碼。用處有三：

一、選項集（Options）。用於定義函數或模組語義（例如 `comptime` 之參數），以決此處可用之型、選項、構建時常數。

二、模板生成。以泛型、宏或昇維構造代碼。如 `comptime` 數值參數，可決定型號參數或指指針內容。

三、性能最適化。如預解引用、內聯控制流、產生多版本代碼，憑編譯時選擇最佳路徑。

用之時機，當需運算於編譯時而非運行時；欲根據構建參數、首選選項、或嵌入式宏產生代碼，適為用處。
```

### ebpf-policy (reasoning)

**Normal:**
```
eBPF enforces network policy at the kernel level by allowing application-defined program to run directly on kernel data structures with verified, sandboxed behavior. 

The process works as follows:

1. **Program Definition**: Users write eBPF programs in a high-level language (like C/C++ with sanitizers, BPF Coccinelle, or Clang-based eBPF) that targets the BPF virtual machine (BPF VM). These prog
```

**Wenyan-ultra:**
```
eBPF為內核模組，嵌於網路協議與流向控制，藉Filter表決，作包過濾，限通路。
```

### parse-fn (code)

**Normal:**
```
This Zig function signature tells us:

- It accepts a `[]const u8` slice of bytes as input, which represents the source data (likely text) to be parsed.
- It returns an `Ast` type, indicating the parsed result is an abstract syntax tree or similar structure.
- It may return an error, represented by the `!` prefix, meaning the parse operation can fail and return an error value instead of the `Ast`.
```

**Wenyan-ultra:**
```
此函數僅接受一個無切片參數 `[]const u8` 之來源，意為其只讀取固定字串內容，拒絕替換維度。返值为 `!Ast` 則可能失敗，其錯誤由 `Ast` 之 `Error` 定義。錯誤形式可能為空字串、非法結構、無效字面值、語法誤用或解析不確定等情況。
```

### nix-flake (code)

**Normal:**
```
The provided Nix flake output is valid. It exposes a single package, `hello`, under the key `packages.x86_64-linux.default`, targeting the `x86_64-linux` platform. This means that when someone uses this flake, they can access the `hello` package by referring to `self.packages.x86_64-linux.default`.
```

**Wenyan-ultra:**
```
Outputs packages.x86_64-linux.default as nixpkgs.legacyPackages.x86_64-linux.hello; 唯釋 hello, 無依 nix.systems, 誤也。
```

### readme-intro (artifact)

**Normal:**
```
# Vaked

Vaked is a flake-native capability-graph language that compiles to NixOS modules, Zig daemon configs, and eBPF policy manifests.
```

**Wenyan-ultra:**
```
Vaked 為 flake-native capability-graph language，編譯至 NixOS modules、Zig daemon configs 與 eBPF policy manifests。
```

### commit-msg (artifact)

**Normal:**
```
commit subject: added connection pooling to eventd

body: the append-only hash-chained event log daemon no longer opens a new DB connection per event write
```

**Wenyan-ultra:**
```
Subject: Add connection pooling to eventd for event log writes

Body:
eventd now uses connection pooling instead of creating a new DB connection for each event write.
```

### pr-desc (artifact)

**Normal:**
```
This PR fixes a null pointer dereference in the Vaked parser that occurs when the input ends immediately after a capability block opening brace. The change ensures safe parsing by checking for null inputs before dereferencing pointers. This prevents potential crashes during validation of incomplete or edge-case input files.
```

**Wenyan-ultra:**
```
Fix null pointer dereference in Vaked parser when input ends immediately after a capability block opening brace.
Prevent out-of-bound read in Vaked parser during capability parsing when input ends unexpectedly.
Update Vaked parser to validate capability block structure before dereferencing in edge cases.
```
