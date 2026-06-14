"""Benchmark prompt corpus for CUC (caveman ultra chinese) wenyan-ultra vs normal mode comparison."""

PROMPTS = [
    # --- Reasoning / Explain ---
    {
        "id": "pool-explain",
        "category": "reasoning",
        "text": "Why does connection pooling help performance in a database-backed service?",
        "is_artifact": False,
    },
    {
        "id": "comptime-explain",
        "category": "reasoning",
        "text": "Explain Zig's comptime feature and when you would use it.",
        "is_artifact": False,
    },
    {
        "id": "ebpf-policy",
        "category": "reasoning",
        "text": "How does eBPF enforce network policy at the kernel level?",
        "is_artifact": False,
    },
    # --- Code Analysis ---
    {
        "id": "parse-fn",
        "category": "code",
        "text": "What does this Zig function signature tell you: `fn parse(src: []const u8) !Ast` — what does it accept, what can it return, what errors are possible?",
        "is_artifact": False,
    },
    {
        "id": "nix-flake",
        "category": "code",
        "text": (
            "Review this Nix flake output for correctness:\n"
            "```nix\n"
            "outputs = { self, nixpkgs }: {\n"
            "  packages.x86_64-linux.default = nixpkgs.legacyPackages.x86_64-linux.hello;\n"
            "};\n"
            "```\n"
            "Is this valid? What does it expose?"
        ),
        "is_artifact": False,
    },
    # --- Artifact Production (must be English output) ---
    {
        "id": "readme-intro",
        "category": "artifact",
        "text": (
            "Write a one-paragraph README introduction for a project called Vaked. "
            "Vaked is a flake-native capability-graph language that compiles to NixOS modules, "
            "Zig daemon configs, and eBPF policy manifests."
        ),
        "is_artifact": True,
    },
    {
        "id": "commit-msg",
        "category": "artifact",
        "text": (
            "Draft a git commit message (subject line + body) for this change: "
            "added connection pooling to eventd so that the append-only hash-chained event log "
            "daemon no longer opens a new DB connection per event write."
        ),
        "is_artifact": True,
    },
    {
        "id": "pr-desc",
        "category": "artifact",
        "text": (
            "Write a 3-sentence pull request description for: "
            "fix null pointer dereference in the Vaked parser when the input ends "
            "immediately after a capability block opening brace."
        ),
        "is_artifact": True,
    },
]
