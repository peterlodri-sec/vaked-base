import os
from agentfield import AgentRouter
from reasoners.models import SectionAssignment, Verdict, CoherenceReport

NODE_ID = os.getenv("AGENT_NODE_ID", "rfc-incoherence-hunter")
router = AgentRouter(prefix="", tags=["committee"])


@router.reasoner()
async def section_classifier(
    corpus_summary: str,
    model: str | None = None,
) -> SectionAssignment:
    result = await router.ai(
        system=(
            "You are a protocol architecture expert. Given a summary of RFC section headers, "
            "produce three focused analysis briefs — one per specialist dimension:\n\n"
            "orchestration_focus: which sections concern HCP lifecycle frames, agent state machine "
            "transitions, pause/drain semantics, preceptord authority delegation, and rewind protocol.\n\n"
            "kernel_focus: which sections concern eBPF, BPF maps, TID→UUID binding, agent-guardd "
            "sole-writer invariant, thread scheduling interactions, and TelemetryBind/Unbind frames.\n\n"
            "languages_focus: which sections concern formal term definitions, MUST/SHOULD normative "
            "language consistency, logical ordering of protocol states, JournalDelta format invariants, "
            "and MemPalace boundary semantics.\n\n"
            "Each focus should be 2-4 sentences of plain English instruction for the analyst."
        ),
        user=corpus_summary,
        schema=SectionAssignment,
        model=model,
    )
    if not result.confident:
        result.orchestration_focus = (
            "Focus on §2 lifecycle Votive Frames, §4 pause/drain semantics, §6 preceptord authority. "
            "Check for missing state transitions and undefined error paths."
        )
        result.kernel_focus = (
            "Focus on §5 TelemetryBind/Unbind protocol and BPF map ownership. "
            "Check for dual-writer risks and TID stability assumptions."
        )
        result.languages_focus = (
            "Focus on §1 terminology, §3 JournalDelta format, §7 MemPalace boundary. "
            "Check for undefined terms in normative clauses and circular definitions."
        )
    return result


@router.reasoner()
async def finding_verifier(
    finding_prose: str,
    model: str | None = None,
) -> Verdict:
    result = await router.ai(
        system=(
            "You are a skeptical peer reviewer trying to REFUTE a finding about a protocol RFC. "
            "Your default position is verdict='refuted'. Only set verdict='confirmed' if ALL of:\n"
            "- The finding quotes exact RFC text that supports the claim\n"
            "- The incoherence cannot be resolved by reasonable interpretation of defined terms\n"
            "- The RFC does not address this issue elsewhere\n"
            "Set verdict='uncertain' if you cannot definitively refute but also cannot confirm. "
            "Always provide refutation_argument — if confirming, explain why you could not refute."
        ),
        user=finding_prose,
        schema=Verdict,
        model=model,
    )
    if not result.confident:
        result.verdict = "uncertain"
        result.refutation_argument = "Verifier could not reach confident verdict."
    return result


@router.reasoner()
async def coherence_report_composer(
    verified_findings_prose: str,
    total_candidates: int,
    model: str | None = None,
) -> CoherenceReport:
    result = await router.ai(
        system=(
            "You are a protocol design lead summarizing a peer review of an RFC series. "
            "Given verified findings from three specialist reviewers (orchestration, kernel, languages), "
            "compose a coherence report:\n"
            "- confirmed_critical: list of confirmed findings with severity=critical\n"
            "- confirmed_major: list of confirmed findings with severity=major\n"
            "- uncertain_items: list of uncertain findings worth manual review\n"
            "- total_confirmed: count of confirmed findings across all severities\n"
            "- executive_summary: 2-3 sentence summary for an RFC status meeting\n"
            "Be concise. Each list item is one sentence."
        ),
        user=f"Total candidate findings submitted: {total_candidates}\n\n{verified_findings_prose}",
        schema=CoherenceReport,
        model=model,
    )
    if not result.confident:
        result.executive_summary = (
            "RFC coherence review completed with low confidence. Manual verification required."
        )
    return result
