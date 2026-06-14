# Caveman Wenyan-Ultra vs Normal — Benchmark Report

**Backend:** openrouter | **Model:** `deepseek/deepseek-r1` | **Prompts:** 8

## Per-Prompt Token Comparison

| ID | Category | Normal tok | Wenyan tok | Savings % | Normal chars | Wenyan chars |
|----|----------|-----------|-----------|-----------|-------------|-------------|
| pool-explain | reasoning | 933 | 122 | +86.9% | 2034 | 141 |
| comptime-explain | reasoning | 2096 | 746 | +64.4% | 4077 | 1030 |
| ebpf-policy | reasoning | 1527 | 242 | +84.2% | 2701 | 367 |
| parse-fn | code | 931 | 1584 | -70.1% | 1737 | 283 |
| nix-flake | code | 856 | 361 | +57.8% | 1493 | 228 |
| readme-intro | artifact | 352 | 163 | +53.7% | 781 | 698 |
| commit-msg | artifact | 1651 | 596 | +63.9% | 1261 | 735 |
| pr-desc | artifact | 168 | 371 | -120.8% | 463 | 336 |

**Aggregate output token savings: 50.8%** (normal=8514 tok, wenyan=4185 tok)
**Character reduction: 73.8%** (normal=14547 chars, wenyan=3818 chars)

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
Connection pooling enhances performance in database-backed services primarily by **reducing connection overhead** and **efficiently managing resources**. Here's why:

1. **Minimized Connection Establishment Costs**  
   Creating a new database connection is expensive, involving:  
   - Network round trips (e.g., TCP handshake, authentication).  
   - Resource allocation (memory, CPU) on both the a
```

**Wenyan-ultra:**
```
连用池效之由：

1. 建连耗→池存复用免频创
2. 并发控→池限数防库过载
3. 时延降→取池连速于新建
4. 资节→TCP握手/SSL复免
5. 错管→池统处断连重试

例：无池则每请求皆经历：
TCP三次握→SSL协商→身份验→库会话建→查执→断连。池存已认证会话，直取复用。
```

### comptime-explain (reasoning)

**Normal:**
```
Zig's **`comptime`** (compile-time) feature allows code to be executed or evaluated **during compilation** instead of runtime. It enables powerful metaprogramming, type introspection, and code generation without a preprocessor or macros. Here's a breakdown:

---

### **Key Concepts**
1. **Compile-Time Execution**:
   - Code marked with `comptime` runs when the program is compiled.
   - Inputs must
```

**Wenyan-ultra:**
```
Zig `comptime` 乃編譯時執行之器，代碼於編譯期運算，非運行時。其用如下：

**核心要義**  
`comptime` 參數/變量 → 值必編譯時確定 → 編譯器直執代碼 → 輸出機器碼/型態  

**典型用境**  
1. **型態參數化** (無模板之痛)  
   '''zig  
   fn Stack(comptime T: type) type {  
       return struct { items: [10]T }; // 編譯時生成特定型態結構  
   }  
   const IntStack = Stack(i32); // 實例化  
   '''

2. **編譯時驗證**  
   '''zig  
   comptime {  
       assert(@sizeOf(usize) == 8, "非64位系統!"); // 編譯時
```

### ebpf-policy (reasoning)

**Normal:**
```
eBPF (extended Berkeley Packet Filter) enforces network policies at the kernel level through programmable hooks in the Linux networking stack. Here's a concise breakdown:

### Key Mechanisms:
1. **Programmable Hooks**  
   eBPF programs attach to kernel networking hooks (e.g., XDP, TC, socket operations). Examples:  
   - **XDP (eXpress Data Path)**: Processes packets at the earliest stage (driver
```

**Wenyan-ultra:**
```
eBPF执网策之要，其法如下：

1. **挂载点**：钩于内核网络栈要处，如XDP（包入时）、TC（流量控层）、socket操作
2. **验证器**：载程序前严查内存安、循环控、指令限，保内核稳
3. **映射表**：用户态←→内核态通共享maps（BPF_MAP_TYPE_HASH等），实时更策规
4. **即时编译**：BPF字节码→本机指令，高效执行无解释开销
5. **事件驱动**：网络包处理路径中触发BPF程序，可：
   - 包过滤（DROP/REDIRECT）
   - 流量统计（更新map计数器）
   - 协议解析（XDP层改包头）
6. **安全沙箱**：程序仅能访受限上下文，不可任意读写内核内存

例效：
网络包至网卡→XDP BPF判源IP→查策略表→非法则DROP，微秒级决，早于分配skb内存。
```

### parse-fn (code)

**Normal:**
```
The function signature `fn parse(src: []const u8) !Ast` in Zig indicates the following:

### 1. **Accepts**  
- A **slice of immutable bytes** (`[]const u8`):  
  - `src` is a read-only byte slice, typically representing a string (e.g., source code).  
  - The slice has a runtime-determined length (`[]`), and its content cannot be modified (`const u8`).  

### 2. **Returns**  
- An **error union**
```

**Wenyan-ultra:**
```
函簽：`fn parse(src: []const u8) !Ast`  
解：  
1. **受參**：`src: []const u8`  
　→ 字節切片（常數），可為 UTF-8 字串或二進數據  
2. **返値**：`!Ast`  
　→ `!` 誤聯 → 故返二途：  
　　- 成：`Ast` 構體（抽象語法樹）  
　　- 敗：`誤`（具體誤型未顯於簽）  
3. **誤集**：  
　→ 未定於簽名，實作隱  
　→ 常例：無效語法、內存竭、越界讀等，視剖析器實作  

簡要：  
　受字節切片 → 返 `Ast` 或 `誤`，誤型待實作定。
```

### nix-flake (code)

**Normal:**
```
The provided Nix flake output is **valid** and exposes the following:

### What it exposes:
1. **A package named `default`**  
   - This is the flake's default package for the `x86_64-linux` system.
   - It resolves to the `hello` package from the `nixpkgs` repository (specifically `nixpkgs.legacyPackages.x86_64-linux.hello`).

2. **Accessibility via standard flake commands**:
   - `nix build .` →
```

**Wenyan-ultra:**
```
答：
驗→合。此flake曝三端：
1. 路徑正：`packages.<system>.default`乃標準出口
2. 包存在：`nixpkgs.legacyPackages`含hello包
   - 若nixpkgs版有之，則`nix build`可構
3. 限系統：僅x86_64-linux有default包，
   他架構需另配（或用flake-utils簡化）

改進議：添`packages.<system>.hello`明指，或跨系統導出。
```

### readme-intro (artifact)

**Normal:**
```
Vaked is a flake-native capability-graph language designed to unify complex system configurations through a declarative, dependency-aware model. It enables developers to define capabilities—such as services, policies, or resources—and their interdependencies as a directed graph, then compiles this graph into production-ready artifacts: NixOS modules for reproducible infrastructure provisioning, Zi
```

**Wenyan-ultra:**
```
'''markdown
# Vaked: Flake-Native Capability-Graph Language

Vaked is a declarative language designed for NixOS ecosystems, compiling to three targets: NixOS modules for system configuration, Zig daemon configurations for efficient service orchestration, and eBPF policy manifests for kernel-level security enforcement. By modeling dependencies as a capability graph within Nix flakes, it enables gra
```

### commit-msg (artifact)

**Normal:**
```
Here's a concise, conventional commit message draft:

**Subject line** (50 characters):  
`Add connection pooling to eventd for database writes`

**Commit body:**  
'''
Previously, eventd (append-only hash-chained event log daemon) opened a new database connection per event write. This caused significant overhead and scalability issues.

Implemented connection pooling to reuse existing database co
```

**Wenyan-ultra:**
```
**Subject:** eventd: add connection pooling for DB writes  
**Body:**  
Previously, eventd opened a new database connection for every event write operation to its append-only hash-chained log. This incurred significant overhead and limited scalability under high load.  

This change introduces a connection pool to reuse existing DB connections. Eventd now acquires connections from the pool for wri
```

### pr-desc (artifact)

**Normal:**
```
Here is a concise 3-sentence pull request description:

---

This fixes a null pointer dereference crash in the Vaked parser when processing inputs ending immediately after a capability block's opening brace (`{`). The issue occurred because the parser attempted to access a non-existent token after encountering an unexpected EOF in this state. The patch adds an explicit EOF check before token dere
```

**Wenyan-ultra:**
```
This PR resolves a null pointer dereference in the Vaked parser triggered when input terminates immediately after a capability block's opening brace (`{`). The fix adds boundary checks during capability block parsing to prevent out-of-bounds token access. Graceful error handling now replaces the crash when encountering this edge case.
```
