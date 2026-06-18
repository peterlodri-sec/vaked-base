#!/usr/bin/env python3
"""Library Digest — RAG-powered ~10 min read generator.

1. Pick topic (from env or auto-select from TOPICS list)
2. Search 206-document RAG index for relevant sources
3. Synthesize via Claude Opus 4.8 (OpenRouter)
4. Create GitHub issue labeled 'library-digest'

GENESIS_SEAL: 7c242080
"""
import json, os, random, ssl, urllib.request

INDEX_PATH = "chat-gateway/knowledge/index.json"
GENESIS = "7c242080"
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GH_TOKEN = os.environ.get("GH_PERSONAL_TOKEN", "")

TOPICS = [
    "CPU microarchitecture and performance tuning for deterministic systems",
    "eBPF kernel enforcement — from BPF to capability-based security",
    "Formal verification of operating systems — the seL4 approach",
    "Anti-entropy gossip protocols — from Xerox PARC to Synapse",
    "Nix and declarative deployment for agentic infrastructure",
    "Zig 0.16 systems programming — zero-cost abstractions and comptime",
    "Capability-graph languages — bridging ERights and Vaked",
    "Merkle trees and append-only ledgers",
    "WebAssembly sandboxing for secure agent execution",
    "Memory allocators and arena patterns for high-performance systems",
]


def load_docs():
    if not os.path.isfile(INDEX_PATH): return []
    with open(INDEX_PATH) as f:
        return json.load(f).get("documents", [])


def pick_topic():
    return os.environ.get("TOPIC", "") or random.choice(TOPICS)


def search(docs, topic, n=5):
    results = []
    words = topic.lower().split()
    for d in docs:
        score = sum(
            (3 if w in d.get("title","").lower() else 0) +
            (2 if w in d.get("path","").lower() else 0) +
            (1 if w in d.get("preview","").lower() else 0)
            for w in words
        )
        if score > 0: results.append((score, d))
    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:n]]


def generate(topic, docs):
    if not OR_KEY:
        return f"# {topic}\n\n*No API key — raw sources below.*\n\n" + "\n\n".join(
            f"## {d['title']}\n{d['preview'][:500]}" for d in docs
        )

    ctx = "\n\n".join(f"### {d['title']}\n{d['preview'][:600]}" for d in docs[:5])
    prompt = f"""Write a ~1200 word digest on: {topic}

CONTEXT:
{ctx}

Write engaging technical prose. ~10 min read. Cite sources inline [1], [2].
End with Further Reading listing the referenced works.
Tone: colleague explaining over coffee. Genesis seal: {GENESIS[:8]}."""

    payload = json.dumps({
        "model": "anthropic/claude-opus-4.8-fast",
        "messages": [
            {"role": "system", "content": "Senior systems engineer and technical writer. Clear, engaging, precise."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 2500,
    }).encode()

    ctx_ssl = ssl.create_default_context()
    ctx_ssl.check_hostname = False
    ctx_ssl.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {OR_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx_ssl) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"]
    except Exception as e:
        return f"# {topic}\n\n*Generation failed: {e}*\n\n{ctx}"


def create_issue(title, body):
    if not GH_TOKEN:
        print("No GH token — preview:")
        print(body[:800])
        return

    payload = json.dumps({"title": title, "body": body, "labels": ["library-digest"]}).encode()
    ctx_ssl = ssl.create_default_context()
    ctx_ssl.check_hostname = False
    ctx_ssl.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        "https://api.github.com/repos/peterlodri-sec/vaked-base/issues",
        data=payload,
        headers={
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx_ssl) as resp:
            issue = json.loads(resp.read())
            print(f"Issue #{issue['number']}: {issue['html_url']}")
    except Exception as e:
        print(f"Error: {e}")
        print(body[:500])


if __name__ == "__main__":
    topic = pick_topic()
    print(f"Topic: {topic}")
    docs = load_docs()
    print(f"RAG: {len(docs)} docs")
    relevant = search(docs, topic)
    print(f"Sources: {len(relevant)}")
    for d in relevant:
        print(f"  - {d['title'][:60]}")
    digest = generate(topic, relevant)
    title = f"[Library Digest] {topic[:80]}"
    body = f"{digest}\n\n---\n*Vaked Library Digest · Genesis: {GENESIS[:8]} · {len(relevant)} sources from {len(docs)} total*"
    create_issue(title, body)
