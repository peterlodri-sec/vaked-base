#!/usr/bin/env python3
"""adk_multi_agent_system.py — Google ADK (Agent Development Kit) multi-agent system.

Builds a supervisor agent that delegates to three specialists:

1. Media Publisher      — YouTube Data API & SoundCloud Artist API
2. Steganography        — Art-for-Secrets LSB embedding
3. RAG & Vector Search  — pgvector / ChromaDB

Delegation is ADK's own mechanism: an ``LlmAgent`` holding ``sub_agents`` emits a
``transfer_to_agent`` function call, and ADK routes execution to the named child.
Routing is driven by each child's ``description``, which is why the smoke test
asserts every specialist has one.

``--smoke-test`` verifies the wiring only. It constructs the graph and checks its
shape; it does NOT call Gemini, so it needs no credentials and is safe in CI.
Live invocation is deliberately not implemented here yet.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from google.adk.agents import LlmAgent

log = logging.getLogger("adk-multi-agent")

# ADK's own docs use `gemini-flash-latest`. Override per environment if needed.
DEFAULT_MODEL = os.environ.get("ADK_MODEL", "gemini-flash-latest")


def build_supervisor(model: str = DEFAULT_MODEL) -> LlmAgent:
    """Build the supervisor and its three specialists.

    Every agent gets a description: ADK routes delegation by matching the task
    against these strings, so an agent without one is unreachable.
    """
    media = LlmAgent(
        name="MediaPublisherAgent",
        model=model,
        description=(
            "Publishes finished audio and video to YouTube and SoundCloud. "
            "Handles upload, metadata, thumbnails and release scheduling."
        ),
        instruction=(
            "You publish media. Given a track, prepare and upload it to YouTube "
            "and SoundCloud with correct title, description and tags. Report the "
            "resulting URLs. Never publish without an explicit title."
        ),
    )

    stego = LlmAgent(
        name="StegoSecretAgent",
        model=model,
        description=(
            "Embeds and extracts hidden payloads in audio and images using LSB "
            "steganography for the Art-for-Secrets work."
        ),
        instruction=(
            "You embed and extract steganographic payloads. State which carrier "
            "file and which bit depth you used, and confirm the payload survives "
            "a round trip before reporting success."
        ),
    )

    rag = LlmAgent(
        name="RAGVectorSearchAgent",
        model=model,
        description=(
            "Indexes and retrieves documents from pgvector and ChromaDB vector "
            "stores. Answers questions grounded in the indexed corpus."
        ),
        instruction=(
            "You index and retrieve. Ground every answer in retrieved chunks and "
            "cite the source of each. If retrieval returns nothing relevant, say "
            "so rather than answering from memory."
        ),
    )

    return LlmAgent(
        name="VakedSupervisorAgent",
        model=model,
        description="Routes constellation tasks to the specialist agent that owns them.",
        instruction=(
            "You coordinate three specialists. Delegate publishing tasks to "
            "MediaPublisherAgent, steganography tasks to StegoSecretAgent, and "
            "indexing or retrieval tasks to RAGVectorSearchAgent. For a task "
            "spanning several, delegate in sequence and pass each result forward. "
            "Do not attempt a specialist's work yourself."
        ),
        sub_agents=[media, stego, rag],
    )


def smoke_test() -> int:
    """Verify the agent graph is wired correctly. Returns a process exit code."""
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    supervisor = build_supervisor()

    children = supervisor.sub_agents
    check(len(children) == 3, f"expected 3 specialists, got {len(children)}")

    expected = {"MediaPublisherAgent", "StegoSecretAgent", "RAGVectorSearchAgent"}
    actual = {child.name for child in children}
    check(actual == expected, f"specialist names {actual} != expected {expected}")
    check(len(actual) == len(children), "specialist names are not unique")

    for agent in [supervisor, *children]:
        # ADK selects a delegate by matching the task against its description.
        # An empty description makes the agent silently unreachable.
        check(
            bool(agent.description and agent.description.strip()),
            f"{agent.name} has no description, so it can never be delegated to",
        )
        check(bool(agent.model), f"{agent.name} has no model set")

    for failure in failures:
        log.error("FAIL: %s", failure)

    if failures:
        log.error("ADK smoke test FAILED with %d problem(s)", len(failures))
        return 1

    log.info(
        "ADK smoke test passed: %s delegates to %s",
        supervisor.name,
        ", ".join(sorted(actual)),
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="verify the agent graph is wired correctly (no model calls, no credentials)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.smoke_test:
        return smoke_test()

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
