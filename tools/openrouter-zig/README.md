# openrouter-zig — OpenRouter Agent SDK in Zig

Zig 0.16 native implementation. 1:1 API with `@vaked/openrouter-ts`.
Once tested and confirmed, supersedes the TypeScript version.

## Build

```bash
zig build                # → zig-out/bin/orcli
zig build test           # run tests
zig build run -- "prompt"
```

## Usage

```bash
# CLI
./zig-out/bin/orcli "What is a capability graph?"
./zig-out/bin/orcli -m claude "Write a Zig 0.16 HTTP server"
./zig-out/bin/orcli -f main.zig -p "Review for bugs"
./zig-out/bin/orcli -l    # list models
./zig-out/bin/orcli --status  # budget
```

## API (library)

```zig
const openrouter = @import("openrouter");

var agent = try openrouter.VakedAgent.init(allocator, io, .{});
defer agent.deinit();

const answer = try agent.ask("What is Zig?");
const code = try agent.code("Write a sorting function");
const review = try agent.review(code);
```

## Par with TypeScript

| TypeScript | Zig |
|-----------|-----|
| `createVakedAgent()` | `VakedAgent.init(allocator, io, .{})` |
| `agent.ask(prompt)` | `agent.ask(prompt)` |
| `agent.code(prompt)` | `agent.code(prompt)` |
| `agent.review(prompt)` | `agent.review(prompt)` |
| Context7 | `context7.queryDocs(io, allocator, name, query)` |
| Budget | `budget.readBudget(io, allocator)` |

## Genesis

```
GENESIS_SEAL: 7c242080
```
