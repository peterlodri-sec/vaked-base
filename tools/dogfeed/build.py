"""Dogfeed builder — compiles Ralph decision logs into a public page."""
import os, time, glob, re

DECISIONS_DIR = "docs/decisions"
OUTPUT = "docs/website/dogfeed.html"

def parse_ralph_logs():
    """Parse all .ralph-log.md files and extract latest decisions."""
    tracks = []
    for f in sorted(glob.glob(os.path.join(DECISIONS_DIR, "*.ralph-log.md"))):
        track_name = os.path.basename(f).replace(".ralph-log.md", "")
        with open(f) as fh:
            content = fh.read()
        
        # Extract entries by ## headers
        sections = re.split(r"\n(?=## \d{4}-\d{2}-\d{2})", content)
        decisions = []
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            # Get the date from header
            header_match = re.search(r"## (\d{4}-\d{2}-\d{2})", sec)
            date = header_match.group(1) if header_match else "?"
            # Get the first substantive paragraph after the header
            lines = [l.strip() for l in sec.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("- **")]
            decision = ""
            for l in lines[:3]:
                if len(l) > 20:
                    decision = l[:250]
                    break
            if decision:
                ratified = "ratified" in sec.lower() or "Ratified" in sec
                decisions.append({"text": decision, "date": date, "ratified": ratified})
        
        if decisions:
            tracks.append({
                "name": track_name,
                "latest": decisions[-1]["text"],
                "date": decisions[-1]["date"],
                "ratified": decisions[-1]["ratified"],
                "total": len(decisions),
            })
    return tracks

def build():
    tracks = parse_ralph_logs()
    
    rows = ""
    for t in tracks:
        status = "✓ ratified" if t["ratified"] else "pending"
        color = "#20c060" if t["ratified"] else "#ffc800"
        rows += f"""<tr>
<td style="color:#4060a0;font-weight:500;white-space:nowrap">{t['name']}<br><span style="font-size:9px;color:#3a4a5a">{t.get('date','')}</span></td>
<td style="max-width:460px;font-size:11px;color:#90a0c0;line-height:1.5">{t['latest'][:250]}</td>
<td style="color:{color};font-size:10px;white-space:nowrap">{status}</td>
<td style="color:#3a4a5a;font-size:10px">{t['total']} total</td>
</tr>
"""
    
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Dogfeed — Vaked Ralph Decisions</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#08081a;color:#c8d0e0;font-family:'Inter','SF Pro',sans-serif;padding:0}}
.header{{background:linear-gradient(180deg,#0c0c24,#08081a);border-bottom:1px solid rgba(48,96,255,0.1);padding:40px 48px 32px}}
.header h1{{font-size:11px;color:#4060a0;letter-spacing:4px;text-transform:uppercase}}
.header .title{{font-size:28px;font-weight:600;color:#e0e8f0;margin-top:4px}}
.header .sub{{font-size:12px;color:#5a5a7a;margin-top:4px}}
.content{{max-width:960px;margin:0 auto;padding:0 48px 48px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:24px}}
td,th{{padding:10px 12px;border-bottom:1px solid rgba(48,96,255,0.08);text-align:left;vertical-align:top}}
th{{color:#4060a0;font-weight:500;font-size:10px;letter-spacing:1px;text-transform:uppercase}}
tr:hover td{{background:rgba(48,96,255,0.04)}}
a{{color:#4060a0;text-decoration:none;font-size:10px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin:24px 0}}
.card{{background:rgba(14,14,34,0.8);border:1px solid rgba(48,96,255,0.12);border-radius:10px;padding:16px}}
.card .val{{font-size:24px;font-weight:600;color:#e0e8f0}}
.card .lbl{{font-size:10px;color:#5a5a7a;margin-top:2px;letter-spacing:1px;text-transform:uppercase}}
</style></head><body>
<div class="header">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
<div style="width:24px;height:24px;border-radius:5px;background:linear-gradient(135deg,#3060ff,#4060a0);font-size:10px;display:flex;align-items:center;justify-content:center;color:#fff">🐕</div>
<div><h1>Dogfeed</h1></div>
<div style="margin-left:auto"><a href="https://constellation.vaked.dev">← constellation</a></div>
</div>
<div class="title">Ralph Decision Pipeline</div>
<div class="sub">autonomous strategy loop · read-only · {len(tracks)} tracks · updated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}</div>
</div>
<div class="content">
<div class="stats">
<div class="card"><div class="val">{sum(t['total'] for t in tracks)}</div><div class="lbl">Total Decisions</div></div>
<div class="card"><div class="val">{sum(1 for t in tracks if t['ratified'])}</div><div class="lbl">Ratified</div></div>
<div class="card"><div class="val">{len(tracks)}</div><div class="lbl">Active Tracks</div></div>
</div>
<table>
<tr><th>Track</th><th>Latest Decision</th><th>Status</th><th>Count</th></tr>
{rows}
</table>
</div>
</body></html>"""
    
    with open(OUTPUT, "w") as f:
        f.write(html)
    print(f"Dogfeed: {OUTPUT} ({len(tracks)} tracks, {sum(t['total'] for t in tracks) if tracks else 0} decisions)")

if __name__ == "__main__":
    build()
