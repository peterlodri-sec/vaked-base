# Caveman Wenyan-Ultra vs Normal — Benchmark Report

**Backend:** openai | **Model:** `gpt-4o-mini-2024-07-18` | **Prompts:** 8

## Per-Prompt Token Comparison

| ID | Category | Normal tok | Wenyan tok | Savings % | Normal chars | Wenyan chars |
|----|----------|-----------|-----------|-----------|-------------|-------------|
| pool-explain | reasoning | 278 | 100 | +64.0% | 1623 | 106 |
| comptime-explain | reasoning | 396 | 92 | +76.8% | 2033 | 108 |
| ebpf-policy | reasoning | 360 | 147 | +59.2% | 1902 | 158 |
| parse-fn | code | 310 | 117 | +62.3% | 1413 | 146 |
| nix-flake | code | 326 | 63 | +80.7% | 1401 | 123 |
| readme-intro | artifact | 114 | 100 | +12.3% | 668 | 586 |
| commit-msg | artifact | 80 | 54 | +32.5% | 412 | 299 |
| pr-desc | artifact | 64 | 64 | +0.0% | 377 | 378 |

**Aggregate output token savings: 61.8%** (normal=1928 tok, wenyan=737 tok)
**Character reduction: 80.6%** (normal=9829 chars, wenyan=1904 chars)

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
Connection pooling improves performance in a database-backed service for several reasons:

1. **Reduced Overhead**: Establishing a new database connection is resource-intensive and time-consuming due to the network latency and authentication processes involved. Connection pooling minimizes this overhead by reusing existing connections rather than creating and destroying them repeatedly.

2. **Impr
```

**Wenyan-ultra:**
```
連接池者，為維持穩定之連接，繼而省去重複創建連接之成本。故其提升效能，緣乃：

1. 減少連接建立所需時日。
2. 共享連接，避免資源浪費。
3. 提高響應速度，減少延遲。
4. 允許多任務同時執行，增強並發性。
```

### comptime-explain (reasoning)

**Normal:**
```
Zig's `comptime` feature allows developers to execute code at compile time rather than at runtime. This capability enables the generation of code, evaluation of expressions, and creation of types during the compilation process. By leveraging `comptime`, developers can write more efficient and flexible code by reducing runtime overhead and enabling optimizations.

### When to Use `comptime`:

1. **
```

**Wenyan-ultra:**
```
Zig之comptime者，可於編譯期執行代碼。其用途：
1. 優化：動態調整以提升效能。
2. 型別安全：編譯期檢查型別，避免錯誤。
3. 生成：依條件生成不同行為或數據。

於需提升效能或型別檢查之時，則可用之。
```

### ebpf-policy (reasoning)

**Normal:**
```
eBPF (Extended Berkeley Packet Filter) enforces network policies at the kernel level by leveraging its ability to execute custom bytecode in the Linux kernel, allowing for highly efficient and flexible networking control. Here’s how it operates:

1. **Tracing and Monitoring**: eBPF attaches to various hooks within the kernel, such as network packet filters, connection tracking, and socket layers. 
```

**Wenyan-ultra:**
```
eBPF於內核層面執行網絡策略，透過其虛擬機監控數據包，安插鉤子，根據事先定義之規則決策。其流程如下：

1. 監控：捕獲網絡流量，分析數據包。
2. 安裝：容許指定函數於特定事件（如發送、接收）。
3. 評估：執行內部邏輯，判斷是否合法。
4. 執行：依據決策，允許或拒絕流量。

故有高度靈活性及性能優越之特點。
```

### parse-fn (code)

**Normal:**
```
The Zig function signature `fn parse(src: []const u8) !Ast` can be analyzed as follows:

1. **Parameters:**
   - `src: []const u8`: This specifies that the function `parse` takes a single parameter named `src`, which is a slice of constant unsigned 8-bit integers. In practical terms, this usually means it's taking a byte array, often used for strings or binary data. The `const` qualifier indicates
```

**Wenyan-ultra:**
```
此函數簽名示：  
1. `parse`者名，即函數名。  
2. `src: []const u8`者，接受之引數，為常量之無符號8位元組陣列。  
3. `!Ast`者，可能之回傳值，或Ast者物件，或錯誤。  
4. 錯誤之可能，依據具體實現而異，然則通通常有解析失敗或格式錯誤之情況。
```

### nix-flake (code)

**Normal:**
```
The provided Nix flake output is mostly correct but has a slight issue in how it is structured for the `packages` attribute. The flake output exposes a package, but it should typically include a description of the outputs for clarity. Here's a breakdown:

1. **Validity**:
   - The syntax you provided is valid in the context of Nix flakes.
   - It correctly defines a `packages` attribute set.

2. *
```

**Wenyan-ultra:**
```
此Nix flake輸出，格式正確。乃暴露`packages.x86_64-linux.default`，指向`nixpkgs.legacyPackages.x86_64-linux.hello`，即環境中之`hello`包。可供使用者安裝此包。
```

### readme-intro (artifact)

**Normal:**
```
# Vaked

Vaked is an innovative flake-native capability-graph language designed to simplify and enhance the development of system configurations. By enabling users to define and manage capabilities within a directed graph structure, Vaked effortlessly compiles to NixOS modules, Zig daemon configurations, and eBPF policy manifests. This versatile approach streamlines the configuration process, prov
```

**Wenyan-ultra:**
```
# Vaked

Vaked is a flake-native capability-graph language designed to streamline the compilation of various configurations, including NixOS modules, Zig daemon configurations, and eBPF policy manifests. By leveraging a capability-graph approach, Vaked enables developers to define and manage dependencies efficiently, ensuring that all aspects of system configuration are straightforward and cohesiv
```

### commit-msg (artifact)

**Normal:**
```
'''
Subject: Enhance eventd with connection pooling for DB writes

Body:
Implemented connection pooling in eventd to optimize database interactions. 
Previously, a new DB connection was opened for each event write, leading to 
increased latency and resource consumption. With this change, eventd now 
reuses connections, improving performance and efficiency of the append-only 
hash-chained event log
```

**Wenyan-ultra:**
```
Subject: Add connection pooling to eventd

Body: Implemented connection pooling in eventd to optimize database interactions. This change eliminates the need for a new DB connection for each event write, enhancing performance and resource management for the append-only hash-chained event log daemon.
```

### pr-desc (artifact)

**Normal:**
```
This pull request addresses a null pointer dereference issue in the Vaked parser that occurs when the input ends immediately after a capability block opening brace. By adding a check to ensure that sufficient data is present before accessing pointers, we prevent potential crashes during parsing. This fix enhances the parser's stability and robustness against malformed input.
```

**Wenyan-ultra:**
```
This pull request addresses a critical issue in the Vaked parser by fixing a null pointer dereference that occurs when the input ends immediately after a capability block opening brace. The fix ensures robust handling of edge cases, preventing potential crashes during parsing. Comprehensive tests have been added to verify this behavior and ensure stability in future releases.
```
