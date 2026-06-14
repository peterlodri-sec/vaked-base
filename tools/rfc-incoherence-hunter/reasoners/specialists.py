import asyncio
import os
from agentfield import AgentRouter
from reasoners.models import CandidateFinding, CrossRefAnalysis

NODE_ID = os.getenv("AGENT_NODE_ID", "rfc-incoherence-hunter")
router = AgentRouter(prefix="", tags=["specialist"])


# ---- Orchestration specialist ----

@router.reasoner()
async def orchestration_expert(
    corpus: str,
    focus: str,
    model: str | None = None,
) -> dict:
    contract_result, lifecycle_result = await asyncio.gather(
        router.call(
            f"{NODE_ID}.protocol_contract_checker",
            corpus=corpus, focus=focus, model=model,
        ),
        router.call(
            f"{NODE_ID}.lifecycle_checker",
            corpus=corpus, focus=focus, model=model,
        ),
    )
    findings = (
        _tag_specialist(contract_result.get("findings", []), "orchestration")
        + _tag_specialist(lifecycle_result.get("findings", []), "orchestration")
    )
    findings += await _follow_cross_refs(findings, corpus, model)
    return {"findings": findings}


@router.reasoner()
async def protocol_contract_checker(
    corpus: str,
    focus: str,
    model: str | None = None,
) -> dict:
    result = await router.ai(
        system=(
            "You are a distributed systems protocol expert. Analyze the RFC corpus for "
            "PROTOCOL CONTRACT violations:\n"
            "- Missing preconditions on normative operations (MUST without precondition stated)\n"
            "- Undefined error paths (what happens when an HCP frame is lost or rejected)\n"
            "- Round-trip incompleteness (request frame defined but its response not, or vice versa)\n"
            "- Ambiguous MUST/SHOULD that can be satisfied in contradictory ways\n"
            "- Missing acknowledgment path for lifecycle signals\n"
            "Report the SINGLE most clear-cut finding. Quote the exact RFC text. "
            "Set needs_cross_ref=true and cross_ref_target to the section header if verifying this "
            "finding requires reading a referenced section not present in the corpus. "
            "Set confident=false if you find no real protocol contract violation."
        ),
        user=f"Focus instructions: {focus}\n\nCorpus:\n{corpus}",
        schema=CandidateFinding,
        model=model,
    )
    return {"findings": [result.model_dump()] if result.confident else []}


@router.reasoner()
async def lifecycle_checker(
    corpus: str,
    focus: str,
    model: str | None = None,
) -> dict:
    result = await router.ai(
        system=(
            "You are an OTP/BEAM actor lifecycle expert. Analyze the RFC corpus for "
            "LIFECYCLE STATE MACHINE issues:\n"
            "- States implied by transitions but never named in the state machine\n"
            "- Dead transitions: defined edges whose source state is never reachable\n"
            "- Deadlock: circular wait on HCP frames between two or more actors\n"
            "- GenServer contract violations: blocking call/3 inside drain, crash during paused state\n"
            "- Missing terminal states: can the machine reach a stuck non-terminal state?\n"
            "Report the SINGLE most clear-cut finding. Quote the exact RFC text. "
            "Set confident=false if you find no real lifecycle issue."
        ),
        user=f"Focus instructions: {focus}\n\nCorpus:\n{corpus}",
        schema=CandidateFinding,
        model=model,
    )
    return {"findings": [result.model_dump()] if result.confident else []}


# ---- Kernel specialist ----

@router.reasoner()
async def kernel_expert(
    corpus: str,
    focus: str,
    model: str | None = None,
) -> dict:
    bpf_result, thread_result = await asyncio.gather(
        router.call(
            f"{NODE_ID}.bpf_atomicity_checker",
            corpus=corpus, focus=focus, model=model,
        ),
        router.call(
            f"{NODE_ID}.thread_model_checker",
            corpus=corpus, focus=focus, model=model,
        ),
    )
    findings = (
        _tag_specialist(bpf_result.get("findings", []), "kernel")
        + _tag_specialist(thread_result.get("findings", []), "kernel")
    )
    findings += await _follow_cross_refs(findings, corpus, model)
    return {"findings": findings}


@router.reasoner()
async def bpf_atomicity_checker(
    corpus: str,
    focus: str,
    model: str | None = None,
) -> dict:
    result = await router.ai(
        system=(
            "You are a Linux kernel contributor specializing in eBPF. "
            "Analyze the RFC corpus for BPF MAP CORRECTNESS issues:\n"
            "- Race conditions from multiple writers on the same BPF map\n"
            "- Single-writer invariant: the RFC must name exactly one daemon that writes each map\n"
            "- TID→UUID binding atomicity: what if the BEAM scheduler migrates a process "
            "between the TID lookup and the eBPF event capture? Is the window named?\n"
            "- eBPF program lifetime vs userspace daemon restart ordering "
            "(maps survive program unload; stale entries?)\n"
            "- Any kernel-verifier-visible invariant that the protocol assumes but cannot enforce\n"
            "Report the SINGLE most clear-cut finding. Quote the exact RFC text. "
            "Set confident=false if you find no real BPF correctness issue."
        ),
        user=f"Focus instructions: {focus}\n\nCorpus:\n{corpus}",
        schema=CandidateFinding,
        model=model,
    )
    return {"findings": [result.model_dump()] if result.confident else []}


@router.reasoner()
async def thread_model_checker(
    corpus: str,
    focus: str,
    model: str | None = None,
) -> dict:
    result = await router.ai(
        system=(
            "You are an OS kernel scheduling expert. "
            "Analyze the RFC corpus for THREAD MODEL assumption issues:\n"
            "- BEAM processes are NOT pinned to OS threads (scheduler may migrate). "
            "Does the RFC assume TID stability that BEAM does not guarantee?\n"
            "- OS-level TID reuse: if a BEAM scheduler thread exits and its TID is reused "
            "before TelemetryUnbind fires, does the protocol handle the stale binding?\n"
            "- Scheduler latency vs protocol timeout: do timeout values account for "
            "BEAM reduction-count preemption and OS scheduling delays?\n"
            "- Any BEAM PID to OS TID mapping that is assumed 1:1 but is M:N in practice\n"
            "Report the SINGLE most clear-cut finding. Quote the exact RFC text. "
            "Set confident=false if you find no real thread model issue."
        ),
        user=f"Focus instructions: {focus}\n\nCorpus:\n{corpus}",
        schema=CandidateFinding,
        model=model,
    )
    return {"findings": [result.model_dump()] if result.confident else []}


# ---- Languages / TCS specialist ----

@router.reasoner()
async def languages_expert(
    corpus: str,
    focus: str,
    model: str | None = None,
) -> dict:
    formal_result, semantic_result = await asyncio.gather(
        router.call(
            f"{NODE_ID}.formal_consistency_checker",
            corpus=corpus, focus=focus, model=model,
        ),
        router.call(
            f"{NODE_ID}.semantic_completeness_checker",
            corpus=corpus, focus=focus, model=model,
        ),
    )
    findings = (
        _tag_specialist(formal_result.get("findings", []), "languages")
        + _tag_specialist(semantic_result.get("findings", []), "languages")
    )
    findings += await _follow_cross_refs(findings, corpus, model)
    return {"findings": findings}


@router.reasoner()
async def formal_consistency_checker(
    corpus: str,
    focus: str,
    model: str | None = None,
) -> dict:
    result = await router.ai(
        system=(
            "You are a type theorist and formal methods expert. "
            "Analyze the RFC corpus for LOGICAL CONSISTENCY issues:\n"
            "- Circular definitions: term A defined via term B, term B defined via term A\n"
            "- Underdetermined semantics: a term appears in normative MUST text but is never defined\n"
            "- Contradictory MUST constraints: two MUST clauses that cannot simultaneously be satisfied\n"
            "- Temporal ordering violations: A is required before B, but B is required to enable A\n"
            "- Missing quantifiers: 'for all agents' vs 'for some agent' distinction absent in normative text\n"
            "- Invariants stated as simultaneously required but logically incompatible\n"
            "Report the SINGLE most clear-cut finding. Quote the exact RFC text. "
            "Set confident=false if you find no real logical consistency issue."
        ),
        user=f"Focus instructions: {focus}\n\nCorpus:\n{corpus}",
        schema=CandidateFinding,
        model=model,
    )
    return {"findings": [result.model_dump()] if result.confident else []}


@router.reasoner()
async def semantic_completeness_checker(
    corpus: str,
    focus: str,
    model: str | None = None,
) -> dict:
    result = await router.ai(
        system=(
            "You are a programming languages researcher specializing in protocol specification. "
            "Analyze the RFC corpus for SEMANTIC COMPLETENESS issues:\n"
            "- Undefined terms used in normative (MUST/SHALL/REQUIRED) clauses\n"
            "- Reachable-but-unnamed states: states reachable by composing defined transitions "
            "but not explicitly named in the state machine\n"
            "- Operations with unspecified return values or side effects\n"
            "- Safety properties without corresponding liveness properties "
            "(prevents X but never guarantees Y eventually happens)\n"
            "- Frame types whose fields are named but whose valid ranges or invariants are unstated\n"
            "Report the SINGLE most clear-cut finding. Quote the exact RFC text. "
            "Set confident=false if you find no real semantic completeness issue."
        ),
        user=f"Focus instructions: {focus}\n\nCorpus:\n{corpus}",
        schema=CandidateFinding,
        model=model,
    )
    return {"findings": [result.model_dump()] if result.confident else []}


# ---- Shared cross-reference follower ----

@router.reasoner()
async def cross_ref_follower(
    corpus: str,
    section_ref: str,
    parent_finding: str,
    model: str | None = None,
) -> dict:
    result = await router.ai(
        system=(
            "You are a protocol analyst following a cross-reference to verify or extend a finding. "
            "Locate the referenced section in the corpus. Determine whether it resolves, confirms, "
            "or extends the parent finding. "
            "Return new_findings as a list of plain-English strings describing any additional "
            "incoherence discovered in the referenced section. "
            "Return an empty list if the section resolves the parent finding. "
            "Set confident=false if the referenced section is not present in the corpus."
        ),
        user=(
            f"Parent finding: {parent_finding}\n"
            f"Cross-reference target section: {section_ref}\n\n"
            f"Corpus:\n{corpus}"
        ),
        schema=CrossRefAnalysis,
        model=model,
    )
    if not result.confident:
        return {"new_findings_structured": []}
    structured = [
        {
            "specialist": "cross_ref",
            "rfc_id": "0004",
            "section_ref": result.section_ref,
            "finding_type": "cross_ref_extension",
            "description": f,
            "supporting_quote": "",
            "severity": "major",
            "needs_cross_ref": False,
            "cross_ref_target": "",
            "confident": True,
        }
        for f in result.new_findings
        if f.strip()
    ]
    return {"new_findings_structured": structured}


# ---- Internal helpers (not reasoners) ----

def _tag_specialist(findings: list[dict], name: str) -> list[dict]:
    for f in findings:
        f["specialist"] = name
    return findings


async def _follow_cross_refs(findings: list[dict], corpus: str, model: str | None) -> list[dict]:
    targets = [
        f for f in findings
        if f.get("needs_cross_ref") and f.get("cross_ref_target")
        and f.get("severity") in ("critical", "major")
    ]
    if not targets:
        return []
    extras = await asyncio.gather(*[
        router.call(
            f"{NODE_ID}.cross_ref_follower",
            corpus=corpus,
            section_ref=f["cross_ref_target"],
            parent_finding=f["description"],
            model=model,
        )
        for f in targets
    ])
    result = []
    for extra in extras:
        if extra:
            result.extend(extra.get("new_findings_structured", []))
    return result
