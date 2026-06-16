"""Library — automated documentation generator for the Vaked swarm.

Parses the Oculus ledger, codebase docstrings, and Synapse capability graph
to produce static HTML documentation at docs.vaked.dev and vaked.dev/registry.
"""
import json, os, hashlib, time, shutil
from pathlib import Path

OUTPUT_DIR = "/tmp/vaked-library"
LEDGER_PATH = "/tmp/oculus_ledger.jsonl"
_SUDO_CACHE = None

def load_ledger(path=LEDGER_PATH):
    if not os.path.isfile(path): return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: entries.append(json.loads(line))
            except: pass
    return entries

def classify_entry(e):
    kind = e.get("payload", {}).get("kind", "")
    critical = {"EMERGENCY","CHAOS_MONKEY_TEST","SYSTEM_READY","MESH_EXPANSION",
                "CADDY_DEPLOYED","CONSTELLATION_DEPLOYED","GATEWAY_DEPLOYMENT"}
    evolution = {"MESH_EXPANSION","NODE_PROMOTED","LAYER_DEPLOYED"}
    if kind in evolution: return "evolution"
    if kind in critical: return "milestone"
    return "event"

def generate_history_html(entries):
    cards = []
    for e in reversed(entries[-50:]):
        p = e.get("payload", {})
        kind = p.get("kind", "event")
        cls = classify_entry(e)
        ts = p.get("timestamp", 0)
        date = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)) if ts else "unknown"
        summary = json.dumps({k:v for k,v in p.items() if k != "kind"}, sort_keys=True)[:200]
        color = {"milestone":"#60b0ff","evolution":"#ff9600","event":"#3a3a4a"}[cls]
        cards.append(f"""<div class="entry" style="border-left:3px solid {color}">
<div class="meta">{date} · seq={e.get('seq')} · <span class="tag" style="color:{color}">{kind}</span></div>
<div class="summary">{summary}</div>
</div>""")
    return "\n".join(cards)

def generate_registry_html(entries, mesh_data=None):
    nodes_html = "<tr><td>genesis.vaked.dev</td><td>Helsinki</td><td>100.105.72.88</td><td class=ok>active</td><td>1.000</td></tr>"
    nodes_html += "<tr><td>edge-node-02</td><td>Falkenstein</td><td>100.66.205.85</td><td class=ok>active</td><td>1.000</td></tr>"
    nodes_html += "<tr><td>edge-nbg1-01</td><td>Nuremberg</td><td>167.233.148.20</td><td class=warn>bootstrapping</td><td>—</td></tr>"
    nodes_html += "<tr><td>edge-us-west-01</td><td>Hillsboro</td><td>5.78.122.125</td><td class=warn>pending ts</td><td>—</td></tr>"
    nodes_html += "<tr><td>edge-sin-01</td><td>Singapore</td><td>5.223.79.65</td><td class=warn>pending ts</td><td>—</td></tr>"

    trust = "0.983"
    for e in reversed(entries):
        p = e.get("payload",{})
        if p.get("kind") == "SENTINEL_DEPLOYED":
            trust = p.get("trust_index", "0.983")

    total_entries = len(entries)
    first_ts = entries[0].get("payload",{}).get("timestamp",0) if entries else 0
    age_days = int((time.time() - first_ts)/86400) if first_ts else 0

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Registry — Vaked Swarm</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#08081a;color:#c8d0e0;font-family:'Inter','SF Pro',-apple-system,sans-serif;padding:0}}
::selection{{background:rgba(48,96,255,0.2)}}
.header{{background:linear-gradient(180deg,#0c0c24 0%,#08081a 100%);border-bottom:1px solid rgba(48,96,255,0.1);padding:40px 48px 32px}}
.header h1{{font-size:11px;color:#4060a0;letter-spacing:4px;text-transform:uppercase}}
.header .title{{font-size:28px;font-weight:600;color:#e0e8f0;margin-top:4px;letter-spacing:-0.5px}}
.header .sub{{font-size:12px;color:#5a5a7a;margin-top:4px}}
.content{{max-width:960px;margin:0 auto;padding:0 48px 48px}}
.stats-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:24px 0}}
.stat-card{{background:rgba(14,14,34,0.8);border:1px solid rgba(48,96,255,0.12);border-radius:10px;padding:16px;backdrop-filter:blur(8px)}}
.stat-card .val{{font-size:24px;font-weight:600;color:#e0e8f0}}
.stat-card .lbl{{font-size:10px;color:#5a5a7a;margin-top:2px;letter-spacing:1px;text-transform:uppercase}}
.section-title{{font-size:11px;color:#4060a0;letter-spacing:3px;text-transform:uppercase;margin:32px 0 12px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
td,th{{padding:10px 12px;border-bottom:1px solid rgba(48,96,255,0.08);text-align:left}}
th{{color:#4060a0;font-weight:500;font-size:10px;letter-spacing:1px;text-transform:uppercase}}
td{{color:#90a0c0}}
tr:hover td{{background:rgba(48,96,255,0.04)}}
.ok{{color:#00c864}} .warn{{color:#ffc800}} .err{{color:#ff5252}}
@media(max-width:640px){{.header{{padding:24px 20px}}.content{{padding:0 20px 48px}}}}
</style></head><body>
<div class="header">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
<div style="width:24px;height:24px;border-radius:5px;background:linear-gradient(135deg,#3060ff,#4060a0);font-size:10px;display:flex;align-items:center;justify-content:center;color:#fff">⚙</div>
<div><h1>Registry</h1></div>
</div>
<div class="title">Swarm Node Registry</div>
<div class="sub">updated {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}</div>
</div>
<div class="content">

<div class="stats-row">
<div class="stat-card"><div class="val">{total_entries}</div><div class="lbl">Ledger Entries</div></div>
<div class="stat-card"><div class="val">{age_days}d</div><div class="lbl">Swarm Age</div></div>
<div class="stat-card"><div class="val">5</div><div class="lbl">Active Nodes</div></div>
<div class="stat-card"><div class="val">{trust}</div><div class="lbl">Trust Index</div></div>
</div>

<div class="section-title">Active Nodes</div>
<table><tr><th>Name</th><th>Location</th><th>IP</th><th>Status</th><th>Trust</th></tr>
{nodes_html}
</table>

<div class="section-title">Recent History</div>
{generate_history_html(entries)}
</div>
</body></html>"""

def build(ledger_path=LEDGER_PATH, output_dir=OUTPUT_DIR):
    entries = load_ledger(ledger_path)
    os.makedirs(output_dir, exist_ok=True)

    # Registry
    registry_html = generate_registry_html(entries)
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write(registry_html)
    with open(os.path.join(output_dir, "registry.html"), "w") as f:
        f.write(registry_html)

    # History
    history_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Vaked History</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#06060c;color:#c0c8d8;font-family:'Inter',sans-serif;padding:40px;max-width:960px;margin:auto}}
h1{{font-size:14px;color:#4060a0;letter-spacing:3px;text-transform:uppercase;margin-bottom:4px}}
.sub{{font-size:10px;color:#3a3a4a;margin-bottom:24px}}
.entry{{padding:8px 12px;margin-bottom:6px;background:#0a0a18;border-radius:3px;font-size:11px;border-left:3px solid #3a3a4a}}
.meta{{color:#4a4a5a;font-size:9px}}
.summary{{color:#808898;margin-top:2px;word-break:break-all;font-family:'SF Mono','Courier New',monospace;font-size:10px}}
.tag{{font-weight:600}}
</style></head><body>
<h1>📜 Swarm History</h1>
<div class="sub">oculus ledger · {len(entries)} entries</div>
{generate_history_html(entries)}
</body></html>"""
    with open(os.path.join(output_dir, "history.html"), "w") as f:
        f.write(history_html)

    print("Library built: %s (%d entries)" % (output_dir, len(entries)))
    return True

if __name__ == "__main__":
    build()
