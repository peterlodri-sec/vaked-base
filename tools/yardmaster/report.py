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

import base64
import hashlib
import http.client
import json
import os
import ssl
import subprocess
import tempfile
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

# The fleet's self-hosted Mastodon — hardcoded default (override via MASTODON_BASE_URL).
MASTODON_DEFAULT_BASE = "https://social.crabcc.app"
# TLS public-key (SPKI) pin for the host above — base64(sha256(SubjectPublicKeyInfo)),
# HPKP "pin-sha256" form. None ⇒ standard CA verification only. Set the real pin
# here (or via MASTODON_SPKI_PIN) to pin the connection. Compute it on a normal
# network (NOT inside a MITM'd CI sandbox):
#   openssl s_client -connect social.crabcc.app:443 -servername social.crabcc.app </dev/null 2>/dev/null \
#     | openssl x509 -pubkey -noout | openssl pkey -pubin -outform der \
#     | openssl dgst -sha256 -binary | openssl enc -base64
_MASTODON_SPKI_PIN = None
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
# Finish the image before upload: compress → metadata/EXIF → Ed25519 signature.
# Every stage is best-effort (a missing CLI tool degrades, never raises); the
# manifest is the durable provenance (yardmaster also writes it to the eventd
# ledger). Verify: strip the embedded `UserComment`, sha256 the bytes → equals
# manifest.image_sha256, then openssl-verify the signature over the unsigned
# manifest with the embedded pubkey.
# --------------------------------------------------------------------------- #

_SIGNED_FIELDS = ("alg", "repo", "commit", "generated_at", "image_sha256", "signer")


def _run(cmd, inp=None):
    try:
        return subprocess.run(cmd, input=inp, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return None


def compress_png(png: bytes) -> bytes:
    """Shrink the infographic before upload. pngquant (lossy palette — ideal for
    a flat-colour graphic) → optipng → original. Strips metadata (re-added next)."""
    r = _run(["pngquant", "--strip", "--quality=40-95", "-"], png)
    if r is not None and r.returncode == 0 and r.stdout:
        return r.stdout
    return png


def _canon(d: dict) -> bytes:
    return json.dumps(d, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=False).encode("utf-8")


def _ed25519_sign(message: bytes, key_pem: str) -> "tuple[str, str] | tuple[None, None]":
    """Sign ``message`` with an Ed25519 private key (PEM) via openssl. Returns
    ``(sig_b64, pubkey_der_b64)`` or ``(None, None)``."""
    kp = mp = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as kf:
            kf.write(key_pem)
            kp = kf.name
        with tempfile.NamedTemporaryFile(delete=False) as mf:
            mf.write(message)
            mp = mf.name
        sig = _run(["openssl", "pkeyutl", "-sign", "-inkey", kp, "-rawin", "-in", mp])
        pub = _run(["openssl", "pkey", "-in", kp, "-pubout", "-outform", "DER"])
        if sig and sig.returncode == 0 and sig.stdout and pub and pub.stdout:
            return base64.b64encode(sig.stdout).decode(), base64.b64encode(pub.stdout).decode()
    except Exception:
        pass
    finally:
        for p in (kp, mp):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
    return None, None


def _exiftool_args(repo: str, tally: str, when_exif: str, year: str) -> list:
    return [
        "-Title=yardmaster: %s merge train" % repo,
        "-Description=%s" % tally,
        "-ImageDescription=%s" % tally,
        "-Artist=yardmaster",
        "-XMP-dc:Creator=yardmaster (vaked-base agent fleet)",
        "-Copyright=%s peterlodri-sec/vaked-base — CC BY 4.0" % year,
        "-Software=yardmaster/report.py",
        "-DateTimeOriginal=%s" % when_exif,
        "-CreateDate=%s" % when_exif,
        "-XMP-dc:Source=https://github.com/%s" % repo,
        "-XMP-dc:Subject=merge-train, vaked, yardmaster, fan-out",
    ]


def finalize_image(png: "bytes | None", repo: str, commit: str, tally: str
                   ) -> "tuple[bytes | None, dict]":
    """compress → embed metadata/EXIF → sign. Returns ``(bytes, manifest)``.
    The manifest is always returned (with ``image_sha256``); ``sig``/``pubkey``
    appear only when ``YARDMASTER_SIGNING_KEY`` (Ed25519 PEM) is set."""
    if not png:
        return png, {}
    now = datetime.now(timezone.utc)
    img = compress_png(png)
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(img)
            path = f.name
        # metadata + EXIF (best-effort)
        _run(["exiftool", "-q", "-overwrite_original"]
             + _exiftool_args(repo, tally[:240], now.strftime("%Y:%m:%d %H:%M:%S"),
                              now.strftime("%Y")) + [path])
        img = open(path, "rb").read()
        # provenance over the metadata-laden image
        manifest = {
            "alg": "sha256", "repo": repo, "commit": commit or "",
            "generated_at": now.replace(microsecond=0).isoformat(),
            "image_sha256": hashlib.sha256(img).hexdigest(), "signer": "yardmaster",
        }
        key = os.environ.get("YARDMASTER_SIGNING_KEY")
        if key:
            manifest["alg"] = "ed25519"
            sig, pub = _ed25519_sign(_canon({k: manifest[k] for k in _SIGNED_FIELDS}), key)
            if sig:
                manifest["sig"], manifest["pubkey"] = sig, pub
            else:
                manifest["alg"] = "sha256"        # signing failed → hash-only
        # embed the manifest (UserComment + a PNG Comment chunk)
        mtxt = _canon(manifest).decode("utf-8")
        _run(["exiftool", "-q", "-overwrite_original",
              "-UserComment=" + mtxt, "-PNG:Comment=" + mtxt, path])
        img = open(path, "rb").read()
        return img, manifest
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def verify_manifest(manifest: dict) -> bool:
    """Verify the Ed25519 signature over the unsigned manifest with its embedded
    pubkey (openssl). True for a valid ``ed25519`` manifest; False otherwise."""
    if manifest.get("alg") != "ed25519" or "sig" not in manifest or "pubkey" not in manifest:
        return False
    msg = _canon({k: manifest[k] for k in _SIGNED_FIELDS})
    pub = mp = sp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".der", delete=False) as pf:
            pf.write(base64.b64decode(manifest["pubkey"]))
            pub = pf.name
        with tempfile.NamedTemporaryFile(delete=False) as mf:
            mf.write(msg)
            mp = mf.name
        with tempfile.NamedTemporaryFile(delete=False) as sf:
            sf.write(base64.b64decode(manifest["sig"]))
            sp = sf.name
        r = _run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", pub,
                  "-keyform", "DER", "-rawin", "-in", mp, "-sigfile", sp])
        return bool(r and r.returncode == 0)
    except Exception:
        return False
    finally:
        for p in (pub, mp, sp):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass


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


def _spki_pin_b64(der_cert: bytes) -> "str | None":
    """base64(sha256(SubjectPublicKeyInfo)) of a DER leaf cert (the HPKP
    pin-sha256), via openssl. Survives cert renewal that reuses the key."""
    pub = _run(["openssl", "x509", "-inform", "DER", "-pubkey", "-noout"], der_cert)
    if not pub or pub.returncode != 0 or not pub.stdout:
        return None
    der = _run(["openssl", "pkey", "-pubin", "-outform", "DER"], pub.stdout)
    if not der or der.returncode != 0 or not der.stdout:
        return None
    return base64.b64encode(hashlib.sha256(der.stdout).digest()).decode()


def _mastodon_pin() -> "str | None":
    return os.environ.get("MASTODON_SPKI_PIN") or _MASTODON_SPKI_PIN


def _issuer_str(cert: dict) -> str:
    return ", ".join("%s=%s" % (k, v) for rdn in cert.get("issuer", ()) for k, v in rdn)


def _https(method: str, url: str, headers: dict, body: bytes,
           timeout: int = 30) -> "tuple[int, bytes]":
    """HTTPS with standard CA verification PLUS egress-aware SPKI pinning.

    When a pin is configured, the peer's SubjectPublicKeyInfo must match — UNLESS
    the (already CA-validated) peer is the trusted TLS-terminating egress gateway,
    identified by its issuer marker (default ``"Egress Gateway"``; set
    ``MASTODON_PIN_BYPASS_ISSUER``). You cannot pin *through* a terminating proxy
    — you only ever see its cert — so on a direct connection the pin is enforced,
    and behind the gateway it degrades to CA-trust-only (the gateway validates the
    upstream cert itself). The bypass can't be forged remotely: it requires a
    CA-valid cert from that issuer, whose CA is only in the sandbox trust store."""
    u = urllib.parse.urlsplit(url)
    conn = http.client.HTTPSConnection(u.hostname, u.port or 443,
                                       context=ssl.create_default_context(),
                                       timeout=timeout)
    try:
        conn.connect()
        pin = _mastodon_pin()
        if pin:
            mark = os.environ.get("MASTODON_PIN_BYPASS_ISSUER", "Egress Gateway")
            issuer = _issuer_str(conn.sock.getpeercert() or {})    # CA-validated dict
            if mark and mark in issuer:
                import sys as _sys
                _sys.stderr.write("[report] SPKI pin bypassed behind trusted egress "
                                  "gateway (%s); CA trust preserved upstream\n" % issuer)
            else:
                got = _spki_pin_b64(conn.sock.getpeercert(binary_form=True))
                if got != pin:
                    raise ssl.SSLError("TLS SPKI pin mismatch for %s (got %r, want %r)"
                                       % (u.hostname, got, pin))
        path = u.path + (("?" + u.query) if u.query else "")
        conn.request(method, path, body=body, headers=headers)
        r = conn.getresponse()
        return r.status, r.read()
    finally:
        conn.close()


def post_mastodon(text: str, png: "bytes | None") -> bool:
    token = os.environ.get("MASTODON_ACCESS_TOKEN")
    if not token:
        return False
    # NB: `or`, not `.get(key, default)` — an unset secret arrives as an EMPTY
    # string (present but blank), which would build a schemeless URL.
    base = (os.environ.get("MASTODON_BASE_URL") or MASTODON_DEFAULT_BASE).rstrip("/")
    visibility = os.environ.get("MASTODON_VISIBILITY") or "unlisted"
    auth = {"Authorization": "Bearer " + token}
    try:                                      # whole body guarded — never raises
        media_ids = []
        if png:
            try:
                boundary, body = _multipart([("file", "train.png", png, "image/png")])
                st, resp = _https("POST", base + "/api/v2/media",
                                  dict(auth, **{"Content-Type":
                                       "multipart/form-data; boundary=" + boundary}),
                                  body)
                if st in (200, 202):
                    mid = json.loads(resp or b"{}").get("id")
                    if mid:
                        media_ids.append(str(mid))
            except Exception:
                media_ids = []                # degrade to text-only
        fields = [("status", text), ("visibility", visibility)]
        for mid in media_ids:
            fields.append(("media_ids[]", mid))
        body = urllib.parse.urlencode(fields).encode()
        st, _resp = _https("POST", base + "/api/v1/statuses",
                           dict(auth, **{"Content-Type":
                                "application/x-www-form-urlencoded"}), body)
        return st in (200, 201)
    except Exception:
        return False


# --------------------------------------------------------------------------- #

def announce(repo: str, planned: list, mode: str, did: "dict | None" = None,
             commit: str = "") -> dict:
    """Build the report + infographic, finish the image (compress → metadata/EXIF
    → sign), and broadcast to both channels. Returns the outcome flags + the
    provenance manifest (which the caller also writes to the eventd ledger).
    Never raises."""
    text = build_text(repo, planned, mode, did)
    caption = build_caption(repo, planned, mode, did)
    c = _counts(planned)
    tally = ("%d merge, %d update, %d wait, %d block, %d hold over %d PR(s)"
             % (c["merge"], c["update_branch"], c["wait"], c["block_conflict"],
                c["skip"], len(planned)))
    img, manifest = finalize_image(render_png(build_svg(repo, planned, mode)),
                                   repo, commit, tally)
    return {
        "telegram": post_telegram(text),
        "mastodon": post_mastodon(caption, img),
        "image_bytes": len(img) if img else 0,
        "provenance": manifest,
        "signed": manifest.get("alg") == "ed25519" and "sig" in manifest,
    }
