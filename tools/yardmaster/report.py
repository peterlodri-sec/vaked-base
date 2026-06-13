"""yardmaster.report — always-on broadcast of the merge train.

Every tick yardmaster announces the train to **both** channels as
``yardmaster:<repo>``:

  * **Telegram** — the full emoji status report (one line per car + counts).
  * **Mastodon** — a short caption **plus a real infographic picture**: a
    deterministic SVG of the train (a locomotive + one colour-coded car per PR,
    on a track), rasterized to PNG. The image is data-accurate (not LLM-drawn);
    a missing rasterizer degrades to a text-only toot, never a failed run.

All posting is BEST-EFFORT and secret-guarded (mirrors the fleet convention):
any missing key or transport error is swallowed and reported in the return
value — the broadcast must never fail the train. Credentials come from the `ci`
GitHub Environment: ``MASTODON_BASE_URL`` / ``MASTODON_ACCESS_TOKEN`` /
``MASTODON_VISIBILITY``; ``TELEGRAM_TOKEN`` / ``TELEGRAM_TO``. Stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

MASTODON_DEFAULT_BASE = "https://social.crabcc.app"
MASTODON_MAX_CHARS = 480

# action → (emoji, short label, infographic fill colour)
_ACTION = {
    "merge":          ("✅", "merge",     "#2ea043"),
    "update_branch":  ("🔄", "update",    "#1f6feb"),
    "wait":           ("⏳", "wait",      "#d29922"),
    "block_conflict": ("⛔", "conflict",  "#da3633"),
    "skip":           ("⏸", "hold/skip", "#6e7681"),
}


def _style(action: str):
    return _ACTION.get(action, ("•", action, "#6e7681"))


# --------------------------------------------------------------------------- #
# Text report (Telegram = full; Mastodon caption = summary).
# --------------------------------------------------------------------------- #

def _counts(planned: list) -> dict:
    c = {k: 0 for k in _ACTION}
    for _, a, _ in planned:
        c[a] = c.get(a, 0) + 1
    return c


def build_text(repo: str, planned: list, mode: str, did: "dict | None") -> str:
    """The full emoji status report (Telegram)."""
    lines = ["🚂 yardmaster:%s" % repo,
             "mode: %s · %d open PR(s)" % (mode, len(planned)), ""]
    for n, action, reason in planned:
        emoji, label, _ = _style(action)
        lines.append("%s #%-4d %-9s %s" % (emoji, n, label, reason))
    c = _counts(planned)
    lines.append("")
    if did and did.get("action") not in (None, "idle", "settled", "paused"):
        de, dl, _ = _style(did.get("action", ""))
        lines.append("did: %s %s #%s (%s)" % (de, dl, did.get("pr"),
                                              "dry-run" if did.get("note") else "live"))
    lines.append("🟢%d ✅merge · 🔵%d 🔄update · 🟡%d ⏳wait · 🔴%d ⛔block · ⚪%d ⏸hold"
                 % (c["merge"], c["update_branch"], c["wait"],
                    c["block_conflict"], c["skip"]))
    return "\n".join(lines)


def build_caption(repo: str, planned: list, mode: str, did: "dict | None") -> str:
    """The short Mastodon caption (the per-PR detail rides the infographic)."""
    c = _counts(planned)
    head = "🚂 yardmaster:%s — %s" % (repo, mode)
    tally = ("✅%d merge · 🔄%d update · ⏳%d wait · ⛔%d block · ⏸%d hold (%d PRs)"
             % (c["merge"], c["update_branch"], c["wait"], c["block_conflict"],
                c["skip"], len(planned)))
    extra = ""
    if did and did.get("action") not in (None, "idle", "settled", "paused"):
        de, dl, _ = _style(did.get("action", ""))
        extra = "\n%s %s #%s this tick" % (de, dl, did.get("pr"))
    text = "%s\n%s%s" % (head, tally, extra)
    return text[:MASTODON_MAX_CHARS]


# --------------------------------------------------------------------------- #
# Infographic — deterministic SVG of the train, rasterized to PNG.
# --------------------------------------------------------------------------- #

def build_svg(repo: str, planned: list, mode: str) -> str:
    """An accurate infographic: a locomotive + one colour-coded car per PR on a
    track, a legend, and a footer. No emoji glyphs (so it renders without an
    emoji font); status is carried by colour + label."""
    car_w, car_h, gap = 150, 70, 26
    margin, loco_w = 40, 110
    n = len(planned)
    width = max(900, margin * 2 + loco_w + gap + n * (car_w + gap))
    height = 300
    track_y = 150
    bg, fg, sub = "#0d1117", "#e6edf3", "#7d8590"

    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    p = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
         'viewBox="0 0 %d %d" font-family="DejaVu Sans, Arial, sans-serif">'
         % (width, height, width, height)]
    p.append('<rect width="100%%" height="100%%" fill="%s"/>' % bg)
    p.append('<text x="%d" y="48" fill="%s" font-size="30" font-weight="bold">'
             'yardmaster &#8226; %s</text>' % (margin, fg, esc(repo)))
    p.append('<text x="%d" y="74" fill="%s" font-size="17">merge train &#8226; %s</text>'
             % (margin, sub, esc(mode)))
    # track
    p.append('<rect x="%d" y="%d" width="%d" height="6" rx="3" fill="#30363d"/>'
             % (margin, track_y + car_h - 4, width - 2 * margin, ))
    # locomotive
    lx = margin
    p.append('<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="#1f2937" '
             'stroke="#30363d"/>' % (lx, track_y, loco_w, car_h))
    p.append('<circle cx="%d" cy="%d" r="9" fill="#30363d"/>'
             % (lx + 28, track_y + car_h + 6))
    p.append('<circle cx="%d" cy="%d" r="9" fill="#30363d"/>'
             % (lx + loco_w - 28, track_y + car_h + 6))
    p.append('<text x="%d" y="%d" fill="%s" font-size="34" text-anchor="middle">'
             '&#9650;</text>' % (lx + loco_w // 2, track_y + 30, fg))
    p.append('<text x="%d" y="%d" fill="%s" font-size="14" text-anchor="middle">'
             'yardmaster</text>' % (lx + loco_w // 2, track_y + 54, sub))
    # cars
    x = lx + loco_w + gap
    for num, action, _reason in planned:
        _emoji, label, fill = _style(action)
        p.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#30363d" '
                 'stroke-width="4"/>' % (x - gap, track_y + car_h // 2, x,
                                         track_y + car_h // 2))
        p.append('<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="%s"/>'
                 % (x, track_y, car_w, car_h, fill))
        p.append('<circle cx="%d" cy="%d" r="8" fill="#30363d"/>'
                 % (x + 26, track_y + car_h + 6))
        p.append('<circle cx="%d" cy="%d" r="8" fill="#30363d"/>'
                 % (x + car_w - 26, track_y + car_h + 6))
        p.append('<text x="%d" y="%d" fill="#0d1117" font-size="26" '
                 'font-weight="bold" text-anchor="middle">#%s</text>'
                 % (x + car_w // 2, track_y + 32, esc(num)))
        p.append('<text x="%d" y="%d" fill="#0d1117" font-size="16" '
                 'text-anchor="middle">%s</text>'
                 % (x + car_w // 2, track_y + 54, esc(label)))
        x += car_w + gap
    # legend + footer
    ly = 250
    lx2 = margin
    for action in ("merge", "update_branch", "wait", "block_conflict", "skip"):
        _e, label, fill = _style(action)
        p.append('<rect x="%d" y="%d" width="18" height="18" rx="4" fill="%s"/>'
                 % (lx2, ly - 14, fill))
        p.append('<text x="%d" y="%d" fill="%s" font-size="15">%s</text>'
                 % (lx2 + 24, ly, sub, esc(label)))
        lx2 += 40 + 8 * len(label) + 30
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p.append('<text x="%d" y="%d" fill="%s" font-size="14" text-anchor="end">%s</text>'
             % (width - margin, ly, sub, stamp))
    p.append("</svg>")
    return "".join(p)


def render_png(svg_text: str) -> "bytes | None":
    """Rasterize SVG → PNG with whatever is on PATH (``rsvg-convert`` →
    ImageMagick ``convert`` → ``cairosvg``). Returns None if none is available
    (the toot then goes out text-only)."""
    data = svg_text.encode("utf-8")
    for cmd in (["rsvg-convert", "-w", "1200", "-f", "png"],
                ["convert", "-background", "none", "svg:-", "png:-"]):
        try:
            out = subprocess.run(cmd, input=data, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, check=True).stdout
            if out:
                return out
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    try:
        import cairosvg  # type: ignore
        return cairosvg.svg2png(bytestring=data, output_width=1200)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Transports (best-effort; never raise).
# --------------------------------------------------------------------------- #

def post_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_TO")
    if not token or not chat:
        return False
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendMessage" % token, data=body)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


def _multipart(files) -> "tuple[str, bytes]":
    boundary = "----yardmaster" + uuid.uuid4().hex
    buf = bytearray()
    for name, filename, data, ctype in files:
        buf += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                % (boundary, name, filename, ctype)).encode()
        buf += data + b"\r\n"
    buf += ("--%s--\r\n" % boundary).encode()
    return boundary, bytes(buf)


def post_mastodon(text: str, png: "bytes | None") -> bool:
    token = os.environ.get("MASTODON_ACCESS_TOKEN")
    if not token:
        return False
    base = os.environ.get("MASTODON_BASE_URL", MASTODON_DEFAULT_BASE).rstrip("/")
    visibility = os.environ.get("MASTODON_VISIBILITY", "unlisted")
    media_ids = []
    if png:
        try:
            boundary, body = _multipart(
                [("file", "train.png", png, "image/png")])
            req = urllib.request.Request(base + "/api/v2/media", data=body)
            req.add_header("Authorization", "Bearer " + token)
            req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
            with urllib.request.urlopen(req, timeout=30) as r:
                mid = json.loads(r.read()).get("id")
                if mid:
                    media_ids.append(str(mid))
        except Exception:
            media_ids = []                    # degrade to text-only
    fields = [("status", text), ("visibility", visibility)]
    for mid in media_ids:
        fields.append(("media_ids[]", mid))
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(base + "/api/v1/statuses", data=body)
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status in (200, 201)
    except Exception:
        return False


# --------------------------------------------------------------------------- #

def announce(repo: str, planned: list, mode: str, did: "dict | None" = None) -> dict:
    """Build the report + infographic and broadcast to both channels. Returns
    ``{telegram, mastodon, image}`` outcome flags. Never raises."""
    text = build_text(repo, planned, mode, did)
    caption = build_caption(repo, planned, mode, did)
    png = render_png(build_svg(repo, planned, mode))
    return {
        "telegram": post_telegram(text),
        "mastodon": post_mastodon(caption, png),
        "image": png is not None,
    }
