#!/usr/bin/env python3
"""build.py — generate a spec-verification dashboard for vaked-base.

Usage:
    python3 tools/specdash/build.py [--out PATH] [--serve [PORT]] [--open]
                                    [--no-local] [--no-github]

Flags:
    --out PATH        Output HTML file (default: tools/specdash/index.html)
    --serve [PORT]    Write file then serve it via http.server (default port 8731)
    --open            Open the file/URL with macOS open(1) after writing
    --no-local        Skip running the local spec suite
    --no-github       Skip GitHub API calls

Requires: Python 3 stdlib only. gh CLI for GitHub data.
"""

import argparse
import datetime
import html
import json
import os
import re
import subprocess
import sys
import textwrap

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO = "peterlodri-sec/vaked-base"
WORKFLOW_FILE = "spec-tests.yml"
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "index.html")
DEFAULT_PORT = 8731


# ---------------------------------------------------------------------------
# GitHub data
# ---------------------------------------------------------------------------

def _gh(*args):
    """Run gh and return parsed JSON, or None on error."""
    try:
        result = subprocess.run(
            ["gh"] + list(args),
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None, result.stderr.strip()
        return json.loads(result.stdout), None
    except FileNotFoundError:
        return None, "gh CLI not found"
    except Exception as e:
        return None, str(e)


def fetch_runs():
    """Return (list_of_run_dicts, error_str_or_None)."""
    data, err = _gh(
        "api",
        f"repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=30"
    )
    if data is None:
        # Fallback: list all runs, filter by name
        data2, err2 = _gh("api", f"repos/{REPO}/actions/runs?per_page=50")
        if data2 is None:
            return [], f"GitHub API failed: {err}; fallback: {err2}"
        runs = [
            r for r in data2.get("workflow_runs", [])
            if r.get("name") == "spec-tests"
        ]
        return runs, None
    return data.get("workflow_runs", []), None


def parse_run(r):
    """Normalize a raw run dict into what we use for rendering."""
    started = r.get("run_started_at") or r.get("created_at", "")
    updated = r.get("updated_at", "")
    duration_s = None
    try:
        t0 = datetime.datetime.fromisoformat(started.replace("Z", "+00:00"))
        t1 = datetime.datetime.fromisoformat(updated.replace("Z", "+00:00"))
        duration_s = int((t1 - t0).total_seconds())
    except Exception:
        pass

    ref = r.get("head_branch") or r.get("head_tag") or "?"
    # head_branch may be None for tag pushes; try display_title or head_commit
    if not ref or ref == "None":
        # Some API responses put the tag in head_branch itself
        ref = r.get("display_title", "?")

    return {
        "ref": ref,
        "event": r.get("event", "?"),
        "status": r.get("status", "?"),
        "conclusion": r.get("conclusion") or r.get("status", "?"),
        "started_at": started,
        "duration_s": duration_s,
        "html_url": r.get("html_url", "#"),
        "sha": (r.get("head_sha") or "")[:7],
    }


def _semver_key(ref):
    """Sort key for semver tags; non-v* refs sort last."""
    if ref.startswith("v"):
        try:
            parts = re.findall(r"\d+", ref)
            return (0, tuple(int(p) for p in parts))
        except Exception:
            pass
    return (1, ref)


def latest_per_ref(runs):
    """Return ordered list of (ref, run_dict) — tags semver-desc, then main."""
    seen = {}
    for r in runs:
        ref = r["ref"]
        if ref not in seen:
            seen[ref] = r

    # Sort: v* tags semver desc, then main, then others
    tags = sorted([k for k in seen if k.startswith("v")],
                  key=lambda r: _semver_key(r), reverse=True)
    others = [k for k in seen if k == "main"]
    rest = sorted([k for k in seen if k != "main" and not k.startswith("v")])
    order = tags + others + rest
    return [(ref, seen[ref]) for ref in order]


# ---------------------------------------------------------------------------
# Local suite
# ---------------------------------------------------------------------------

def run_local_suite(repo_root):
    """Run tests/spec/run_all.py and return (summary_rows, all_ok, sha, dirty, raw_out, error)."""
    harness = os.path.join(repo_root, "tests", "spec", "run_all.py")
    if not os.path.exists(harness):
        return [], None, None, None, "", f"Harness not found: {harness}"

    # Get current sha + dirty flag
    sha, dirty = None, False
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        pass
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_root, text=True, stderr=subprocess.DEVNULL
        )
        dirty = bool(status.strip())
    except Exception:
        pass

    # Run the harness
    try:
        proc = subprocess.run(
            [sys.executable, harness],
            capture_output=True, text=True,
            cwd=repo_root, timeout=120
        )
        raw = proc.stdout + proc.stderr
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        return [], None, sha, dirty, "", "Spec suite timed out after 120s"
    except Exception as e:
        return [], None, sha, dirty, "", str(e)

    # Parse SUMMARY block
    # Format:
    #   SUMMARY
    #   ---...
    #     module_name   PASS/FAIL   12345 ms
    #   ---...
    #   n/N test modules passed => ALL GREEN / FAILURES PRESENT
    rows = []
    all_ok = None
    in_summary = False
    for line in raw.splitlines():
        if re.match(r"^SUMMARY\s*$", line):
            in_summary = True
            continue
        if in_summary:
            m = re.match(r"^\s+(\S+)\s+(PASS|FAIL)\s+([\d.]+)\s*ms", line)
            if m:
                rows.append({
                    "module": m.group(1),
                    "ok": m.group(2) == "PASS",
                    "ms": m.group(3),
                })
            if "ALL GREEN" in line or "FAILURES PRESENT" in line:
                all_ok = "ALL GREEN" in line

    if all_ok is None:
        all_ok = (rc == 0)

    return rows, all_ok, sha, dirty, raw, None


# ---------------------------------------------------------------------------
# Time formatting helpers
# ---------------------------------------------------------------------------

def _relative_time(iso_str):
    """Return '2h ago', '3d ago', etc."""
    try:
        t = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = now - t
        s = int(delta.total_seconds())
        if s < 60:
            return f"{s}s ago"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return iso_str[:16] if iso_str else "?"


def _fmt_duration(s):
    if s is None:
        return "—"
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"


def _fmt_local(iso_str):
    """Format UTC ISO string as local time."""
    try:
        t = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local = t.astimezone()
        return local.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return iso_str


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

CSS = """
:root {
  --bg: #0d1117;
  --bg2: #161b22;
  --bg3: #21262d;
  --border: #30363d;
  --text: #e6edf3;
  --text2: #8b949e;
  --green: #3fb950;
  --green-bg: #0d2818;
  --red: #f85149;
  --red-bg: #2d0f0e;
  --amber: #d29922;
  --amber-bg: #271f08;
  --link: #58a6ff;
  --mono: 'SF Mono', 'Fira Code', 'Consolas', 'Liberation Mono', monospace;
  --sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.5;
  padding: 0;
}
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }

/* Layout */
.page { max-width: 1100px; margin: 0 auto; padding: 24px 20px 60px; }

/* Header */
.header {
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 28px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.header h1 { font-size: 20px; font-weight: 600; }
.header .meta { color: var(--text2); font-size: 12px; }

/* Section */
.section { margin-bottom: 36px; }
.section h2 {
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text2);
  margin-bottom: 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

/* Cards */
.cards { display: flex; flex-wrap: wrap; gap: 12px; }
.card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  min-width: 200px;
  max-width: 280px;
  flex: 1 1 200px;
}
.card .status-icon { font-size: 22px; margin-bottom: 6px; }
.card .ref-name {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 4px;
  word-break: break-all;
}
.card .card-meta {
  color: var(--text2);
  font-size: 12px;
  font-family: var(--mono);
  margin-bottom: 6px;
}
.card .card-link { font-size: 12px; }

/* Status colors */
.s-success { color: var(--green); }
.s-failure { color: var(--red); }
.s-in_progress { color: var(--amber); }
.s-cancelled { color: var(--text2); }
.s-skipped { color: var(--text2); }
.s-unknown { color: var(--text2); }

/* Banner */
.banner {
  padding: 10px 16px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 14px;
  display: inline-block;
}
.banner-green { background: var(--green-bg); color: var(--green); border: 1px solid #1f4a2a; }
.banner-red { background: var(--red-bg); color: var(--red); border: 1px solid #5c1f1a; }
.banner-warn { background: var(--amber-bg); color: var(--amber); border: 1px solid #4a3800; }

/* Notice */
.notice {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-left: 3px solid var(--amber);
  padding: 10px 14px;
  border-radius: 4px;
  color: var(--text2);
  font-size: 13px;
  margin-bottom: 16px;
}

/* Tables */
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th {
  text-align: left;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text2);
  border-bottom: 1px solid var(--border);
}
td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--bg3); }
.mono { font-family: var(--mono); }
.sha { font-family: var(--mono); color: var(--text2); font-size: 12px; }
.dur { font-family: var(--mono); color: var(--text2); }
.tag-pass { color: var(--green); font-weight: 600; }
.tag-fail { color: var(--red); font-weight: 600; }
.tag-other { color: var(--text2); }

/* Local suite sha line */
.sha-line { font-family: var(--mono); font-size: 12px; color: var(--text2); margin-bottom: 10px; }
"""

SCRIPT = """
(function() {
  // Relative time live update — recalc every 60s
  function ago(iso) {
    var d = new Date(iso), now = new Date(), s = Math.floor((now - d) / 1000);
    if (s < 60) return s + 's ago';
    if (s < 3600) return Math.floor(s/60) + 'm ago';
    if (s < 86400) return Math.floor(s/3600) + 'h ago';
    return Math.floor(s/86400) + 'd ago';
  }
  function refresh() {
    document.querySelectorAll('[data-iso]').forEach(function(el) {
      el.textContent = ago(el.getAttribute('data-iso'));
    });
  }
  refresh();
  setInterval(refresh, 60000);
})();
"""


def _status_icon_class(conclusion):
    mapping = {
        "success": ("✓", "s-success"),
        "failure": ("✗", "s-failure"),
        "in_progress": ("●", "s-in_progress"),
        "queued": ("○", "s-in_progress"),
        "waiting": ("○", "s-in_progress"),
        "cancelled": ("⊘", "s-cancelled"),
        "skipped": ("–", "s-skipped"),
    }
    return mapping.get(conclusion, ("?", "s-unknown"))


def _conclusion_html(conclusion):
    icon, cls = _status_icon_class(conclusion)
    return f'<span class="{cls}">{html.escape(icon)} {html.escape(conclusion or "unknown")}</span>'


def render_html(
    runs,
    gh_error,
    local_rows,
    local_all_ok,
    local_sha,
    local_dirty,
    local_error,
    generated_at,
    no_github,
    no_local,
):
    """Build the full HTML string."""

    H = html.escape

    parts = []

    def w(s):
        parts.append(s)

    w(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>vaked spec verification</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
""")

    # --- Header ---
    repo_url = f"https://github.com/{REPO}"
    w(f"""<div class="header">
  <h1>&#x1F4CA; <a href="{H(repo_url)}">{H(REPO)}</a> &middot; spec verification</h1>
  <div class="meta">generated {H(generated_at)} &nbsp;&middot;&nbsp; <a href="{H(repo_url)}/actions">CI</a></div>
</div>
""")

    # --- GitHub notice / error ---
    if no_github:
        w('<div class="notice">&#9888; GitHub data skipped (--no-github).</div>\n')
    elif gh_error:
        w(f'<div class="notice">&#9888; GitHub API unavailable: {H(str(gh_error))}</div>\n')

    # --- Section A: Latest per ref ---
    if not no_github and not gh_error and runs:
        w('<div class="section">\n<h2>Latest per ref</h2>\n<div class="cards">\n')
        for ref, r in latest_per_ref(runs):
            icon, cls = _status_icon_class(r["conclusion"])
            dur = _fmt_duration(r["duration_s"])
            sha = r["sha"]
            url = r["html_url"]
            event = r["event"]
            w(f"""<div class="card">
  <div class="status-icon {H(cls)}">{H(icon)}</div>
  <div class="ref-name">{H(ref)}</div>
  <div class="card-meta">{H(dur)} &nbsp;&middot;&nbsp; {H(sha)} &nbsp;&middot;&nbsp; {H(event)}</div>
  <div class="card-link"><a href="{H(url)}" target="_blank" rel="noopener">view run &rarr;</a></div>
</div>
""")
        w('</div>\n</div>\n')
    elif not no_github and not gh_error:
        w('<div class="section"><h2>Latest per ref</h2><p style="color:var(--text2)">No runs found.</p></div>\n')

    # --- Section B: Local suite ---
    w('<div class="section">\n<h2>Local suite (this checkout)</h2>\n')
    if no_local:
        w('<div class="notice">&#9888; Local suite skipped (--no-local).</div>\n')
    elif local_error:
        w(f'<div class="notice">&#9888; Could not run local suite: {H(str(local_error))}</div>\n')
    else:
        # SHA + dirty flag
        sha_display = local_sha or "unknown"
        dirty_flag = " <span style='color:var(--amber)'>+dirty</span>" if local_dirty else ""
        w(f'<div class="sha-line">checkout: <span class="mono">{H(sha_display)}</span>{dirty_flag}</div>\n')

        # Banner
        if local_all_ok is True:
            w('<div class="banner banner-green">&#10003; ALL GREEN</div>\n')
        elif local_all_ok is False:
            w('<div class="banner banner-red">&#10007; FAILURES PRESENT</div>\n')
        else:
            w('<div class="banner banner-warn">&#9888; Result unknown</div>\n')

        if local_rows:
            w("""<table>
<thead><tr>
  <th>Module</th>
  <th>Status</th>
  <th>Time (ms)</th>
</tr></thead>
<tbody>
""")
            for row in local_rows:
                status_cls = "tag-pass" if row["ok"] else "tag-fail"
                status_label = "PASS" if row["ok"] else "FAIL"
                w(f"""<tr>
  <td class="mono">{H(row["module"])}</td>
  <td class="{H(status_cls)}">{H(status_label)}</td>
  <td class="dur">{H(str(row["ms"]))}</td>
</tr>
""")
            w("</tbody></table>\n")
        else:
            w('<p style="color:var(--text2);margin-top:8px">No summary rows parsed. Check suite output.</p>\n')

    w('</div>\n')

    # --- Section C: Run history ---
    if not no_github and not gh_error and runs:
        w('<div class="section">\n<h2>Run history (last 30)</h2>\n')
        w("""<table>
<thead><tr>
  <th>When</th>
  <th>Ref</th>
  <th>Event</th>
  <th>Conclusion</th>
  <th>Duration</th>
  <th>SHA</th>
  <th>Link</th>
</tr></thead>
<tbody>
""")
        for r in runs:
            iso = r["started_at"]
            w(f"""<tr>
  <td><span data-iso="{H(iso)}">{H(_relative_time(iso))}</span></td>
  <td class="mono">{H(r["ref"])}</td>
  <td class="mono">{H(r["event"])}</td>
  <td>{_conclusion_html(r["conclusion"])}</td>
  <td class="dur">{H(_fmt_duration(r["duration_s"]))}</td>
  <td class="sha">{H(r["sha"])}</td>
  <td><a href="{H(r["html_url"])}" target="_blank" rel="noopener">&#x2197;</a></td>
</tr>
""")
        w("</tbody></table>\n</div>\n")

    # --- Footer / script ---
    w(f"""</div>
<script>{SCRIPT}</script>
</body>
</html>""")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help=f"Output path (default: {DEFAULT_OUT})")
    parser.add_argument("--serve", nargs="?", const=DEFAULT_PORT, type=int, metavar="PORT",
                        help=f"Serve after writing (default port {DEFAULT_PORT})")
    parser.add_argument("--open", action="store_true",
                        help="Open in browser after writing")
    parser.add_argument("--no-local", action="store_true",
                        help="Skip running the local spec suite")
    parser.add_argument("--no-github", action="store_true",
                        help="Skip GitHub API calls")
    args = parser.parse_args()

    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Find repo root (two levels up from this file, or cwd fallback)
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(here))
    if not os.path.isdir(os.path.join(repo_root, "tests", "spec")):
        # Try cwd
        repo_root = os.getcwd()

    # GitHub
    runs = []
    gh_error = None
    if not args.no_github:
        print("Fetching GitHub runs...", end=" ", flush=True)
        raw_runs, gh_error = fetch_runs()
        if gh_error:
            print(f"WARN: {gh_error}")
        else:
            runs = [parse_run(r) for r in raw_runs]
            print(f"OK ({len(runs)} runs)")

    # Local suite
    local_rows, local_all_ok, local_sha, local_dirty, local_raw, local_error = \
        [], None, None, None, "", None
    if not args.no_local:
        print("Running local spec suite...", end=" ", flush=True)
        local_rows, local_all_ok, local_sha, local_dirty, local_raw, local_error = \
            run_local_suite(repo_root)
        if local_error:
            print(f"WARN: {local_error}")
        else:
            status = "ALL GREEN" if local_all_ok else "FAILURES PRESENT"
            print(f"OK ({status})")

    # Render
    html_out = render_html(
        runs=runs,
        gh_error=gh_error,
        local_rows=local_rows,
        local_all_ok=local_all_ok,
        local_sha=local_sha,
        local_dirty=local_dirty,
        local_error=local_error,
        generated_at=generated_at,
        no_github=args.no_github,
        no_local=args.no_local,
    )

    # Write output
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"Wrote {out_path} ({len(html_out)} bytes)")

    # --open
    if args.open and not args.serve:
        try:
            subprocess.run(["open", out_path], check=False)
        except Exception:
            pass

    # --serve
    if args.serve:
        port = args.serve
        serve_dir = os.path.dirname(out_path)
        url = f"http://localhost:{port}"
        print(f"Serving {serve_dir} at {url}")
        if args.open:
            try:
                subprocess.Popen(["open", url])
            except Exception:
                pass
        import http.server
        import functools
        Handler = functools.partial(
            http.server.SimpleHTTPRequestHandler,
            directory=serve_dir
        )
        with http.server.HTTPServer(("", port), Handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nStopped.")


if __name__ == "__main__":
    main()
