# Caveman Wenyan-Ultra vs Normal — Benchmark Report

**Backend:** openrouter | **Model:** `minimax/minimax-m3-20260531` | **Prompts:** 8

## Per-Prompt Token Comparison

| ID | Category | Normal tok | Wenyan tok | Savings % | Normal chars | Wenyan chars |
|----|----------|-----------|-----------|-----------|-------------|-------------|
| pool-explain | reasoning | 915 | 335 | +63.4% | 2508 | 65 |
| comptime-explain | reasoning | 1015 | 585 | +42.4% | 3885 | 847 |
| ebpf-policy | reasoning | 1133 | 509 | +55.1% | 4545 | 602 |
| parse-fn | code | 965 | 595 | +38.3% | 2346 | 563 |
| nix-flake | code | 1468 | 877 | +40.3% | 1596 | 830 |
| readme-intro | artifact | 619 | 240 | +61.2% | 1013 | 940 |
| commit-msg | artifact | 517 | 184 | +64.4% | 1091 | 899 |
| pr-desc | artifact | 115 | 126 | -9.6% | 479 | 410 |

**Aggregate output token savings: 48.9%** (normal=6747 tok, wenyan=3451 tok)
**Character reduction: 70.5%** (normal=17463 chars, wenyan=5156 chars)

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
Connection pooling improves performance primarily by **amortizing the cost of connection setup** and **bounding resource usage**. The key reasons:

**1. Connection setup is expensive**
Opening a new database connection involves multiple costly steps:
- **Network handshake**: TCP three-way handshake, plus TLS negotiation if encrypted (several round-trips).
- **Database-side initialization**: Authen
```

**Wenyan-ultra:**
```
建連貴（TCP握手、認證、TLS）→ 每請求重建則延遲高、資源耗。
池化復用舊連，攤薄開銷，限並發，防雪崩。
故吞吐增、尾延遲降。
```

### comptime-explain (reasoning)

**Normal:**
```
# Zig's `comptime` Feature

`comptime` is one of Zig's most powerful and distinctive features. It allows you to execute code at **compile time** rather than at runtime, treating types and values as first-class citizens that can be manipulated by ordinary Zig code.

## Core Idea

In Zig, almost any expression can be evaluated at compile time. The compiler runs your Zig code (a subset of it) during 
```

**Wenyan-ultra:**
```
Zig `comptime` 乃編譯期求值機制也。

**核心：**
- `comptime` 標記之變量/參數/表達式，編譯時必求值
- 所有類型於編譯期可作值傳遞（type-as-value）
- 未標 `comptime` 者亦隱式 comptime 化（如 `++"a"` 自動生成展開代碼）

**機制：**
- 編譯期可執行任意函數（`fn` 默認 comptime-eligible）
- `inline` 暗示將調用展開至調用點
- 與 runtime 代碼同源，無需另寫模板語言

**用時機：**

1. **泛型** → `fn List(comptime T: type) ...` 取代 C++ 模板
2. **配置生成** → 根據 build flag 生成不同代碼路徑
3. **常數計算** → 斐波那契表、CRC 查表、位元掩碼於編譯期算畢
4. **DSL / 
```

### ebpf-policy (reasoning)

**Normal:**
```
# How eBPF Enforces Network Policy at the Kernel Level

eBPF (extended Berkeley Packet Filter) enables high-performance, programmable network policy enforcement by running sandboxed bytecode inside the Linux kernel. Here is the core mechanism:

## 1. Hook Points into the Kernel Networking Path

eBPF programs attach at strategic points in the kernel's network stack rather than running in user space
```

**Wenyan-ultra:**
```
eBPF駐核執行，以鉤點介入協議棧。

**鉤點層級**

- XDP（驅動前，最早點，零拷貝）
- TC ingress/egress（IP棧前後）
- cgroup/connect4/6（socket建立時）
- sock_ops（連接生命週期）
- sk_msg（socket資料流）

**執行路徑**

封包入境→鉤點觸發→載入eBPF bytecode→verifier預驗→JIT編譯→BPF map查策略→返回碼處置（PASS/DROP/REDIRECT/TX）。

**策略載體**

- LPM trie map：CIDR匹配
- Hash map：endpoint身份/標籤
- Array/PerCPU：統計計數
- Ringbuf/PerfEvent：事件推送userspace

**強制手段**

return XDP_DROP／TC_ACT_SHOT→內核於鉤點處丟棄
```

### parse-fn (code)

**Normal:**
```
# Breakdown of `fn parse(src: []const u8) !Ast`

## Parameter
'''zig
src: []const u8
'''
This is a **byte slice** — a pointer + length pair pointing to a sequence of `u8` (bytes). The `const` applies to the *elements*, so:
- You can read the bytes
- You **cannot** modify them through this slice
- The slice itself (the pointer/length) is still a value copy on the stack

In practice, this is how Zig
```

**Wenyan-ultra:**
```
'''
fn parse(src: []const u8) !Ast
'''

**解：**

- **入参** `src: []const u8`
  - 胖指针 = `{ptr, len}`，指向只读字节序列
  - 形参按值传（slice 本即句柄），调者持其命
  - 实质：不可变字符串/字节流

- **返值** `!Ast`
  - 错误联合（error union）之简写
  - 等价 `error{...}!Ast`
  - 非 `Ast` 即 `error`——二者必居其一
  - 调用须 `try` / `catch` / `if` 解之

- **错误集**
  - 签名本身不列错种
  - `!` 触发**推断错误集**（inferred error set）——编译期由函数体所 `return error.X` 聚合而定
  - 跨传播需显式 `error{...
```

### nix-flake (code)

**Normal:**
```
# Flake Review

**Yes, this is valid.** It's a minimal but correct Nix flake output.

## What it exposes

- A single package named `default` for the `x86_64-linux` system
- That package is the `hello` program from nixpkgs (prints "Hello, world!")
- Users can run `nix build` or `nix run` against this flake to build/run it

## Things to note

**1. System-specific only.** It's hardcoded to `x86_64-li
```

**Wenyan-ultra:**
```
可。語法合 flake output schema。

曝：`packages.x86_64-linux.default` → `nixpkgs.legacyPackages.x86_64-linux.hello`。

用：
'''
nix build .#default   # 或 .#hello
nix run .#default
'''

## 評

**合** — 函簽 `{ self, nixpkgs }` 合法，attrs 路徑 `packages.<system>.default` 遵 schema。

**闕**：
- 僅 `x86_64-linux`。他系（`aarch64-linux`、`x86_64-darwin` 等）構建則：`error: a 'x86_64-linux' is not a valid system`
- 無 `apps` / `devShells
```

### readme-intro (artifact)

**Normal:**
```
Vaked is a flake-native capability-graph language for declaring the shape of a complete Linux system in a single, auditable source of truth. Rather than scattering authorization decisions across ad-hoc shell scripts, systemd units, and hand-written policy files, Vaked models what a service, user, or workload is allowed to do — and what it depends on — as a typed graph of capabilities and edges, so
```

**Wenyan-ultra:**
```
Vaked is a flake-native capability-graph language that compiles to NixOS modules, Zig daemon configs, and eBPF policy manifests. It treats every dependency, socket, mount, and syscall grant as a typed capability node, and lets you wire them into a single declarative graph that your `flake.nix` can consume directly. The compiler emits three concrete artifacts in one pass: a NixOS module tree for sy
```

### commit-msg (artifact)

**Normal:**
```
**Suggested commit message:**

'''
eventd: pool database connections across event writes

eventd previously opened a fresh database connection for every event
it appended to the hash-chained log. For a daemon whose entire job is
to durably record events, that meant the cost of a full TCP/TLS/auth
handshake (or local socket setup) was paid on every single write,
dominating latency and putting unnec
```

**Wenyan-ultra:**
```
Subject: eventd: add connection pooling to amortize DB connection setup

Body:
Per-event connection open is the dominant cost in the write path. Each
write paid full TCP/TLS + auth + handshake latency before the INSERT,
which dominated tail latency under bursty ingest and burned file
descriptors under load.

Replace the per-write connect with a pooled client. The pool maintains a
bounded set of li
```

### pr-desc (artifact)

**Normal:**
```
This PR fixes a null pointer dereference in the Vaked parser that occurs when input ends immediately after a capability block's opening brace, leaving an incomplete nested element reference. The parser previously assumed a valid element would follow the brace and attempted to dereference it without bounds checking, causing a crash on well-formed but truncated input. A guard clause has been added t
```

**Wenyan-ultra:**
```
This pull request fixes a null pointer dereference in the Vaked parser that occurs when input ends immediately after a capability block opening brace. Previously, the parser failed to validate the presence of content following the brace, causing a crash on valid-but-truncated input. The fix adds a length check before accessing the parser's internal buffer, ensuring graceful error handling in this 
```
