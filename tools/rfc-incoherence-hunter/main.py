"""RFC incoherence hunter — multi-specialist analysis of Vaked protocol RFCs.

Entry reasoner: rfc-incoherence-hunter.rfc_incoherence_hunter
Architecture:   Parallel Hunters (3 specialists) + HUNT→PROVE + Dynamic Cross-Reference Following
"""
import asyncio
import os

from agentfield import Agent, AIConfig

from reasoners import committee_router, specialists_router
from reasoners.helpers import (
    build_corpus_summary,
    build_full_corpus,
    deduplicate_findings,
    ingest_rfcs,
    render_finding,
    render_verified_findings,
)
from reasoners.models import CoherenceReport, SectionAssignment

app = Agent(
    node_id=os.getenv("AGENT_NODE_ID", "rfc-incoherence-hunter"),
    agentfield_server=os.getenv("AGENTFIELD_SERVER", "http://localhost:8080"),
    ai_config=AIConfig(
        model=os.getenv("AI_MODEL", "openrouter/google/gemini-2.5-flash"),
    ),
    dev_mode=True,
)

app.include_router(committee_router)
app.include_router(specialists_router)


@app.reasoner(tags=["entry"])
async def rfc_incoherence_hunter(
    model: str | None = None,
) -> dict:
    # 1. Ingest RFC documents from mounted volume
    rfc_texts = ingest_rfcs()
    if not rfc_texts:
        return {
            "error": "No RFC files found. Ensure VAKED_REPO_PATH is set and the volume is mounted.",
            "rfc_dir": os.getenv("RFC_DIR", "/rfcs/protocol/rfcs"),
        }

    corpus_summary = build_corpus_summary(rfc_texts)
    full_corpus = build_full_corpus(rfc_texts)

    # 2. Classify which sections each specialist should focus on
    assignment_dict = await app.call(
        f"{app.node_id}.section_classifier",
        corpus_summary=corpus_summary,
        model=model,
    )
    assignment = SectionAssignment(**assignment_dict)

    # 3. Run three specialist orchestrators in parallel
    orch_result, kernel_result, lang_result = await asyncio.gather(
        app.call(
            f"{app.node_id}.orchestration_expert",
            corpus=full_corpus,
            focus=assignment.orchestration_focus,
            model=model,
        ),
        app.call(
            f"{app.node_id}.kernel_expert",
            corpus=full_corpus,
            focus=assignment.kernel_focus,
            model=model,
        ),
        app.call(
            f"{app.node_id}.languages_expert",
            corpus=full_corpus,
            focus=assignment.languages_focus,
            model=model,
        ),
    )

    # 4. Collect and deduplicate all candidate findings
    all_findings = deduplicate_findings(
        orch_result.get("findings", [])
        + kernel_result.get("findings", [])
        + lang_result.get("findings", [])
    )

    # 5. HUNT→PROVE: verify non-minor findings in parallel
    to_verify = [f for f in all_findings if f.get("severity") in ("critical", "major")]
    minor_findings = [f for f in all_findings if f.get("severity") == "minor"]

    verdict_results: list[dict] = []
    if to_verify:
        raw_verdicts = await asyncio.gather(*[
            app.call(
                f"{app.node_id}.finding_verifier",
                finding_prose=render_finding(f),
                model=model,
            )
            for f in to_verify
        ])
        for finding, verdict in zip(to_verify, raw_verdicts):
            if verdict:
                verdict_results.append({
                    **finding,
                    "verdict": verdict.get("verdict", "uncertain"),
                    "refutation_argument": verdict.get("refutation_argument", ""),
                })

    all_for_report = verdict_results + [
        {**f, "verdict": "not_verified"} for f in minor_findings
    ]

    # 6. Compose coherence report
    report_prose = render_verified_findings(all_for_report)
    report_dict = await app.call(
        f"{app.node_id}.coherence_report_composer",
        verified_findings_prose=report_prose,
        total_candidates=len(all_findings),
        model=model,
    )

    confirmed = [
        v for v in verdict_results
        if v.get("verdict") == "confirmed"
    ]

    return {
        "report": report_dict,
        "total_candidates": len(all_findings),
        "total_confirmed": len(confirmed),
        "rfcs_analyzed": list(rfc_texts.keys()),
        "findings_by_specialist": {
            "orchestration": [f for f in all_findings if f.get("specialist") == "orchestration"],
            "kernel": [f for f in all_findings if f.get("specialist") == "kernel"],
            "languages": [f for f in all_findings if f.get("specialist") == "languages"],
            "cross_ref": [f for f in all_findings if f.get("specialist") == "cross_ref"],
        },
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8001")), auto_port=False)
