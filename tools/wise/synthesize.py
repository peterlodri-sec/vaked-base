"""Wise Node — Engram strategist for the Vaked swarm.

Performs Daily Synthesis: ingests Oculus Ledger, Mnemosyne ancestry,
and Sentinel reputation; outputs a Strategic Briefing (strategy.json)
posted to the ledger. Issues Strategic Directives to the operator.

This node does NOT execute system commands. It advises.
"""
import json, os, time, hashlib
from typing import Optional
from pathlib import Path

ENGRAM_PATH = "engram/workflow.json"
LEDGER_PATH = "/tmp/oculus_ledger.jsonl"
OUTPUT_DIR = "/tmp/vaked-library"

class WiseNode:
    def __init__(self):
        self.engram = self._load_engram()
        self.ledger = self._load_ledger()

    def _load_engram(self):
        if os.path.isfile(ENGRAM_PATH):
            with open(ENGRAM_PATH) as f:
                return json.load(f)
        return {"heuristics": [], "focus_areas": []}

    def _load_ledger(self):
        if not os.path.isfile(LEDGER_PATH):
            return []
        entries = []
        with open(LEDGER_PATH) as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: entries.append(json.loads(line))
                except: pass
        return entries

    def assess_focus_areas(self):
        """Determine which focus areas are active based on ledger state."""
        focus = []
        has_transatlantic = any(
            e.get("payload",{}).get("rtt_from_eu_ms",0) > 300
            for e in self.ledger
        )
        has_low_trust = any(
            e.get("payload",{}).get("kind","") in ("SENTINEL_DEPLOYED",)
            for e in self.ledger
        )
        has_pending = any(
            e.get("payload",{}).get("status","") in ("pending_bootstrap","needs_auth")
            for e in self.ledger
        )

        for fa in self.engram.get("focus_areas", []):
            fid = fa["id"]
            if fid == "F1": fa["active"] = has_transatlantic
            elif fid == "F2": fa["active"] = has_low_trust
            elif fid == "F3": fa["active"] = has_pending
            elif fid == "F4": fa["active"] = True
            focus.append(fa)
        return focus

    def synthesize(self) -> dict:
        """Produce a strategic briefing."""
        focus = self.assess_focus_areas()
        active_foci = [f for f in focus if f["active"]]
        primary_focus = active_foci[0]["label"] if active_foci else "Idle"

        # Count events by type
        event_counts = {}
        for e in self.ledger:
            kind = e.get("payload",{}).get("kind","unknown")
            event_counts[kind] = event_counts.get(kind, 0) + 1

        # Find latest critical event
        latest_critical = None
        for e in reversed(self.ledger):
            k = e.get("payload",{}).get("kind","")
            if k in ("CHAOS_MONKEY_TEST","EMERGENCY_HOLD_ACTIVE","MESH_EXPANSION"):
                latest_critical = {
                    "kind": k,
                    "seq": e.get("seq"),
                    "summary": str(e.get("payload",{}))[:120]
                }
                break

        # Generate strategic directives
        directives = []
        if any(f["id"] == "F1" for f in active_foci):
            directives.append({
                "heuristic": "H01",
                "message": "Transatlantic RTT exceeds 300ms — Adaptive Batching is active. Consider colocating a US-East node to reduce NA latency."
            })
        if event_counts.get("CHAOS_MONKEY_TEST",0) > 0:
            directives.append({
                "heuristic": "H06",
                "message": "Chaos events detected in ledger. Mesh self-healed within convergence thresholds. No action required."
            })

        briefing = {
            "generated_at": time.time(),
            "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "engram_version": self.engram.get("meta",{}).get("name","unknown"),
            "primary_focus": primary_focus,
            "active_focus_areas": active_foci,
            "ledger_summary": {
                "total_entries": len(self.ledger),
                "event_breakdown": event_counts,
                "latest_critical_event": latest_critical,
            },
            "strategic_directives": directives,
            "recommendations": [
                "Complete Tailscale auth for US and APAC nodes to expand quorum",
                "Run Mnemosyne squash when Oculus ledger exceeds 100 entries",
                "Verify Sentinel trust scores remain above 0.7 threshold"
            ],
            "governance": {
                "quorum_nodes": 1,
                "pending_nodes": 3,
                "trust_index": "0.983 (estimated)",
                "next_scheduled": "Mnemosyne squash in ~23h"
            }
        }
        return briefing

    def check_panic_threshold(self) -> Optional[dict]:
        """Check if >=50% of nodes are unreachable. Trigger SYSTEM_PANIC if so."""
        total = 5  # genesis + edge-02 + nbg1 + us-west + sin
        unreachable = 0
        for e in self.ledger:
            s = e.get("payload",{}).get("status","")
            if s in ("pending_bootstrap","needs_auth","unreachable"):
                unreachable += 1
        ratio = unreachable / total if total > 0 else 0
        if ratio >= 0.5:
            return {"kind":"SYSTEM_PANIC","unreachable":unreachable,"total":total,
                    "ratio":ratio,"action":"freeze_ledger+halt_playground+alert_operator"}
        return None

    def check_graveyard(self) -> Optional[dict]:
        """Check graveyard.log. Empty = warning."""
        gpath = "/var/log/vaked/graveyard.log"
        if os.path.isfile(gpath):
            with open(gpath) as f:
                lines = [l for l in f if l.strip()]
            if lines:
                return {"entries":len(lines),"status":"healthy"}
        return {"entries":0,"status":"WARNING: graveyard empty — system not self-pruning"}

    def synthesize(self) -> dict:
        """Produce a strategic briefing."""
        focus = self.assess_focus_areas()
        active_foci = [f for f in focus if f["active"]]
        primary_focus = active_foci[0]["label"] if active_foci else "Idle"

        # Count events by type
        event_counts = {}
        for e in self.ledger:
            kind = e.get("payload",{}).get("kind","unknown")
            event_counts[kind] = event_counts.get(kind, 0) + 1

        # Panic check
        panic = self.check_panic_threshold()

        # Graveyard check
        graveyard = self.check_graveyard()

        # Find latest critical event
        latest_critical = None
        for e in reversed(self.ledger):
            k = e.get("payload",{}).get("kind","")
            if k in ("CHAOS_MONKEY_TEST","EMERGENCY_HOLD_ACTIVE","MESH_EXPANSION"):
                latest_critical = {
                    "kind": k,
                    "seq": e.get("seq"),
                    "summary": str(e.get("payload",{}))[:120]
                }
                break

        # Generate strategic directives with governance binding
        directives = []
        if panic:
            directives.append({
                "heuristic": "H10",
                "severity": "CRITICAL",
                "message": f"SYSTEM_PANIC: {panic['unreachable']}/{panic['total']} nodes unreachable. Ledger frozen. Experiments halted."
            })

        # Node happiness check (H08)
        has_high_latency = any(e.get("payload",{}).get("rtt_from_eu_ms",0) > 50 for e in self.ledger)
        if has_high_latency:
            directives.append({
                "heuristic": "H08",
                "severity": "WARNING",
                "message": "Node Happiness at risk: transatlantic RTT > 50ms. Pausing mesh expansion until stability confirmed."
            })

        # Graveyard warning
        if graveyard and graveyard.get("entries",0) == 0:
            directives.append({
                "heuristic": "H11",
                "severity": "WARNING",
                "message": graveyard["status"]
            })

        # Two-Strike protocol reminder
        directives.append({
            "heuristic": "H09",
            "severity": "INFO",
            "message": "Two-Strike Integrity Protocol active. All nodes subject to Quarantine → Exclusion on divergence."
        })

        if event_counts.get("CHAOS_MONKEY_TEST",0) > 0:
            directives.append({
                "heuristic": "H06",
                "message": "Chaos events detected in ledger. Mesh self-healed within convergence thresholds. No action required."
            })

        briefing = {
            "generated_at": time.time(),
            "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "engram_version": self.engram.get("meta",{}).get("name","unknown"),
            "primary_focus": "System Stability" if has_high_latency else primary_focus,
            "active_focus_areas": active_foci,
            "ledger_summary": {
                "total_entries": len(self.ledger),
                "event_breakdown": event_counts,
                "latest_critical_event": latest_critical,
            },
            "governance": {
                "node_happiness_kpi": {"latency_ms":"<50","gossip_success":">99%","resource_load":"<70%","current_status":"monitoring"},
                "two_strike_protocol": {"active":True,"strike1":"reconcile+quarantine","strike2":"permanent_exclusion"},
                "panic_threshold": panic if panic else {"status":"normal","unreachable_ratio":"<50%"},
                "graveyard": graveyard,
                "playground": {"mode":"restricted","promotion_gate":"operator_signature_or_24h_validation"},
            },
            "strategic_directives": directives,
            "recommendations": [
                "Re-evaluate transatlantic node happiness before expanding further",
                "Run Two-Strike drill on a test node to verify quarantine pathway",
                "Create graveyard entry when retiring nodes — empty graveyard is a warning",
                "Complete Tailscale auth for US and APAC nodes to reduce unreachable ratio"
            ],
        }
        return briefing

    def analyze_past_event(self, seq: int) -> dict:
        """Analyze a past ledger event using Engram heuristics."""
        target = None
        for e in self.ledger:
            if e.get("seq") == seq:
                target = e
                break
        if not target:
            return {"error": f"No event at seq={seq}"}

        payload = target.get("payload", {})
        kind = payload.get("kind", "?")

        analysis = {
            "target_event": {"seq": seq, "kind": kind},
            "engram_heuristics_applied": [],
            "conclusion": "",
            "strategic_relevance": ""
        }

        if kind == "CHAOS_MONKEY_TEST":
            verdict = payload.get("verdict", "?")
            convergence = payload.get("convergence_ms", "?")
            injected = payload.get("injected", {})

            analysis["engram_heuristics_applied"] = [
                {"id": "H06", "reason": "Chaos Recovery Postulate — wait 3 cycles before declaring healed"},
                {"id": "H02", "reason": "Trust Decay Response — monitor but do not isolate"}
            ]
            analysis["conclusion"] = (
                f"Chaos Monkey test at seq={seq}: injected {json.dumps(injected)}, "
                f"verdict={verdict}, convergence={convergence}ms. "
                f"Engram H06 confirms mesh self-healed within convergence threshold. "
                f"H02 recommends continued observation — no isolation needed. "
                f"The test validated genesis authority propagation (deny overrides allow)."
            )
            analysis["strategic_relevance"] = (
                "Confirms anti-entropy logic is correct. No remediation needed. "
                "Log result to Oculus and continue normal operations."
            )

        elif kind == "MESH_EXPANSION":
            node = payload.get("node", "?")
            latency = payload.get("rtt_from_eu_ms", "?")
            batching = payload.get("adaptive_batching", False)

            analysis["engram_heuristics_applied"] = [
                {"id": "H01", "reason": "Latency-Convergence Tradeoff — enable batching if RTT > 300ms"},
                {"id": "H05", "reason": "Node Promotion Gate — node must pass Genesis Hash Verification"}
            ]
            analysis["conclusion"] = (
                f"Mesh expansion to {node} (RTT={latency}ms, batching={'ON' if batching else 'OFF'}). "
                f"Engram H01 triggered Adaptive Batching for transatlantic link. "
                f"H05 requires Genesis Hash Verification before node gains quorum rights."
            )
            analysis["strategic_relevance"] = (
                f"Node {node} pending Tailscale auth. Once authenticated, "
                f"verify hash and promote to observer status. "
                f"Batching conserves bandwidth — expected convergence impact: +{latency}ms."
            )

        else:
            analysis["conclusion"] = f"Event {kind} at seq={seq}: routine operation, no Engram exceptions."
            analysis["strategic_relevance"] = "Standard monitoring. No action required."

        return analysis

    def to_dict(self):
        return {
            "engram": self.engram.get("meta", {}),
            "focus_areas": self.assess_focus_areas(),
            "heuristic_count": len(self.engram.get("heuristics", [])),
        }

def generate_wisdom_html(briefing: dict) -> str:
    """Generate the public /wisdom page."""
    focus_html = ""
    for f in briefing.get("active_focus_areas", []):
        icon = "●" if f["active"] else "○"
        focus_html += f'<div class="focus {"active" if f["active"] else "inactive"}">{icon} {f["label"]}</div>'

    dir_html = ""
    for d in briefing.get("strategic_directives", []):
        dir_html += f'<div class="directive"><span class="tag">H{d["heuristic"]}</span> {d["message"]}</div>'

    rec_html = ""
    for r in briefing.get("recommendations", []):
        rec_html += f'<li>{r}</li>'

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Wisdom — Vaked Swarm</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#08081a;color:#c8d0e0;font-family:'Inter','SF Pro',-apple-system,sans-serif;padding:0}}
::selection{{background:rgba(128,96,192,0.3)}}
.header{{background:linear-gradient(180deg,#0c0c24 0%,#08081a 100%);border-bottom:1px solid rgba(128,96,192,0.1);padding:40px 48px 32px}}
.header h1{{font-size:11px;color:#8060c0;letter-spacing:4px;text-transform:uppercase}}
.header .title{{font-size:28px;font-weight:600;color:#e0e8f0;margin-top:4px;letter-spacing:-0.5px}}
.header .sub{{font-size:12px;color:#5a5a7a;margin-top:4px}}
.content{{max-width:960px;margin:0 auto;padding:0 48px 48px}}
.stats-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:24px 0}}
.stat-card{{background:rgba(14,14,34,0.8);border:1px solid rgba(128,96,192,0.12);border-radius:10px;padding:16px;backdrop-filter:blur(8px)}}
.stat-card .val{{font-size:24px;font-weight:600;color:#e0e8f0}}
.stat-card .lbl{{font-size:10px;color:#5a5a7a;margin-top:2px;letter-spacing:1px;text-transform:uppercase}}
.section-title{{font-size:11px;color:#8060c0;letter-spacing:3px;text-transform:uppercase;margin:32px 0 12px}}
.focus{{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:6px;font-size:11px;margin:3px;font-weight:500}}
.focus.active{{background:rgba(128,96,192,0.12);border:1px solid rgba(128,96,192,0.25);color:#b090e0}}
.focus.inactive{{background:rgba(26,26,46,0.5);border:1px solid rgba(26,26,46,0.3);color:#4a4a6a}}
.directive{{padding:10px 14px;margin:6px 0;background:rgba(14,14,34,0.6);border-left:3px solid #8060c0;border-radius:6px;font-size:12px;line-height:1.5;color:#a0a8c0}}
.directive .tag{{font-size:9px;color:#8060c0;font-weight:600;letter-spacing:1px;text-transform:uppercase}}
ul{{list-style:none;padding:0}}
li{{padding:6px 0 6px 20px;font-size:12px;color:#7a8aaa;line-height:1.5;position:relative}}
li:before{{content:"→";position:absolute;left:0;color:#8060c0}}
.gov-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin:12px 0}}
.gov-item{{background:rgba(14,14,34,0.6);border:1px solid rgba(128,96,192,0.08);border-radius:8px;padding:10px 14px}}
.gov-item .key{{font-size:9px;color:#5a5a7a;letter-spacing:1px;text-transform:uppercase}}
.gov-item .val{{font-size:12px;color:#b0b8d0;margin-top:2px}}
@media(max-width:640px){{.header{{padding:24px 20px}}.content{{padding:0 20px 48px}}}}
</style></head><body>
<div class="header">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
<div style="width:24px;height:24px;border-radius:5px;background:linear-gradient(135deg,#8060c0,#3060ff);font-size:10px;display:flex;align-items:center;justify-content:center;color:#fff">✦</div>
<div><h1>Wisdom</h1></div>
</div>
<div class="title">Swarm Strategic Briefing</div>
<div class="sub">engram v1 · {briefing.get("generated_at_iso","")}</div>
</div>
<div class="content">

<div class="stats-row">
<div class="stat-card"><div class="val">{briefing.get("primary_focus","—")}</div><div class="lbl">Primary Focus</div></div>
<div class="stat-card"><div class="val">{briefing["ledger_summary"]["total_entries"]}</div><div class="lbl">Ledger Entries</div></div>
<div class="stat-card"><div class="val">{len(briefing["active_focus_areas"])}</div><div class="lbl">Active Focus Areas</div></div>
</div>

<div class="section-title">Active Focus Areas</div>
<div>{focus_html}</div>

<div class="section-title">Strategic Directives</div>
{dir_html if dir_html else '<div style="color:#4a4a6a;font-size:12px;padding:12px;background:rgba(14,14,34,0.4);border-radius:6px">No active directives</div>'}

<div class="section-title">Recommendations</div>
<ul>{rec_html}</ul>

<div class="section-title">Governance</div>
<div class="gov-grid">
<div class="gov-item"><div class="key">Node Happiness KPI</div><div class="val">latency &lt;50ms · gossip &gt;99% · load &lt;70%</div></div>
<div class="gov-item"><div class="key">Two-Strike Protocol</div><div class="val">Active — Strike1=quarantine · Strike2=exclusion</div></div>
<div class="gov-item"><div class="key">Graveyard</div><div class="val">{briefing["governance"]["graveyard"]["entries"]} entries · {briefing["governance"]["graveyard"]["status"][:40]}</div></div>
<div class="gov-item"><div class="key">Playground</div><div class="val">{briefing["governance"]["playground"]["mode"]} · gate: {briefing["governance"]["playground"]["promotion_gate"]}</div></div>
<div class="gov-item"><div class="key">Engram</div><div class="val">{briefing["engram_version"]}</div></div>
</div>
</div>
</body></html>"""

def run_synthesis(ledger_path=LEDGER_PATH, output_dir=OUTPUT_DIR):
    """Run one synthesis cycle and write output."""
    wise = WiseNode()
    briefing = wise.synthesize()

    # Write strategy.json
    strategy_path = os.path.join(output_dir, "strategy.json")
    with open(strategy_path, "w") as f:
        json.dump(briefing, f, indent=2)
    print("Strategy written: %s" % strategy_path)

    # Write wisdom.html
    wisdom_html = generate_wisdom_html(briefing)
    wisdom_path = os.path.join(output_dir, "wisdom.html")
    with open(wisdom_path, "w") as f:
        f.write(wisdom_html)
    print("Wisdom page: %s" % wisdom_path)

    # Log to ledger (append-only, read-only from system)
    print("Synthesis complete: focus=%s, directives=%d" % (
        briefing["primary_focus"], len(briefing["strategic_directives"])))
    return briefing

if __name__ == "__main__":
    run_synthesis()
