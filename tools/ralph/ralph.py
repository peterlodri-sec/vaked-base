#!/usr/bin/env python3
"""ralph — decision/strategy loop (decide / run / watch).

The core is Python stdlib only. Langfuse tracing is an OPTIONAL extra: it is
imported lazily and every call is guarded, so the loop runs identically with
zero third-party deps. Enable it with the `tracing` extra + LANGFUSE_* env:
    uv run --project tools/ralph --extra tracing tools/ralph/ralph.py …
"""
from __future__ import annotations
import argparse
import base64
import binascii
import datetime
import functools
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ralphcore as C  # noqa: E402

try:                                  # optional observability — never required
    from langfuse import Langfuse as _Langfuse
except Exception:                     # not installed → tracing is a no-op
    _Langfuse = None

try:                                  # optional fast JSON — falls back to stdlib
    import orjson as _orjson
except Exception:
    _orjson = None

try:                                  # optional image compression for toot media
    from PIL import Image as _PILImage
except Exception:                     # not installed → upload the raw image as-is
    _PILImage = None


def _loads(data):
    """Fast JSON parse — orjson when installed, stdlib otherwise. Accepts str or
    bytes. orjson.JSONDecodeError subclasses json.JSONDecodeError, so existing
    `except json.JSONDecodeError` handlers still catch malformed input. Used for
    DESERIALIZATION only; the hash-chained ledger keeps stdlib json.dumps so the
    committed canonical bytes (and their hashes) never shift."""
    if _orjson is not None:
        return _orjson.loads(data)
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    return _STD_JSON_LOADS(data)


_STD_JSON_LOADS = json.loads

REPO_HOME = os.path.abspath(os.path.join(HERE, "..", ".."))   # vaked-base
DECISIONS_DIR = os.path.join(REPO_HOME, "docs", "decisions")
STATE_DIR = os.path.join(HERE, "state")
STATUS_PATH = os.path.join(STATE_DIR, "status.json")
CONTROL_PATH = os.path.join(STATE_DIR, "control.json")
EVENTS_PATH = os.path.join(STATE_DIR, "events.jsonl")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PURPOSE_PATH = os.path.join(HERE, "PURPOSE.md")
DEFAULT_S1 = "qwen/qwen3-235b-a22b-thinking-2507"
DEFAULT_S2 = "deepseek/deepseek-v4-flash"
HOME_GH = "peterlodri-sec/vaked-base"   # tracks read issues from the home repo
MASTODON_DEFAULT_BASE = "https://social.crabcc.app"   # private, self-hosted
MASTODON_MAX_CHARS = 470                # safety margin under Mastodon's 500
ANNOUNCE_MODEL = "openai/gpt-oss-120b"  # writes the toot (separate from decide)
ANNOUNCE_LOOKBACK = 5                   # how far back to retry un-announced decisions
TOOT_IMAGE_MODEL = "google/gemini-2.5-flash-image"  # generates the toot's media
CRITIQUE_CONTEXT_CHARS = 32000          # cap grounding context for the stage-3 critique
WRITER_MAX_TOKENS = 4000                # stage-2/3 entry budget (2200 truncated the critique)


def read_purpose() -> str:
    """The PURPOSE.md mission preamble injected into every stage-1 call. Empty
    string if absent (the loop still works, just without the goal preamble)."""
    try:
        with open(PURPOSE_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


# Endpoint + key resolution (OpenRouter by default; override to a self-hosted,
# trust-boundary endpoint — e.g. agentfield-inference-host — to avoid sending
# private-repo content to a third party).  Precedence: explicit arg > env > default.
def _resolve_base_url(explicit: "str | None" = None) -> str:
    return explicit or os.environ.get("RALPH_BASE_URL") or OPENROUTER_URL


def _resolve_api_key() -> str:
    return os.environ.get("RALPH_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or ""


# ---------------------------------------------------------------------------
# Optional Langfuse tracing — lazily initialized, fully guarded. Returns None
# (a no-op) unless the SDK is installed AND LANGFUSE_PUBLIC_KEY is set, so the
# loop's behaviour is identical with or without observability.
# ---------------------------------------------------------------------------

_LF_CLIENT = None
_LF_INIT = False


def _langfuse():
    """The Langfuse client, or None when tracing is unavailable/unconfigured."""
    global _LF_CLIENT, _LF_INIT
    if not _LF_INIT:
        _LF_INIT = True
        if _Langfuse is not None and os.environ.get("LANGFUSE_PUBLIC_KEY"):
            try:
                _LF_CLIENT = _Langfuse()   # reads LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST
            except Exception:
                _LF_CLIENT = None
    return _LF_CLIENT


def _flush_langfuse() -> None:
    """Flush buffered spans before exit (no-op when tracing is off)."""
    client = _langfuse()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Mastodon announcements (the `announce` subcommand). Posts a caveman-style,
# hashtagged, <=470-char toot for the latest decision to a private, self-hosted
# instance. Runs AFTER the decision is committed, so it can FAIL FAST and LOUD
# (CI red + a deduped GitHub issue) without ever dropping a decision. No-op when
# MASTODON_ACCESS_TOKEN is unset. Idempotent: one toot per decision id.
# ---------------------------------------------------------------------------

# Caveman-style post generator prompt (distilled from .claude/skills/caveman).
_TOOT_SYS = (
    "You write ONE short social post (a Mastodon 'toot') announcing a single "
    "design decision from the 'ralph' autonomous loop. Write in TERSE CAVEMAN "
    "STYLE: drop articles (a/an/the) and filler (just/really/basically); "
    "fragments OK; short punchy words. Pattern: '[thing] [action] [reason]. "
    "[next].'. Keep technical terms, names and identifiers EXACT. No emoji, no "
    "@mentions, no URLs, no hashtags (added later). Never mention you are a "
    "caveman or a model. Output ONLY the post text, at most {limit} characters."
)


def _toot_hashtags(track_name: str) -> list[str]:
    tag = re.sub(r"[^a-z0-9]", "", track_name.lower())
    return ["#vaked", "#ralph"] + (["#" + tag] if tag else [])


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())          # collapse whitespace/newlines
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + "…"


_MD_FENCE_RE = re.compile(r"```.*?```", re.S)            # code fences
_MD_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s*")    # headings
_MD_BULLET_RE = re.compile(r"(?m)^\s{0,3}[-*+]\s+")      # bullets
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")       # [txt](url) → txt


def _strip_md(text: str) -> str:
    """Mastodon renders plain text, NOT markdown — strip the markup that would
    otherwise show as literal `**`, `#`, `` ` `` in the toot."""
    if not text:
        return ""
    t = _MD_FENCE_RE.sub("", text)
    t = t.replace("**", "").replace("__", "").replace("`", "")
    t = _MD_HEADING_RE.sub("", t)
    t = _MD_BULLET_RE.sub("", t)
    t = _MD_LINK_RE.sub(r"\1", t)
    return t.strip()


def _clean_title(title: str) -> str:
    """A clean, label-free one-line title for the toot."""
    t = _strip_md(title)
    t = re.sub(r"^\s*decision\s*/?\s*question\s*:?\s*", "", t, flags=re.I)
    return " ".join(t.split()).strip()


def _decision_link(track_name: str) -> str:
    """Web link to the track's decision log (private repo — for the team)."""
    if not HOME_GH or "/" not in HOME_GH:
        return ""
    return "https://github.com/%s/blob/main/docs/decisions/%s.ralph-log.md" % (
        HOME_GH, track_name)


def _generate_toot(track_name: str, n: int, title: str, model: str, cost: float,
                   api_key: str, base_url: "str | None") -> str:
    """Build the toot: a caveman body (gpt-oss when a key is set, else a
    deterministic fallback), then a code-controlled tail — the decision id
    ``[track#N]`` (grep back to the log), a link, and hashtags — so the post is
    ALWAYS valid and <= MASTODON_MAX_CHARS regardless of what the model returns."""
    did = f"{track_name}#{n}"
    title = _clean_title(title)
    link = _decision_link(track_name)
    tail = " [%s]" % did
    if link:
        tail += "\n" + link
    tail += "\n\n" + " ".join(_toot_hashtags(track_name))
    budget = MASTODON_MAX_CHARS - len(tail)
    body = ""
    if api_key:
        try:
            resp = openrouter_call(
                ANNOUNCE_MODEL,
                [{"role": "system", "content": _TOOT_SYS.format(limit=budget)},
                 {"role": "user", "content":
                     "decision #%d · track '%s'\ntitle: %s\nmodel: %s · cost ~$%.4f\n"
                     "advisory — human must ratify." % (n, track_name, title, model, cost)}],
                api_key=api_key, temperature=0.7, max_tokens=800,
                reasoning={"effort": "low"}, base_url=base_url,
                span_name="ralph.toot", span_meta={"track": track_name, "id": did})
            body = _strip_md((_message_content(resp) or "").strip())
            if not body:
                print("[announce] toot gen empty (finish=%s) — using fallback"
                      % _finish_reason(resp), file=sys.stderr)
        except Exception as e:   # noqa: BLE001 — gen is best-effort; fall back
            print("[announce] toot generation failed (%s) — using fallback"
                  % type(e).__name__, file=sys.stderr)
    if not body:
        body = "ralph pick top decision for %s — %s. human say yes-or-no." % (
            track_name, title)
    return _truncate(body, budget) + tail


def _rate_limit_wait(exc, default: int = 5, cap: int = 60) -> int:
    """Seconds to wait before retrying a 429, from Retry-After or Mastodon's
    X-RateLimit-Reset (ISO-8601). Bounded by `cap` to keep fail-fast."""
    headers = getattr(exc, "headers", None) or {}
    ra = headers.get("Retry-After")
    if ra:
        try:
            return min(cap, max(1, int(float(ra))))
        except ValueError:
            pass
    reset = headers.get("X-RateLimit-Reset")
    if reset:
        try:
            t = datetime.datetime.fromisoformat(reset.replace("Z", "+00:00"))
            secs = (t - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            return min(cap, max(1, int(secs)))
        except (ValueError, TypeError):
            pass
    return default


def _post_toot(host: str, token: str, text: str, visibility: str, idem_key: str,
               *, language: str = "en", spoiler_text: "str | None" = None,
               media_ids: "list[str] | None" = None, retries: int = 3) -> dict:
    """POST one status, up to `retries` times. Honors Mastodon rate limiting
    (429 → wait per Retry-After / X-RateLimit-Reset) and retries transient 5xx /
    network errors with backoff; raises on the final failure (fail fast). The
    same Idempotency-Key across attempts makes retries safe (no double-post)."""
    fields = [("status", text), ("visibility", visibility), ("language", language)]
    if spoiler_text:
        fields.append(("spoiler_text", spoiler_text))
    for mid in (media_ids or []):           # repeated media_ids[] = array form-encoding
        fields.append(("media_ids[]", mid))
    data = urllib.parse.urlencode(fields).encode()
    headers = {"Authorization": "Bearer " + token,
               "Content-Type": "application/x-www-form-urlencoded",
               "Idempotency-Key": "ralph-" + idem_key}
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(host + "/api/v1/statuses", data=data,
                                         method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return _loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if attempt == retries - 1:
                raise
            if e.code == 429:
                wait = _rate_limit_wait(e)
                print("[announce] 429 rate-limited; wait %ds (attempt %d/%d)"
                      % (wait, attempt + 1, retries))
                time.sleep(wait)
            elif 500 <= e.code < 600:
                time.sleep(2 ** attempt)
            else:
                raise   # 4xx (bad request/auth) — don't retry
        except urllib.error.URLError as e:
            last = e
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise last   # pragma: no cover


# ---------------------------------------------------------------------------
# Toot image: generate ONE picture per post with an OpenRouter image model, then
# upload it to Mastodon as media. Entirely BEST-EFFORT — any failure (no key,
# model error, unparseable data, upload/processing failure) degrades silently to
# a text-only toot; the image must NEVER block or fail the announcement.
# ---------------------------------------------------------------------------

# An image prompt grounded in the decision + the Vaked language concept. No text
# in the picture (models render words badly) — pure abstract graph motif.
_IMAGE_PROMPT = (
    "Abstract minimalist poster illustration for a software design decision. "
    "Subject: {title}. Theme: 'Vaked' — a capability-graph language where a "
    "declaration compiles to a typed semantic graph: nodes, typed edges, "
    "capabilities, supervision and enforcement layers. Style: clean flat vector, "
    "geometric directed-graph motifs, deep indigo and teal palette on dark, "
    "subtle glow, high contrast, square composition. Absolutely NO text, NO "
    "words, NO letters, NO numbers, NO logos."
)
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<b64>.+)$", re.S)
_IMG_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}
TOOT_IMAGE_MAX_EDGE = 1280              # downscale the longest side to this (px)
TOOT_IMAGE_JPEG_QUALITY = 82           # re-encode to progressive JPEG at this quality


def _compress_image(raw: bytes, mime: str) -> "tuple[bytes, str]":
    """Shrink the generated image before upload: downscale the longest edge to
    TOOT_IMAGE_MAX_EDGE and re-encode as an optimized progressive JPEG. A model
    PNG is often ~800 KB; this typically lands ~100-200 KB. Best-effort — if
    Pillow is absent, the result would be larger, or anything errors, returns the
    original bytes unchanged (the image is never dropped over compression)."""
    if _PILImage is None:
        return raw, mime
    try:
        import io
        with _PILImage.open(io.BytesIO(raw)) as im:
            im = im.convert("RGB")                       # JPEG has no alpha
            w, h = im.size
            longest = max(w, h)
            if longest > TOOT_IMAGE_MAX_EDGE:
                scale = TOOT_IMAGE_MAX_EDGE / float(longest)
                im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                               _PILImage.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=TOOT_IMAGE_JPEG_QUALITY,
                    optimize=True, progressive=True)
            out = buf.getvalue()
        if out and len(out) < len(raw):
            return out, "image/jpeg"
        return raw, mime                                 # no win → keep original
    except Exception as e:   # noqa: BLE001 — compression is optional
        print("[announce] image compression failed (%s) — uploading original"
              % type(e).__name__, file=sys.stderr)
        return raw, mime


def _toot_image_on() -> bool:
    """Image-per-toot is on by default; RALPH_TOOT_IMAGE=off|0|false disables it."""
    return os.environ.get("RALPH_TOOT_IMAGE", "").strip().lower() not in ("0", "off", "false", "no")


def _first_image_url(resp: dict) -> "str | None":
    """The first generated image's data URL, at OpenRouter's documented path
    choices[0].message.images[].image_url.url (tolerant of shape variations)."""
    try:
        msg = resp["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None
    for img in (msg.get("images") or []):
        if not isinstance(img, dict):
            continue
        iu = img.get("image_url")
        url = iu.get("url") if isinstance(iu, dict) else (iu if isinstance(iu, str) else None)
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def _decode_data_url(url: str) -> "tuple[bytes, str] | None":
    """(raw_bytes, mime) from a base64 data URL, or None if it isn't one / is
    empty / fails to decode."""
    m = _DATA_URL_RE.match((url or "").strip())
    if not m:
        return None
    try:
        raw = base64.b64decode(m.group("b64"), validate=False)
    except (binascii.Error, ValueError):
        return None
    if not raw:
        return None
    return raw, (m.group("mime") or "image/png").lower()


def _generate_image(title: str, model: str, api_key: str,
                    base_url: "str | None") -> "tuple[bytes, str] | None":
    """Generate ONE image for the toot via an OpenRouter image model. Returns
    (raw_bytes, mime) or None. Best-effort: any failure returns None so the toot
    still posts text-only."""
    if not api_key:
        return None
    prompt = _IMAGE_PROMPT.format(title=_clean_title(title)[:200] or "a design decision")
    try:
        resp = openrouter_call(
            model, [{"role": "user", "content": prompt}],
            api_key=api_key, temperature=0.9, max_tokens=4096,
            modalities=["image", "text"], base_url=base_url,
            span_name="ralph.toot-image", span_meta={"model": model})
    except Exception as e:   # noqa: BLE001 — image is optional
        print("[announce] image generation failed (%s) — text-only toot"
              % type(e).__name__, file=sys.stderr)
        return None
    url = _first_image_url(resp)
    if not url:
        print("[announce] image gen returned no image (finish=%s) — text-only toot"
              % _finish_reason(resp), file=sys.stderr)
        return None
    decoded = _decode_data_url(url)
    if decoded is None:
        print("[announce] image data URL unparseable — text-only toot", file=sys.stderr)
    return decoded


def _multipart(fields: "dict[str, str]", file_field: str, filename: str,
               mime: str, content: bytes) -> "tuple[bytes, str]":
    """Build a multipart/form-data body (stdlib only). Returns (body, content_type)."""
    boundary = "----ralph" + uuid.uuid4().hex
    bb = boundary.encode()
    nl = b"\r\n"
    out = bytearray()
    for k, v in fields.items():
        out += b"--" + bb + nl
        out += ('Content-Disposition: form-data; name="%s"' % k).encode() + nl + nl
        out += str(v).encode("utf-8") + nl
    out += b"--" + bb + nl
    out += ('Content-Disposition: form-data; name="%s"; filename="%s"'
            % (file_field, filename)).encode() + nl
    out += ("Content-Type: %s" % mime).encode() + nl + nl
    out += content + nl
    out += b"--" + bb + b"--" + nl
    return bytes(out), "multipart/form-data; boundary=" + boundary


def _await_media(host: str, token: str, mid: str, *, tries: int = 12,
                 delay: int = 2) -> bool:
    """Poll GET /api/v1/media/:id until a 202-processing upload is ready. 200 =
    ready; 206 (still processing) is a 2xx, so urlopen returns it without raising
    and we just retry. Bounded; any HTTPError (e.g. 422 failed) gives up."""
    headers = {"Authorization": "Bearer " + token}
    for _ in range(tries):
        try:
            req = urllib.request.Request(host + "/api/v1/media/" + mid, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    return True
                # 206 Partial Content (still processing) → fall through and retry.
        except Exception:
            return False
        time.sleep(delay)
    return False


def _upload_media(host: str, token: str, content: bytes, mime: str,
                  alt: str) -> "str | None":
    """Upload one image (POST /api/v2/media) and return its media id, polling
    briefly if it 202-processes. Best-effort: None on any failure."""
    ext = _IMG_EXT.get(mime, "png")
    body, ctype = _multipart({"description": (alt or "")[:1400]}, "file",
                             "ralph." + ext, mime, content)
    headers = {"Authorization": "Bearer " + token, "Content-Type": ctype}
    try:
        req = urllib.request.Request(host + "/api/v2/media", data=body,
                                     method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            obj = _loads(resp.read().decode("utf-8"))
            code = resp.status
    except Exception as e:   # noqa: BLE001 — media is optional
        print("[announce] media upload failed (%s) — text-only toot"
              % type(e).__name__, file=sys.stderr)
        return None
    mid = (obj or {}).get("id")
    if not mid:
        return None
    if code == 202 and not _await_media(host, token, mid):
        print("[announce] media %s not ready in time — text-only toot" % mid,
              file=sys.stderr)
        return None
    return mid


def _maybe_toot_image(title: str, host: str, token: str, api_key: str,
                      base_url: "str | None") -> "list[str] | None":
    """Generate + upload one image for the toot; returns [media_id] or None.
    Wholly best-effort — never raises, so it can't block the announcement."""
    try:
        model = os.environ.get("RALPH_IMAGE_MODEL", "").strip() or TOOT_IMAGE_MODEL
        img = _generate_image(title, model, api_key, base_url)
        if img is None:
            return None
        raw, mime = img
        orig_bytes = len(raw)
        raw, mime = _compress_image(raw, mime)           # shrink before upload
        alt = ("Abstract graph-motif illustration for the ralph decision: "
               + _clean_title(title))[:1400]
        mid = _upload_media(host, token, raw, mime, alt)
        if not mid:
            return None
        print("[announce] image attached media_id=%s bytes=%d (from %d) mime=%s model=%s"
              % (mid, len(raw), orig_bytes, mime, model))
        return [mid]
    except Exception as e:   # noqa: BLE001 — belt-and-suspenders; never block the toot
        print("[announce] image step errored (%s) — text-only toot"
              % type(e).__name__, file=sys.stderr)
        return None


def _short_err(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    reason = getattr(exc, "reason", None)
    s = ("%s %s" % (code, reason)) if code else str(exc)
    return s[:200]


def _open_announce_failure_issue(host: str, did: str, exc: Exception) -> None:
    """Open ONE tracking issue per repo when announcing fails (deduped by title,
    so repeated failures don't spam)."""
    title = "ralph: Mastodon announce failing"
    raw = _run(["gh", "issue", "list", "--repo", HOME_GH, "--state", "open",
                "--limit", "100", "--json", "title"], cwd=REPO_HOME)
    try:
        if raw and any(i.get("title") == title for i in _loads(raw)):
            print("[announce] failure issue already open — not duplicating")
            return
    except (json.JSONDecodeError, TypeError):
        pass
    body = (
        "The ralph Mastodon announcer is failing.\n\n"
        f"- host: `{host}`\n- decision: `{did}`\n"
        f"- error: `{type(exc).__name__}: {_short_err(exc)}`\n\n"
        "The decision itself was still committed — announcing is a separate, "
        "post-commit step. Fix the endpoint/token, then close this issue; ralph "
        "retries the announcement each tick (idempotent).")
    out = _run(["gh", "issue", "create", "--repo", HOME_GH, "--title", title,
                "--body", body], cwd=REPO_HOME)
    print("[announce] opened failure issue: %s" % (out.strip() or "(gh)"))


def _close_announce_failure_issue() -> None:
    """Auto-close the failure issue once announcing recovers (keeps the tracker
    clean). Best-effort — failures here are ignored."""
    title = "ralph: Mastodon announce failing"
    raw = _run(["gh", "issue", "list", "--repo", HOME_GH, "--state", "open",
                "--limit", "100", "--json", "number,title"], cwd=REPO_HOME)
    try:
        for i in _loads(raw or "[]"):
            if i.get("title") == title:
                _run(["gh", "issue", "close", str(i["number"]), "--repo", HOME_GH,
                      "--comment", "ralph announce recovered — closing."], cwd=REPO_HOME)
                print("[announce] closed recovered failure issue #%s" % i["number"])
    except (json.JSONDecodeError, TypeError):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _repo_tree(path: str, limit: int = 120) -> str:
    """A compact, deterministic file-tree summary (tracked files grouped by
    top-level dir with counts), so the model knows the repo's shape. Bounded."""
    files = [ln for ln in _run(["git", "ls-files"], cwd=path).splitlines() if ln]
    if not files:
        return ""
    counts: dict[str, int] = {}
    is_dir: dict[str, bool] = {}
    for f in files:
        top, _, rest = f.partition("/")
        counts[top] = counts.get(top, 0) + 1
        is_dir[top] = is_dir.get(top, False) or bool(rest)
    lines = [f"{top}/ ({counts[top]})" if is_dir[top] else top
             for top in sorted(counts)]
    return "\n".join(lines[:limit])


def _gh_json(args: list[str], cwd: str) -> list:
    raw = _run(args, cwd=cwd)
    if not raw:
        return []
    try:
        return _loads(raw)
    except json.JSONDecodeError:
        return []


@functools.lru_cache(maxsize=16)
def _gather_context_cached(repo_gh: str, repo_path: str, git_log_window: int,
                           compact: bool, head: str) -> str:
    """Build the repo context string. Memoized on HEAD (and the inputs) so
    repeated calls in one run don't re-shell-out; the `head` key invalidates the
    cache when the repo moves. Content is ordered STABLE → VOLATILE (key files,
    then tree, then issues/PRs, then the git log last) so an LLM provider's
    prompt-prefix cache can reuse the unchanging head of the prompt across ticks."""
    parts: list[str] = []

    # 1) Key files — most stable, first (good prompt-cache prefix).
    for rel in ("README.md", "CLAUDE.md", "AGENTS.md"):
        fpath = os.path.join(repo_path, rel)
        if os.path.isfile(fpath):
            try:
                with open(fpath, encoding="utf-8") as f:
                    txt = f.read()
            except OSError:
                continue
            parts.append(f"## {rel}\n{txt[:1500] if compact else txt}")

    # 2) Repo file tree — fairly stable layout.
    tree = _repo_tree(repo_path)
    if tree:
        parts.append("## Repo layout (tracked files by top-level dir)\n" + tree)

    # 3) Open issues.
    issues = _gh_json(["gh", "issue", "list", "--repo", repo_gh, "--state", "open",
                       "--limit", "40", "--json", "number,title,body"], cwd=repo_path)
    if issues:
        if compact:
            parts.append("## Open issues\n"
                         + "\n".join(f"#{i['number']} {i['title']}" for i in issues))
        else:
            parts.append("## Open issues\n" + "\n\n".join(
                f"### #{i['number']} {i['title']}\n{(i.get('body') or '')[:4000]}"
                for i in issues))
    else:
        parts.append("## Open issues\n(unavailable)")

    # 4) Open pull requests — richer signal on in-flight work.
    prs = _gh_json(["gh", "pr", "list", "--repo", repo_gh, "--state", "open",
                    "--limit", "30", "--json", "number,title"], cwd=repo_path)
    if prs:
        parts.append("## Open pull requests\n"
                     + "\n".join(f"#{p['number']} {p['title']}" for p in prs))

    # 5) Git log — most volatile, LAST so it never shifts the cached prefix above.
    log = _run(["git", "log", "--oneline", f"-n{git_log_window}"], cwd=repo_path)
    if log:
        parts.append("## Git log\n" + log.rstrip())

    return "\n\n".join(parts)


def gather_context(repo: C.Repo, git_log_window: int, compact: bool) -> str:
    """Read-only project state for a repo (deprecated repo mode). Cache-friendly:
    memoized on HEAD and ordered stable→volatile (see `_gather_context_cached`)."""
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo.path).strip() or "?"
    return _gather_context_cached(repo.gh, repo.path, git_log_window, compact, head)


# ---------------------------------------------------------------------------
# Per-track context (read-only, all inside the home repo / vaked-base)
# ---------------------------------------------------------------------------


def _expand_doc_globs(patterns: list[str]) -> list[str]:
    """Resolve track doc globs against REPO_HOME. `recursive=True` is required
    so `**` descends (else protocol/** + vaked/examples/** drop nested files);
    keep only files, de-duped and sorted for determinism."""
    seen: set[str] = set()
    out: list[str] = []
    for pat in patterns:
        for fp in sorted(glob.glob(os.path.join(REPO_HOME, pat), recursive=True)):
            if os.path.isfile(fp) and fp not in seen:
                seen.add(fp)
                out.append(fp)
    return out


def _query_open_issues(extra: list[str]) -> "list[dict] | None":
    """One `gh issue list --state open` query. None ⇒ gh unavailable / error;
    [] ⇒ a successful but empty result."""
    raw = _run(["gh", "issue", "list", "--repo", HOME_GH, "--state", "open",
                "--limit", "40", "--json", "number,title,body"] + extra,
               cwd=REPO_HOME)
    if not raw:
        return None
    try:
        return _loads(raw)
    except json.JSONDecodeError:
        return None


def _issues_for_labels(labels: list[str]) -> "tuple[list[dict], str]":
    """Open home-repo issues scoped to the OR-union of `labels` (gh's repeated
    `--label` ANDs, so we query per label and union by issue number). Falls back
    to all-open (with a note) ONLY when EVERY label query fails (gh unavailable /
    every label unusable) — a successful-but-empty scoped result is preserved, so
    a freshly-triaged label scope with zero issues stays scoped instead of
    pulling in unrelated work. Empty `labels` ⇒ all-open. Returns (issues, note),
    issues sorted newest-first (number desc)."""
    if not labels:
        return (_query_open_issues([]) or []), ""

    union: dict[int, dict] = {}
    any_ok = False
    for lab in labels:
        res = _query_open_issues(["--label", lab])
        if res is None:
            continue                     # this label failed; try the others
        any_ok = True
        for it in res:
            union[it["number"]] = it
    if not any_ok:
        # every label query failed → gh unusable → fall back to all-open
        return (_query_open_issues([]) or []), " (no usable label filter; showing all open)"
    issues = sorted(union.values(), key=lambda i: -i["number"])
    return issues, ""


def _track_issues(label: str) -> "tuple[list[dict], str]":
    """Back-compat single-label scope (delegates to the OR-union helper)."""
    return _issues_for_labels([label] if label else [])


def gather_track_context(track: C.Track, git_log_window: int, compact: bool) -> str:
    """Read-only project state scoped to a track, all inside REPO_HOME:
    label-filtered home-repo issues, the track's doc globs, and a path-scoped
    git log. compact=True trims for stage 1; full text for stage 2."""
    parts: list[str] = []

    issues, note = _issues_for_labels(track.issue_labels)
    if issues:
        if compact:
            lines = [f"#{i['number']} {i['title']}" for i in issues]
            parts.append(f"## Open issues{note}\n" + "\n".join(lines))
        else:
            chunks = [f"### #{i['number']} {i['title']}\n{(i.get('body') or '')[:4000]}"
                      for i in issues]
            parts.append(f"## Open issues{note}\n" + "\n\n".join(chunks))
    else:
        parts.append("## Open issues\n(unavailable)")

    for fpath in _expand_doc_globs(track.context.docs):
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except OSError:
            continue
        rel = os.path.relpath(fpath, REPO_HOME)
        parts.append(f"## {rel}\n{txt[:1500] if compact else txt}")

    cmd = ["git", "log", "--oneline", f"-n{git_log_window}"]
    if track.context.paths:
        cmd += ["--", *track.context.paths]
    log = _run(cmd, cwd=REPO_HOME)
    if log:
        parts.append("## Git log\n" + log.rstrip())

    return "\n\n".join(parts)


def _open_track_issue_count(track: C.Track) -> int:
    """Count the issues actually shown to the track — the OR-union of its
    `issue_labels` — so the `N open issues` header matches the scoped body."""
    issues, _ = _issues_for_labels(track.issue_labels)
    return len(issues)


def _trace_generation(gen, model: str, resp: dict, meta: "dict | None",
                      latency: float) -> None:
    """Record an LLM call's result onto an open Langfuse generation. Fully
    guarded — any tracing failure is swallowed (observability never breaks the
    loop). No-op when `gen` is None."""
    if gen is None:
        return
    try:
        usage = resp.get("usage") or {}
        update = {
            "output": _message_content(resp),
            "usage_details": {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            },
            "metadata": {**(meta or {}), "latency_s": round(latency, 3)},
        }
        price = C.FALLBACK_PRICES.get(model)
        if price is not None:
            update["cost_details"] = {"total_cost": C.cost_usd(usage, price)}
        gen.update(**update)
    except Exception:
        pass


def openrouter_call(
    model: str,
    messages: list[dict],
    *,
    api_key: str,
    temperature: float,
    max_tokens: int,
    reasoning: dict | None = None,
    response_format: dict | None = None,
    modalities: list | None = None,
    seed: int | None = None,
    retries: int = 3,
    base_url: str | None = None,
    span_name: str = "ralph.generation",
    span_meta: dict | None = None,
) -> dict:
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.95,
        "max_tokens": max_tokens,
    }
    if reasoning is not None:
        body["reasoning"] = reasoning
    if response_format is not None:
        body["response_format"] = response_format
    if modalities is not None:               # e.g. ["image", "text"] for image gen
        body["modalities"] = modalities
    if seed is not None:
        body["seed"] = seed

    data = json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Open an optional Langfuse generation span around the call (no-op if off).
    lf = _langfuse()
    gen_cm = gen = None
    if lf is not None:
        try:
            params = {"temperature": temperature, "top_p": 0.95, "max_tokens": max_tokens}
            if seed is not None:
                params["seed"] = seed
            gen_cm = lf.start_as_current_generation(
                name=span_name, model=model, input=messages, model_parameters=params)
            gen = gen_cm.__enter__()
        except Exception:
            gen_cm = gen = None

    t0 = time.time()
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(_resolve_base_url(base_url), data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                parsed = _loads(resp.read().decode("utf-8"))
            _trace_generation(gen, model, parsed, span_meta, time.time() - t0)
            if gen_cm is not None:
                try:
                    gen_cm.__exit__(None, None, None)
                except Exception:
                    pass
            return parsed
        except Exception as exc:
            last_exc = exc
            time.sleep(2 ** attempt)

    if gen is not None:
        try:
            gen.update(level="ERROR", status_message=str(last_exc),
                       metadata={**(span_meta or {}), "latency_s": round(time.time() - t0, 3)})
        except Exception:
            pass
    if gen_cm is not None:
        try:
            gen_cm.__exit__(None, None, None)
        except Exception:
            pass
    raise RuntimeError(f"openrouter_call failed after {retries} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Log helpers
# ---------------------------------------------------------------------------


def _log_path(repo_name: str) -> str:
    return os.path.join(DECISIONS_DIR, f"{repo_name}.ralph-log.md")


def _prior_titles(repo_name: str) -> list[str]:
    path = _log_path(repo_name)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    titles: list[str] = []
    for line in lines:
        if line.startswith("## ") and "Decision #" in line:
            # "## DATE — Decision #N: TITLE"
            if ":" in line:
                titles.append(line.split(":", 1)[1].strip())
            else:
                titles.append(line.strip())
    return titles


def _read_log(repo_name: str) -> str:
    path = _log_path(repo_name)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "(none)"


def _prior_decisions_block(subject_name: str) -> str:
    """The stage-2 "prior decisions" context block, WINDOWED (#57). Injecting
    the whole ever-growing log made cost/decision climb linearly with history,
    breaking PURPOSE.md's near-flat-cost bet; `window_log` keeps only the last N
    full entries so this block — and the stage-2 prompt — is O(1) in log size."""
    return "\n\n## Full prior decisions\n" + C.window_log(_read_log(subject_name))


def _decision_block(track_name: str, n: int) -> str:
    """The text of the `## … Decision #n: …` block in a track's log (for
    sensitivity detection). Empty if not found."""
    log = _read_log(track_name)
    if not log or log == "(none)":
        return ""
    marker = "Decision #%d:" % n
    for block in re.split(r"(?m)^(?=## )", log):
        if marker in block.split("\n", 1)[0]:
            return block
    return ""


_SENSITIVE_RE = re.compile(
    r"\b(secret|credential|password|token|api[- ]?key|private[- ]?key|"
    r"vuln(?:erability)?|exploit|cve|rce|leak|pii|security)\b", re.I)


def _is_sensitive(text: str) -> bool:
    """A decision is 'sensitive' if it touches security topics or is low
    confidence — those get a Mastodon content warning (spoiler_text)."""
    if not text:
        return False
    if _SENSITIVE_RE.search(text):
        return True
    # Bounded gap (no unbounded adjacent quantifiers) — avoids O(N²) backtracking
    # on long whitespace runs in the decision block.
    return bool(re.search(r"confidence[:\s*\"']{0,8}low", text, re.I))


def _ratify_log_path(name: str) -> str:
    return os.path.join(DECISIONS_DIR, f"{name}.ratify-log.md")


def _read_ratify(name: str) -> list[dict]:
    """Parsed ratification records for a track (skips malformed/comment lines)."""
    out: list[dict] = []
    try:
        with open(_ratify_log_path(name), encoding="utf-8") as f:
            for line in f:
                rec = C.parse_ratify_line(line)
                if rec:
                    out.append(rec)
    except FileNotFoundError:
        pass
    return out


def _recent_overrides(name: str, limit: int = 5) -> list[str]:
    """Recent 'override' reasons for a track, as 'id: reason' — fed back into
    stage 1 so the loop learns what the human rejected."""
    overrides = [r for r in _read_ratify(name) if r["verdict"] == "override"]
    return ["%s: %s" % (r["id"], r["reason"]) for r in overrides[-limit:]]


_LOG_HEADER = (
    "# Ralph decision log — {repo}\n\n"
    "> Machine-generated, ADVISORY. Each entry is one strategic decision surfaced by the ralph loop "
    "(qwen3-235b-thinking → deepseek-v4-flash). A human ratifies; entries are appended, never rewritten.\n\n"
)


def _append_log(repo_name: str, entry: str) -> None:
    os.makedirs(DECISIONS_DIR, exist_ok=True)
    path = _log_path(repo_name)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(_LOG_HEADER.format(repo=repo_name))
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


def _today() -> str:
    return datetime.date.today().isoformat()


def _open_issue_count(repo: C.Repo) -> int:
    raw = _run(
        ["gh", "issue", "list", "--repo", repo.gh, "--state", "open",
         "--limit", "200", "--json", "number"],
        cwd=repo.path,
    )
    if not raw:
        return 0
    try:
        return len(_loads(raw))
    except (json.JSONDecodeError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Stage-1 schema
# ---------------------------------------------------------------------------

_STAGE1_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "candidates", "strict": True,
        "schema": {"type": "object", "properties": {"candidates": {"type": "array",
            "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "why_now": {"type": "string"},
                "urgency": {"type": "integer"}, "addressed": {"type": "boolean"}},
                "required": ["title", "why_now", "urgency", "addressed"]}}},
            "required": ["candidates"]}}}


# ---------------------------------------------------------------------------
# Live decide path (Task 8)
# ---------------------------------------------------------------------------


def _message_content(resp: dict) -> "str | None":
    """The assistant message text of an OpenRouter response, or None if the
    response has no usable content. Guards the realistic non-standard 200s:
    empty ``choices`` (content filtering) and ``content: null`` (a thinking
    model that emitted only reasoning) — so callers skip rather than crash."""
    try:
        choices = resp.get("choices") or []
        if not choices:
            return None
        return choices[0].get("message", {}).get("content")
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def _reasoning_text(resp: dict) -> "str | None":
    """A thinking model's reasoning text (OpenRouter puts it in
    message.reasoning / reasoning_content). Used as a fallback when `content` is
    null but the JSON answer ended up inside the reasoning."""
    try:
        msg = (resp.get("choices") or [{}])[0].get("message", {})
        return msg.get("reasoning") or msg.get("reasoning_content")
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def _finish_reason(resp: dict) -> "str | None":
    try:
        return (resp.get("choices") or [{}])[0].get("finish_reason")
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.S)


def _parse_candidates(text: "str | None") -> list:
    """Extract the `candidates` list from a stage-1 response that may be raw
    JSON, fenced JSON (```json …```), or JSON embedded in prose/reasoning.
    Returns [] if nothing usable."""
    if not text:
        return []
    for chunk in (text, _strip_fences(text)):
        try:
            c = _loads(chunk).get("candidates")
            if isinstance(c, list):
                return c
        except (json.JSONDecodeError, AttributeError):
            pass
    m = _JSON_OBJ_RE.search(text)
    if m:
        try:
            c = _loads(m.group(0)).get("candidates")
            if isinstance(c, list):
                return c
        except (json.JSONDecodeError, AttributeError):
            pass
    return []


def _parse_json_obj(text: "str | None") -> dict:
    """Parse a JSON object from raw / fenced / prose-embedded text. {} if none."""
    if not text:
        return {}
    for chunk in (text, _strip_fences(text)):
        try:
            obj = _loads(chunk)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, AttributeError):
            pass
    m = _JSON_OBJ_RE.search(text)
    if m:
        try:
            obj = _loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, AttributeError):
            pass
    return {}


def _critique_on() -> bool:
    """Stage-3 self-critique is on by default; RALPH_CRITIQUE=off disables it."""
    return os.environ.get("RALPH_CRITIQUE", "").strip().lower() not in ("0", "off", "false", "no")


def _writer_call(writer: str, fallback: str, msgs, **kw):
    """Call the writer model; if it errors (e.g. a bad/unavailable slug), retry
    once with the track's fallback model. Returns (response, model_used)."""
    meta = dict(kw.pop("span_meta", {}) or {})
    try:
        return openrouter_call(writer, msgs, span_meta={**meta, "model": writer}, **kw), writer
    except Exception as e:   # noqa: BLE001 — degrade to the track model
        if writer == fallback:
            raise
        print("[decide] writer model %s failed (%s) — falling back to %s"
              % (writer, type(e).__name__, fallback), file=sys.stderr)
        return openrouter_call(fallback, msgs,
                               span_meta={**meta, "model": fallback, "writer_fallback": True},
                               **kw), fallback


def _run_stages(subject, s1_msgs, full_context_builder, stage1_model,
                stage2_model, api_key, base_url, seed, meta=None):
    """Run both LLM stages and return ``(cost, body, writer_used)`` or ``None`` to skip the
    iteration. `subject` keys the stage-2 prompt; `full_context_builder()` is
    called only once stage 1 yields a candidate (so we don't gather the full
    context for a skipped iteration). `meta` tags the Langfuse spans (e.g. the
    track name). Shared by repo and track decide paths."""
    base_meta = meta or {}
    # max_tokens is generous: thinking models (e.g. qwen3-thinking) spend tokens
    # on reasoning before the JSON answer — too small a budget truncates the
    # answer (finish_reason=length) and yields no candidates.
    s1 = openrouter_call(stage1_model, s1_msgs, api_key=api_key,
                         temperature=0.4, max_tokens=6000,
                         reasoning={"enabled": True, "effort": "low"},
                         response_format=_STAGE1_SCHEMA, seed=seed,
                         base_url=base_url, span_name="ralph.rank",
                         span_meta={**base_meta, "stage": 1})
    # Tolerant: content may be raw/fenced/embedded JSON; fall back to the
    # reasoning field for thinking models that return content=null.
    s1_text = _message_content(s1)
    cands = _parse_candidates(s1_text) or _parse_candidates(_reasoning_text(s1))
    if not cands:
        print("stage-1 returned no usable candidates "
              "(finish=%s, content_chars=%d); skipping iteration"
              % (_finish_reason(s1), len(s1_text or "")), file=sys.stderr)
        return None
    chosen = C.select_candidate(cands)
    if chosen is None:
        print("no candidates; skipping", file=sys.stderr)
        return None
    full = full_context_builder()
    # Stage 2 — deep-dive written by the configured strong WRITER model (falls
    # back to the track model if the writer call fails), grounded in `full`.
    writer = os.environ.get("RALPH_WRITER_MODEL", "").strip() or stage2_model
    s2_msgs = C.build_stage2_messages(subject, full, chosen)
    s2, used2 = _writer_call(writer, stage2_model, s2_msgs, api_key=api_key,
                             base_url=base_url, temperature=0.3, max_tokens=WRITER_MAX_TOKENS,
                             span_name="ralph.deep-dive",
                             span_meta={**base_meta, "stage": 2})
    body = _message_content(s2) or _reasoning_text(s2)
    if not body:
        print("stage-2 returned no usable content (finish=%s); skipping iteration"
              % _finish_reason(s2), file=sys.stderr)
        return None

    cost = (C.cost_usd(s1.get("usage", {}),
                       C.FALLBACK_PRICES.get(stage1_model, C.Price(0.10, 0.10)))
            + C.cost_usd(s2.get("usage", {}),
                         C.FALLBACK_PRICES.get(used2, C.Price(0.10, 0.20))))

    # Stage 3 — self-critique → rewrite for sharper, better-grounded entries.
    # Best-effort over a USABLE stage-2 draft: a critique failure (transient 5xx,
    # both writer + fallback down) or a rewrite that doesn't read like a finished
    # entry must NEVER lose the decision, so we keep the stage-2 body in those
    # cases. Cost for the call is counted whenever it was actually made, including
    # the keep-draft path, so the ledger never under-reports spend.
    if _critique_on():
        try:
            # Cap the grounding context for the critique: it already has the full
            # draft, so the entire (doubled) prior-decisions log isn't needed —
            # this halves the stage-3 token bill on a large ledger.
            crit_ctx = (full if len(full) <= CRITIQUE_CONTEXT_CHARS
                        else full[:CRITIQUE_CONTEXT_CHARS] + "\n\n[context truncated for critique]")
            s3_msgs = C.build_critique_messages(subject, body, crit_ctx)
            s3, used3 = _writer_call(writer, stage2_model, s3_msgs, api_key=api_key,
                                     base_url=base_url, temperature=0.2, max_tokens=WRITER_MAX_TOKENS,
                                     span_name="ralph.critique",
                                     span_meta={**base_meta, "stage": 3})
            cost += C.cost_usd(s3.get("usage", {}),
                               C.FALLBACK_PRICES.get(used3, C.Price(0.10, 0.20)))
            improved = (_message_content(s3) or _reasoning_text(s3) or "").strip()
            # Only accept a rewrite that actually reads like a decision entry — a
            # reasoning/preview model can return its review notes instead of the
            # rewritten entry; that must not overwrite a clean stage-2 draft.
            if len(improved) >= 40 and C.looks_like_entry(improved):
                body = improved
            else:
                print("[decide] critique output isn't a clean entry (finish=%s, "
                      "chars=%d) — keeping stage-2 draft"
                      % (_finish_reason(s3), len(improved)), file=sys.stderr)
        except Exception as e:           # noqa: BLE001 — never drop a good draft
            print("[decide] critique pass failed (%s) — keeping stage-2 draft"
                  % type(e).__name__, file=sys.stderr)
    return cost, body.strip(), used2


def _decide_live(args, repo: C.Repo, s1_msgs: list[dict], api_key: str) -> float:
    """Deprecated repo-mode iteration: two-stage, two-model (stage1/stage2)."""
    base_url = getattr(args, "base_url", None)

    def full_ctx() -> str:
        return (gather_context(repo, args.git_log_window, compact=False)
                + _prior_decisions_block(repo.name))

    result = _run_stages(repo.name, s1_msgs, full_ctx, args.stage1_model,
                         args.stage2_model, api_key, base_url, args.seed,
                         meta={"repo": repo.name})
    if result is None:
        return 0.0
    cost, body, writer_used = result
    head = _run(["git", "rev-parse", "--short", "HEAD"], repo.path).strip() or "?"
    n = len(_prior_titles(repo.name)) + 1
    entry = C.format_entry(n=n, date=_today(), repo=repo.name, head=head,
                           open_issues=_open_issue_count(repo), body=body,
                           s1=args.stage1_model.split("/")[-1],
                           s2=writer_used.split("/")[-1])
    _append_log(repo.name, entry)
    print("decided #%d for %s (cost $%.4f): %s" % (n, repo.name, cost,
                                                    entry.splitlines()[0]))
    return cost


def _decide_track(args, track: C.Track, api_key: str) -> float:
    """Track-mode iteration: two-stage, ONE model (track.model) for both
    stages. Writes to docs/decisions/<track>.ralph-log.md."""
    base_url = getattr(args, "base_url", None)
    compact = gather_track_context(track, args.git_log_window, compact=True)
    s1_msgs = C.build_stage1_messages(track.topic, compact,
                                      _prior_titles(track.name),
                                      mission=read_purpose(),
                                      overrides=_recent_overrides(track.name))

    def full_ctx() -> str:
        return (gather_track_context(track, args.git_log_window, compact=False)
                + _prior_decisions_block(track.name))

    result = _run_stages(track.topic, s1_msgs, full_ctx, track.model,
                         track.model, api_key, base_url, args.seed,
                         meta={"track": track.name, "model": track.model})
    if result is None:
        # No decision this tick (model skipped). Still advance the rotation
        # pointer with a skip event, or one flaky track would starve the rest.
        append_event({"event": "skip", "track": track.name})
        return 0.0
    cost, body, writer_used = result
    head = _run(["git", "rev-parse", "--short", "HEAD"], REPO_HOME).strip() or "?"
    n = len(_prior_titles(track.name)) + 1
    entry = C.format_entry(n=n, date=_today(), repo=track.name, head=head,
                           open_issues=_open_track_issue_count(track), body=body,
                           s1=track.model.split("/")[-1],
                           s2=writer_used.split("/")[-1], subject_label="Track")
    _append_log(track.name, entry)
    # Emit the rotation event so --next-track advances and CI persists it.
    # The track decision-maker logs its own decide event (unlike repo-mode,
    # where cmd_run appends); a future track supervisor must not double-append.
    # `total_cost` is cumulative (prior ledger spend + this cost) so
    # `events --replay` reconstructs total spend across stateless CI runs.
    append_event({"event": "decide", "track": track.name, "iteration": n,
                  "cost": cost, "total_cost": _events_total_cost() + cost})
    print("decided #%d for %s (cost $%.4f): %s" % (n, track.name, cost,
                                                   entry.splitlines()[0]))
    return cost


def _last_decided_track() -> "str | None":
    """The most recently *attempted* track (rotation pointer for --next-track).
    Counts both `decide` and `skip` events — a skip must still advance rotation
    so one flaky track can't starve the others. None if none attempted yet."""
    for e in reversed(load_events()):
        payload = e.get("payload", {})
        if payload.get("track") and payload.get("event") in ("decide", "skip"):
            return payload["track"]
    return None


def _events_total_cost() -> float:
    """Cumulative spend recorded across decide events (the max `total_cost` seen,
    which the supervisor and track decide both write monotonically)."""
    total = 0.0
    for e in load_events():
        payload = e.get("payload", {})
        if payload.get("event") == "decide":
            total = max(total, float(payload.get("total_cost", 0.0) or 0.0))
    return total


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_decide(args) -> int:
    # Track mode is primary; --repo is the deprecated path.
    if getattr(args, "track", None) or getattr(args, "next_track", False):
        return _cmd_decide_track(args)
    if not getattr(args, "repo", None):
        print("one of --track / --next-track / --repo is required", file=sys.stderr)
        return 2
    print("note: --repo mode is deprecated; prefer --track", file=sys.stderr)

    repos_list = C.load_repos(args.repos)
    repo_map = {r.name: r for r in repos_list}
    if args.repo not in repo_map:
        print(f"unknown repo: {args.repo!r}", file=sys.stderr)
        return 2

    repo = repo_map[args.repo]
    compact_ctx = gather_context(repo, args.git_log_window, compact=True)
    prior_titles = _prior_titles(repo.name)
    s1_msgs = C.build_stage1_messages(repo.name, compact_ctx, prior_titles, mission=read_purpose())

    if args.dry_run:
        model = args.stage1_model
        approx_tokens = sum(len(m["content"]) // 4 for m in s1_msgs)
        print(f"=== stage 1 prompt ({model}) ===")
        print(json.dumps(s1_msgs, indent=2)[:2000])
        print(f"=== cost estimate ===")
        print(f"approximate token estimate: ~{approx_tokens} prompt tokens")
        return 0

    api_key = _resolve_api_key()
    if not api_key:
        print("no API key — set RALPH_API_KEY or OPENROUTER_API_KEY", file=sys.stderr)
        return 1

    _decide_live(args, repo, s1_msgs, api_key)
    return 0


def _cmd_decide_track(args) -> int:
    tracks = C.load_tracks(args.tracks)
    tmap = {t.name: t for t in tracks}
    if getattr(args, "next_track", False):
        nxt = C.next_track([t.name for t in tracks], _last_decided_track(), set())
        if nxt is None:
            print("no tracks available", file=sys.stderr)
            return 2
        track = tmap[nxt]
    else:
        if args.track not in tmap:
            print(f"unknown track: {args.track!r}", file=sys.stderr)
            return 2
        track = tmap[args.track]

    compact_ctx = gather_track_context(track, args.git_log_window, compact=True)
    s1_msgs = C.build_stage1_messages(track.topic, compact_ctx,
                                      _prior_titles(track.name),
                                      mission=read_purpose())

    if args.dry_run:
        approx_tokens = sum(len(m["content"]) // 4 for m in s1_msgs)
        print(f"=== stage 1 prompt ({track.model}) ===")
        print(json.dumps(s1_msgs, indent=2)[:2000])
        print("=== cost estimate ===")
        print(f"approximate token estimate: ~{approx_tokens} prompt tokens")
        return 0

    api_key = _resolve_api_key()
    if not api_key:
        print("no API key — set RALPH_API_KEY or OPENROUTER_API_KEY", file=sys.stderr)
        return 1

    _decide_track(args, track, api_key)
    return 0


def read_status() -> "dict | None":
    if not os.path.exists(STATUS_PATH):
        return None
    try:
        with open(STATUS_PATH, encoding="utf-8") as f:
            return _loads(f.read())
    except json.JSONDecodeError:
        return None


def write_status(status: dict) -> None:
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2)
    os.replace(tmp, STATUS_PATH)


def read_control() -> C.Control:
    """Read CONTROL_PATH and parse it. Missing or malformed -> defaults."""
    try:
        with open(CONTROL_PATH, encoding="utf-8") as f:
            d = _loads(f.read())
        return C.parse_control(d)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return C.parse_control(None)


def _clear_step() -> None:
    """Reset the one-shot `step` flag after a stepped iteration, keeping
    paused/interval intact. No-op if control.json is missing/unset."""
    try:
        with open(CONTROL_PATH, encoding="utf-8") as f:
            d = _loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return
    if d.get("step"):
        d["step"] = False
        tmp = CONTROL_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, CONTROL_PATH)


# Single-writer head cache (#58): the eventd design mandates one writer per log,
# so the next (prev_hash, seq) can be carried in memory instead of re-scanning
# the whole file on every append — that scan made a run of N appends O(N^2). The
# cache primes from a VERIFIED read (refusing a broken chain) and advances in
# place; any change to EVENTS_PATH or its stat signature forces a re-prime, so an
# append can never silently fork off a stale or torn tail.
_WRITER = {"path": None, "tail": C.GENESIS_HASH, "seq": 0, "sig": None}


def _reset_writer_cache() -> None:
    _WRITER["path"] = None
    _WRITER["sig"] = None


def _stat_sig() -> tuple:
    """An O(1) change signature for EVENTS_PATH: (size, mtime_ns, inode). Any
    append/rewrite bumps mtime (and an os.replace swaps the inode), so this
    catches an external change the cache must re-prime against — unlike a
    size-only check, which a same-size content swap would hide."""
    try:
        st = os.stat(EVENTS_PATH)
    except OSError:
        return (0, 0, 0)
    return (st.st_size, st.st_mtime_ns, st.st_ino)


def _verified_entries_for_prime() -> list[dict]:
    """Parse EVENTS_PATH and return its entries ONLY if it is a fully-verified
    chain; a torn/unparseable line or a chain that fails verification raises
    EventLogTamper. The single writer must never chain onto an unverified tail
    (mirrors eventd's verify-on-open). cmd_run repairs a torn tail via
    _boot_recover_events before appending, so its appends prime clean; a stray
    append onto a broken log fails loudly instead of corrupting it silently."""
    raw = _event_byte_lines()
    entries: list[dict] = []
    for n, bl in enumerate(raw, 1):
        try:
            e = _loads(bl)
        except (json.JSONDecodeError, UnicodeDecodeError) as ex:
            raise EventLogTamper(
                f"{EVENTS_PATH}:{n}: unparseable log line — run `ralph run` to "
                f"boot-repair a torn tail before appending") from ex
        if not isinstance(e, dict):
            raise EventLogTamper(f"{EVENTS_PATH}:{n}: non-object log line")
        entries.append(e)
    if not C.verify_chain(entries):
        raise EventLogTamper(
            f"{EVENTS_PATH}: chain does not verify — refusing to append onto a "
            f"tampered/torn spine")
    return entries


def _writer_head() -> "tuple[str, int]":
    """The (prev_hash, next_seq) for the next append — O(1) from the warm cache,
    re-primed from a VERIFIED read whenever EVENTS_PATH or its stat signature
    changed. Priming refuses a broken chain (EventLogTamper)."""
    sig = _stat_sig()
    if _WRITER["path"] != EVENTS_PATH or _WRITER["sig"] != sig:
        entries = _verified_entries_for_prime()
        _WRITER["path"] = EVENTS_PATH
        _WRITER["tail"] = entries[-1]["hash"] if entries else C.GENESIS_HASH
        _WRITER["seq"] = len(entries)
        _WRITER["sig"] = sig
    return _WRITER["tail"], _WRITER["seq"]


def append_event(payload: dict) -> dict:
    """Build and append one hash-chained entry to EVENTS_PATH, fsync, return it.

    O(1) amortized: the (prev_hash, seq) come from the single-writer head cache,
    re-primed (and re-verified) only when the file changed under us — not a full
    re-scan per call (#58; a run of N appends was O(N^2)). fsync-on-append, plus
    a one-time directory fsync when the first entry creates the file, makes the
    write durable; a crash leaves at worst a torn FINAL line, which
    _boot_recover_events truncates."""
    os.makedirs(STATE_DIR, exist_ok=True)
    prev, seq = _writer_head()
    entry = C.make_entry(prev, seq, payload)
    line = json.dumps(entry) + "\n"
    created = seq == 0
    with open(EVENTS_PATH, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    if created:                  # the first append created the file — fsync dir
        _fsync_dir(os.path.dirname(EVENTS_PATH) or ".")
    _WRITER["path"] = EVENTS_PATH
    _WRITER["tail"] = entry["hash"]
    _WRITER["seq"] = seq + 1
    _WRITER["sig"] = _stat_sig()   # exact post-write signature (one O(1) stat)
    return entry


KIND_REPAIR = "log_repair"


def _fsync_dir(path: str) -> None:
    """fsync a directory so a newly-created/renamed file's dir entry is durable."""
    dfd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


class EventLogTamper(RuntimeError):
    """The event log's chain is broken in a way that is not a recoverable
    torn tail (a parseable entry that fails the hash chain = tamper/corruption).
    The driver refuses to chain new entries onto it."""


def _event_byte_lines() -> list[bytes]:
    """Non-empty raw byte lines of EVENTS_PATH (empty if missing). Byte-oriented
    so a crash that tore the final line mid-multibyte is handled as an
    unparseable suffix line, not a UnicodeDecodeError traceback."""
    try:
        with open(EVENTS_PATH, "rb") as f:
            return [ln for ln in f.read().split(b"\n") if ln.strip()]
    except FileNotFoundError:
        return []


def _boot_recover_events() -> None:
    """Boot-time integrity gate for the driver (#58), mirroring the eventd
    daemon's discipline. cmd_run must verify the chain BEFORE appending, or it
    chains onto a torn/tampered log:

      * a fully-verifying chain (or an empty/missing log) → no-op;
      * a torn TAIL (a crash left a trailing line that fails to PARSE) →
        truncate the unverifiable suffix to the longest valid prefix and append
        a `log_repair` event (the truncation is itself audited), crash-atomically;
      * a TAMPER (the first broken line PARSES as an entry but fails the chain —
        an edited field, a deleted middle entry) → raise EventLogTamper. A
        deliberate edit is not silently healed."""
    raw = _event_byte_lines()
    if not raw:
        _reset_writer_cache()
        return
    prefix: list[dict] = []
    prev = C.GENESIS_HASH
    broke_at = None
    bad_was_parseable = False
    for idx, bl in enumerate(raw):
        try:
            e = _loads(bl)
            parseable = isinstance(e, dict)
        except (json.JSONDecodeError, UnicodeDecodeError):
            e, parseable = None, False
        if (not parseable or e.get("seq") != len(prefix) or e.get("prev") != prev
                or e.get("hash") != C.chain_hash(prev, e.get("payload", {}))):
            broke_at, bad_was_parseable = idx, parseable
            break
        prefix.append(e)
        prev = e["hash"]
    if broke_at is None:
        return                              # whole log verifies
    if bad_was_parseable:
        raise EventLogTamper(
            f"{EVENTS_PATH}: chain broken at line {broke_at + 1} by a "
            f"well-formed entry — tamper/corruption, refusing to run")
    _rewrite_events_with_repair(prefix, dropped=len(raw) - len(prefix))


def _rewrite_events_with_repair(prefix: list[dict], dropped: int) -> None:
    """Crash-atomically rewrite EVENTS_PATH to ``prefix`` + a ``log_repair``
    entry recording ``dropped`` (temp → fsync → os.replace → dir fsync), then
    invalidate the writer cache so the next append chains off the repaired tail."""
    prev = prefix[-1]["hash"] if prefix else C.GENESIS_HASH
    repair = C.make_entry(prev, len(prefix),
                          {"event": KIND_REPAIR, "dropped": dropped})
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = EVENTS_PATH + ".repair.tmp"
    with open(tmp, "w", encoding="utf-8") as w:
        for e in prefix:
            w.write(json.dumps(e) + "\n")
        w.write(json.dumps(repair) + "\n")
        w.flush()
        os.fsync(w.fileno())
    os.replace(tmp, EVENTS_PATH)
    _fsync_dir(os.path.dirname(EVENTS_PATH) or ".")
    _reset_writer_cache()


def _supervised_decide(args, repo: C.Repo, status: dict) -> None:
    """One decide iteration; fold cost + result into status. Contained --
    a failure here never crashes the supervisor."""
    api_key = _resolve_api_key()
    if not api_key:
        print("no API key — set RALPH_API_KEY or OPENROUTER_API_KEY — cannot decide",
              file=sys.stderr)
        return
    try:
        compact = gather_context(repo, args.git_log_window, compact=True)
        s1_msgs = C.build_stage1_messages(repo.name, compact, _prior_titles(repo.name), mission=read_purpose())
        before = len(_prior_titles(repo.name))
        cost = _decide_live(args, repo, s1_msgs, api_key)
        status["total_cost"] = status.get("total_cost", 0.0) + cost
        after = _prior_titles(repo.name)
        rep = status["repos"].setdefault(repo.name,
                                         {"entries": 0, "last_title": "-", "cost": 0.0})
        rep["cost"] = rep.get("cost", 0.0) + cost
        if len(after) > before:
            rep["entries"] = len(after)
            rep["last_title"] = after[-1]
            status["recent"].insert(0, {"repo": repo.name, "date": _today(),
                                        "title": after[-1]})
            status["recent"] = status["recent"][:10]
    except Exception as e:
        print("iteration failed for %s: %s" % (repo.name, e), file=sys.stderr)


def _apply_state_dir(d: str) -> None:
    """Redirect all state-file globals to an alternate directory."""
    global STATE_DIR, STATUS_PATH, CONTROL_PATH, EVENTS_PATH
    STATE_DIR = d
    STATUS_PATH = os.path.join(d, "status.json")
    CONTROL_PATH = os.path.join(d, "control.json")
    EVENTS_PATH = os.path.join(d, "events.jsonl")
    _reset_writer_cache()   # different log ⇒ the head cache must re-prime


def _supervised_decide_track(args, track: C.Track, status: dict) -> None:
    """One track decide iteration; fold cost + result into status. Contained --
    a failure here never crashes the supervisor. `_decide_track` appends its own
    decide/skip event, so the track supervisor must NOT double-append."""
    api_key = _resolve_api_key()
    if not api_key:
        print("no API key — set RALPH_API_KEY or OPENROUTER_API_KEY — cannot decide",
              file=sys.stderr)
        return
    try:
        before = len(_prior_titles(track.name))
        cost = _decide_track(args, track, api_key)
        status["total_cost"] = status.get("total_cost", 0.0) + cost
        after = _prior_titles(track.name)
        subjects = status.setdefault("subjects", {})
        rec = subjects.setdefault(track.name,
                                  {"entries": 0, "last_title": "-", "cost": 0.0,
                                   "model": track.model})
        rec["model"] = track.model
        rec["cost"] = rec.get("cost", 0.0) + cost
        if len(after) > before:
            rec["entries"] = len(after)
            rec["last_title"] = after[-1]
            status.setdefault("recent", []).insert(
                0, {"subject": track.name, "date": _today(), "title": after[-1]})
            status["recent"] = status["recent"][:10]
    except Exception as e:
        print("iteration failed for %s: %s" % (track.name, e), file=sys.stderr)


def cmd_run(args) -> int:
    if getattr(args, "state_dir", None):
        _apply_state_dir(args.state_dir)
    # Boot integrity gate (#58): verify (and torn-tail-repair) the chain before
    # appending. A tamper is a hard error — never chain onto a tampered spine.
    try:
        _boot_recover_events()
    except EventLogTamper as e:
        print(f"ralph: refusing to run — {e}", file=sys.stderr)
        return 4
    if getattr(args, "repo_mode", False):
        return _run_repos(args)
    return _run_tracks(args)


def _run_tracks(args) -> int:
    """Supervisor over concept tracks (the primary mode): round-robin tracks,
    one model each, budget-capped. Each iteration's decide/skip event is logged
    by _decide_track itself."""
    tracks = C.load_tracks(args.tracks)
    names = [t.name for t in tracks]
    by_name = {t.name: t for t in tracks}
    status = read_status()
    if status is None:
        status = {
            "running": True, "current": None, "iteration": 0,
            "total_cost": 0.0, "budget_total": args.budget_total,
            "subjects": {t.name: {"entries": 0, "last_title": "-", "cost": 0.0,
                                  "model": t.model} for t in tracks},
            "recent": [], "last_step_epoch": 0, "mode": "tracks",
        }
    status["running"] = True
    status["budget_total"] = args.budget_total
    status.setdefault("subjects", {})
    # status.json is a derived cache (gitignored); the committed event ledger is
    # the state-of-record. Reconcile rotation pointer + cumulative spend against
    # it on EVERY start — even when status exists but is stale (e.g. an external
    # `decide --next-track` advanced the ledger the cache never saw) — so we
    # never restart at track #1 or under-count spend already past the budget.
    ledger_total = _events_total_cost()
    if ledger_total > float(status.get("total_cost", 0.0) or 0.0):
        status["total_cost"] = ledger_total
    ledger_track = _last_decided_track()
    if ledger_track is not None:
        status["current"] = ledger_track
    iters = 0
    ticks = 0
    try:
        while True:
            if args.max_ticks and ticks >= args.max_ticks:
                break
            ctrl = read_control()
            if status["total_cost"] >= args.budget_total:
                print("budget cap reached ($%.2f) — stopping" % args.budget_total)
                break
            if args.max_iters and iters >= args.max_iters:
                print("max-iters reached — stopping")
                break
            interval = ctrl.interval if ctrl.interval is not None else args.interval
            if ctrl.paused and not ctrl.step:
                append_event({"tick": ticks, "event": "paused"})
                ticks += 1
                write_status(status)
                if args.max_ticks and ticks >= args.max_ticks:
                    break
                time.sleep(min(interval, 2.0))
                continue
            nxt = C.next_track(names, status["current"], set())
            if nxt is None:
                print("no tracks available — stopping", file=sys.stderr)
                break
            status["current"] = nxt
            status["iteration"] += 1
            iters += 1
            _supervised_decide_track(args, by_name[nxt], status)
            status["last_step_epoch"] = int(time.time())
            if ctrl.step:                 # one-shot consumed → back to paused
                _clear_step()
            ticks += 1
            write_status(status)
            if args.max_ticks and ticks >= args.max_ticks:
                break
            if args.max_iters and iters >= args.max_iters:
                continue
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nSIGINT — shutting down")
    finally:
        status["running"] = False
        write_status(status)
    return 0


def _run_repos(args) -> int:
    """DEPRECATED supervisor over whole repos (the original round-robin)."""
    repos = C.load_repos(args.repos)
    names = [r.name for r in repos]
    by_name = {r.name: r for r in repos}
    status = read_status() or {
        "running": True, "current": None, "iteration": 0,
        "total_cost": 0.0, "budget_total": args.budget_total,
        "repos": {n: {"entries": 0, "last_title": "-", "cost": 0.0} for n in names},
        "recent": [], "last_step_epoch": 0,
    }
    status["running"] = True
    status["budget_total"] = args.budget_total
    iters = 0
    ticks = 0
    try:
        while True:
            if args.max_ticks and ticks >= args.max_ticks:
                break
            ctrl = read_control()
            if status["total_cost"] >= args.budget_total:
                print("budget cap reached ($%.2f) — stopping" % args.budget_total)
                break
            if args.max_iters and iters >= args.max_iters:
                print("max-iters reached — stopping")
                break
            interval = ctrl.interval if ctrl.interval is not None else args.interval
            if ctrl.paused and not ctrl.step:
                append_event({"tick": ticks, "event": "paused"})
                ticks += 1
                write_status(status)
                if args.max_ticks and ticks >= args.max_ticks:
                    break
                time.sleep(min(interval, 2.0))
                continue
            unavailable = {r.name for r in repos if not os.path.isdir(r.path)}
            nxt = C.next_repo(names, status["current"], unavailable)
            if nxt is None:
                print("no available repos — stopping", file=sys.stderr)
                break
            status["current"] = nxt
            status["iteration"] += 1
            iters += 1
            _supervised_decide(args, by_name[nxt], status)
            status["last_step_epoch"] = int(time.time())
            append_event({"tick": ticks, "event": "decide", "repo": nxt,
                          "iteration": status["iteration"],
                          "total_cost": status["total_cost"]})
            if ctrl.step:                 # one-shot consumed → back to paused
                _clear_step()
            ticks += 1
            write_status(status)
            if args.max_ticks and ticks >= args.max_ticks:
                break
            if args.max_iters and iters >= args.max_iters:
                continue
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nSIGINT — shutting down")
    finally:
        status["running"] = False
        write_status(status)
    return 0


def load_events() -> list[dict]:
    """Read EVENTS_PATH and return a list of JSON entries (empty if file missing)."""
    try:
        with open(EVENTS_PATH, encoding="utf-8") as f:
            entries = []
            for line in f:
                line = line.strip()
                if line:
                    entries.append(_loads(line))
            return entries
    except (FileNotFoundError, OSError):
        return []


def replay_events(entries: list[dict]) -> dict:
    """Pure fold over entries → reconstructed view. entries must already be verified."""
    state: dict = {
        "decisions": 0,
        "ticks": len(entries),
        "total_cost": 0.0,
        "subjects": {},
        "paused": 0,
    }
    for e in entries:
        p = e.get("payload", {})
        event = p.get("event")
        if event == "decide":
            state["decisions"] += 1
            cost = p.get("total_cost", 0.0)
            if cost > state["total_cost"]:
                state["total_cost"] = cost
            # repo-mode events key on "repo"; track-mode on "track". Bucket
            # either so per-subject (per-track/per-model) audit stays populated.
            subject = p.get("repo") or p.get("track")
            if subject is not None:
                rec = state["subjects"].setdefault(subject, {"decisions": 0, "last_iteration": None})
                rec["decisions"] += 1
                rec["last_iteration"] = p.get("iteration")
        elif event == "paused":
            state["paused"] += 1
    # Back-compat alias: callers/tests that read the old "repos" key still work.
    state["repos"] = state["subjects"]
    return state


def cmd_events(args) -> int:
    if getattr(args, "state_dir", None):
        _apply_state_dir(args.state_dir)
    entries = load_events()
    ok = C.verify_chain(entries)
    if not ok:
        print(f"events: chain INVALID at {len(entries)} entries")
        return 1
    if getattr(args, "replay", False):
        state = replay_events(entries)
        print(json.dumps(state, indent=2))
    else:
        print(f"events: {len(entries)} entries, chain OK")
    return 0


def cmd_ratify(args) -> int:
    """Summarize the human ratify status per track: decisions surfaced, verdicts
    recorded, ratify-rate, and the un-acted backlog. Reads the advisory + ratify
    logs only (no network). See docs/decisions/RATIFY.md for the process."""
    tracks = C.load_tracks(args.tracks)
    print("ralph ratify — advisory decision status (see docs/decisions/RATIFY.md)\n")
    print("%-20s %5s %7s %9s %6s %6s %7s" %
          ("track", "dec", "ratify", "override", "defer", "todo", "rate"))
    all_verdicts: list[str] = []
    for t in tracks:
        recs = _read_ratify(t.name)
        verdicts = [r["verdict"] for r in recs]
        all_verdicts += verdicts
        decisions = len(_prior_titles(t.name))
        nr, no, nd = (verdicts.count("ratify"), verdicts.count("override"),
                      verdicts.count("defer"))
        todo = max(0, decisions - (nr + no))   # deferred items re-surface → still "todo"
        rate = C.ratify_rate(verdicts)
        rate_s = "—" if rate is None else "%d%%" % round(rate * 100)
        print("%-20s %5d %7d %9d %6d %6d %7s" %
              (t.name, decisions, nr, no, nd, todo, rate_s))
    overall = C.ratify_rate(all_verdicts)
    print("\noverall ratify-rate: %s   (ratified / (ratified + overridden))" %
          ("—" if overall is None else "%d%%" % round(overall * 100)))
    return 0


def _track_model(args, track_name: str) -> str:
    try:
        for t in C.load_tracks(getattr(args, "tracks", os.path.join(HERE, "tracks.json"))):
            if t.name == track_name:
                return t.model
    except Exception:
        pass
    return "?"


def cmd_announce(args) -> int:
    """Post a toot for the latest decision (the `announce` step, run AFTER the
    decision commit). No-op without MASTODON_ACCESS_TOKEN. Idempotent (one toot
    per decision id). On a posting failure: PII-safe debug + a CI ::error::
    annotation + a deduped GitHub issue + exit 1 (fail fast / report)."""
    if getattr(args, "state_dir", None):
        _apply_state_dir(args.state_dir)
    if os.environ.get("MASTODON_ANNOUNCE", "").strip().lower() in ("0", "off", "false", "no"):
        print("[announce] disabled via MASTODON_ANNOUNCE — skipping")
        return 0
    token = os.environ.get("MASTODON_ACCESS_TOKEN")
    if not token and not getattr(args, "dry_run", False):
        print("[announce] no MASTODON_ACCESS_TOKEN set — nothing to announce")
        return 0

    dry = getattr(args, "dry_run", False)
    events = load_events()
    decides = [e["payload"] for e in events
               if e.get("payload", {}).get("event") == "decide"
               and e["payload"].get("track")]
    announced_ids = {e["payload"].get("id") for e in events
                     if e.get("payload", {}).get("event") == "announced"}

    def _pid(p) -> str:
        return "%s#%d" % (p["track"], int(p.get("iteration", 0)))

    # Oldest un-announced within a small recent window: retries an outage's
    # decisions in order (not just the latest), while bounding any first-enable
    # backlog so we never flood-toot ancient history.
    recent = decides[-ANNOUNCE_LOOKBACK:]
    pending = [p for p in recent if _pid(p) not in announced_ids]
    if not pending:
        print("[announce] nothing new to announce")
        return 0
    target = pending[0]

    track = target["track"]
    n = int(target.get("iteration", 0))
    cost = float(target.get("total_cost", target.get("cost", 0.0)) or 0.0)
    did = _pid(target)

    titles = _prior_titles(track)
    title = titles[n - 1] if 1 <= n <= len(titles) else (titles[-1] if titles else "(decision)")
    model = _track_model(args, track)
    toot = _generate_toot(track, n, title, model, cost,
                          _resolve_api_key(), getattr(args, "base_url", None))
    host = (os.environ.get("MASTODON_BASE_URL") or MASTODON_DEFAULT_BASE).rstrip("/")
    visibility = os.environ.get("MASTODON_VISIBILITY") or "unlisted"
    spoiler = ("ralph · sensitive decision (review before sharing)"
               if _is_sensitive(_decision_block(track, n) or title) else None)

    # One generated image per toot (best-effort; degrades to text-only). Skipped
    # in --dry-run and when RALPH_TOOT_IMAGE=off so previews/CI stay network-light.
    media_ids = None
    if not dry and _toot_image_on():
        media_ids = _maybe_toot_image(title, host, token, _resolve_api_key(),
                                      getattr(args, "base_url", None))

    # PII-safe debug BEFORE (no token; the body is what gets broadcast anyway).
    print("[announce] -> host=%s id=%s chars=%d/%d visibility=%s sensitive=%s media=%d"
          % (host, did, len(toot), MASTODON_MAX_CHARS, visibility, bool(spoiler),
             len(media_ids or [])))
    print("[announce] body |%s|" % toot)

    if dry:
        print("[announce] --dry-run: not posting"
              + (" (image generation also skipped)" if _toot_image_on() else ""))
        return 0

    try:
        resp = _post_toot(host, token, toot, visibility, did, spoiler_text=spoiler,
                          media_ids=media_ids)
    except Exception as exc:   # noqa: BLE001 — report loudly, fail the step
        print("[announce] AFTER: FAILED %s: %s"
              % (type(exc).__name__, _short_err(exc)), file=sys.stderr)
        print("::error title=ralph announce failed::%s posting %s to %s"
              % (type(exc).__name__, did, host))
        _open_announce_failure_issue(host, did, exc)
        return 1

    status_id = (resp or {}).get("id")
    url = (resp or {}).get("url")
    print("[announce] AFTER: OK status_id=%s url=%s" % (status_id, url))
    append_event({"event": "announced", "id": did, "track": track,
                  "iteration": n, "status_id": status_id})
    _close_announce_failure_issue()   # recovered — clear any open failure issue
    return 0


_URL_RE = re.compile(r"https?://\S+")


def _mastodon_len(text: str) -> int:
    """Mastodon counts every URL as 23 chars regardless of length — budget by
    that so a post with links isn't over-truncated."""
    return len(_URL_RE.sub("u" * 23, text))


def _rnd_link(topic: str) -> str:
    return ("https://arxiv.org/search/?searchtype=all&query="
            + urllib.parse.quote(topic.strip()))


def _activity_24h() -> str:
    """Compact summary of the last ~24h of repo activity (commit subjects +
    today's ralph decisions), for the recap generator."""
    parts: list[str] = []
    log = _run(["git", "log", "--since=24 hours ago", "--pretty=%s", "-n", "40"],
               cwd=REPO_HOME)
    commits = [ln for ln in (log or "").splitlines() if ln.strip()]
    if commits:
        parts.append("commits (%d): %s" % (len(commits), "; ".join(commits[:12])))
    today = _today()
    decisions: list[str] = []
    try:
        for fn in sorted(os.listdir(DECISIONS_DIR)):
            if not fn.endswith(".ralph-log.md"):
                continue
            with open(os.path.join(DECISIONS_DIR, fn), encoding="utf-8") as f:
                for ln in f:
                    if ln.startswith("## ") and today in ln and "Decision #" in ln:
                        decisions.append(ln.split(":", 1)[-1].strip())
    except OSError:
        pass
    if decisions:
        parts.append("ralph decisions today: %s" % "; ".join(decisions[:8]))
    return "\n".join(parts) or "(quiet day — no commits or decisions)"


_RECAP_SYS = (
    "You are ralph's daily herald for a private dev community on Mastodon. Given "
    "today's repo activity, write a CLEAR and genuinely FUNNY recap — witty, not "
    "cringe, no emoji spam — in at most 220 characters. Then propose 3 SHORT R&D "
    "topics (adjacent concepts / research directions worth reading), 2-5 words "
    "each. Return JSON ONLY: {\"recap\": str, \"rnd\": [str, str, str]}."
)
_RECAP_SCHEMA = {
    "type": "json_schema",
    "json_schema": {"name": "recap", "strict": True, "schema": {
        "type": "object",
        "properties": {"recap": {"type": "string"},
                       "rnd": {"type": "array", "items": {"type": "string"}}},
        "required": ["recap", "rnd"]}}}


def _generate_recap(activity: str, stats: str, api_key: str,
                    base_url: "str | None") -> "tuple[str, list[str]]":
    """(funny recap, [3 R&D topics]) from gpt-oss; deterministic fallback."""
    if api_key:
        try:
            resp = openrouter_call(
                ANNOUNCE_MODEL,
                [{"role": "system", "content": _RECAP_SYS},
                 {"role": "user", "content": activity + "\n\nStats: " + stats}],
                api_key=api_key, temperature=0.8, max_tokens=2000,
                reasoning={"effort": "low"}, response_format=_RECAP_SCHEMA,
                base_url=base_url, span_name="ralph.recap",
                span_meta={"kind": "daily-recap"})
            text = _message_content(resp) or _reasoning_text(resp) or "{}"
            data = _parse_json_obj(text)
            recap = _strip_md((data.get("recap") or "").strip())
            rnd = [_strip_md(t) for t in (data.get("rnd") or [])
                   if isinstance(t, str) and t.strip()]
            if recap and rnd:
                return recap, rnd[:3]
            print("[recap] gen empty (finish=%s) — using fallback"
                  % _finish_reason(resp), file=sys.stderr)
        except Exception as e:   # noqa: BLE001 — fall back
            print("[recap] generation failed (%s) — using fallback"
                  % type(e).__name__, file=sys.stderr)
    return ("ralph chewed on the repo all day so you didn't have to. %s" % stats,
            ["capability-based security", "content-addressed storage", "effect systems"])


def cmd_digest(args) -> int:
    """The daily **recap** sub-announcer: once per day (around `RALPH_DIGEST_HOUR`,
    default 23:00 UTC) post a funny summary of the last 24h of repo activity +
    ratify stats + 3 R&D suggestion links. Self-gating via a dated `digest`
    ledger event. Best-effort: a failure prints a CI ::warning::, never red."""
    if getattr(args, "state_dir", None):
        _apply_state_dir(args.state_dir)
    if os.environ.get("MASTODON_ANNOUNCE", "").strip().lower() in ("0", "off", "false", "no"):
        print("[digest] disabled via MASTODON_ANNOUNCE — skipping")
        return 0
    dry = getattr(args, "dry_run", False)
    token = os.environ.get("MASTODON_ACCESS_TOKEN")
    if not token and not dry:
        print("[digest] no MASTODON_ACCESS_TOKEN set — skipping")
        return 0

    today = _today()
    if any(e.get("payload", {}).get("event") == "digest"
           and e["payload"].get("date") == today for e in load_events()):
        print("[digest] already posted today — skip")
        return 0
    hour = datetime.datetime.now(datetime.timezone.utc).hour
    try:
        trigger_hour = int(os.environ.get("RALPH_DIGEST_HOUR", "23"))
    except ValueError:
        trigger_hour = 23
    if not dry and hour < trigger_hour:
        print("[digest] before digest hour (%d<%d UTC) — skip" % (hour, trigger_hour))
        return 0

    # Ratify stats line.
    verdicts: list[str] = []
    total_dec = 0
    for t in C.load_tracks(args.tracks):
        verdicts += [r["verdict"] for r in _read_ratify(t.name)]
        total_dec += len(_prior_titles(t.name))
    rate = C.ratify_rate(verdicts)
    stats = "%d decisions total, ratify-rate %s" % (
        total_dec, "n/a" if rate is None else "%d%%" % round(rate * 100))

    recap, rnd = _generate_recap(_activity_24h(), stats,
                                 _resolve_api_key(), getattr(args, "base_url", None))
    # Cap each topic, then drop R&D items until the fixed tail leaves room for a
    # minimal recap — so an overlong gpt-oss topic can't push the toot over budget.
    topics = [t.strip()[:40] for t in rnd[:3] if t.strip()]
    while True:
        rnd_line = " · ".join("%s %s" % (t, _rnd_link(t)) for t in topics)
        fixed = (("\n\nR&D: " + rnd_line) if rnd_line else "") + "\n\n#vaked #ralph #recap"
        if not topics or MASTODON_MAX_CHARS - _mastodon_len(fixed) >= 24:
            break
        topics = topics[:-1]
    body = _truncate(recap, max(0, MASTODON_MAX_CHARS - _mastodon_len(fixed)))
    toot = body + fixed
    host = (os.environ.get("MASTODON_BASE_URL") or MASTODON_DEFAULT_BASE).rstrip("/")
    visibility = os.environ.get("MASTODON_VISIBILITY") or "unlisted"

    print("[digest] -> host=%s masto_chars=%d/%d visibility=%s"
          % (host, _mastodon_len(toot), MASTODON_MAX_CHARS, visibility))
    print("[digest] body |%s|" % toot)
    if dry:
        print("[digest] --dry-run: not posting")
        return 0

    try:
        resp = _post_toot(host, token, toot, visibility, "digest-" + today)
    except Exception as exc:   # noqa: BLE001 — digest is best-effort (no red)
        print("[digest] failed (non-fatal): %s" % type(exc).__name__, file=sys.stderr)
        print("::warning title=ralph digest failed::%s posting digest to %s"
              % (type(exc).__name__, host))
        return 0
    print("[digest] OK status_id=%s" % (resp or {}).get("id"))
    append_event({"event": "digest", "date": today,
                  "status_id": (resp or {}).get("id")})
    return 0


def cmd_watch(args) -> int:
    try:
        while True:
            status = read_status()
            last = status.get("last_step_epoch", 0) if status else 0
            out = C.render_dashboard(status, int(time.time()), last)
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.write(out)
            sys.stdout.flush()
            time.sleep(args.refresh)
    except KeyboardInterrupt:
        return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repos", default=os.path.join(HERE, "repos.json"))
    common.add_argument("--stage1-model", default=DEFAULT_S1)
    common.add_argument("--stage2-model", default=DEFAULT_S2)
    common.add_argument("--git-log-window", type=int, default=30)
    common.add_argument("--base-url", default=None,
                        help="OpenAI-compatible endpoint (default OpenRouter; or "
                             "set RALPH_BASE_URL — point at a self-hosted, "
                             "trust-boundary endpoint to keep private content local)")

    parser = argparse.ArgumentParser(prog="ralph")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_decide = sub.add_parser("decide", parents=[common])
    p_decide.add_argument("--tracks", default=os.path.join(HERE, "tracks.json"))
    p_decide.add_argument("--track", help="concept track from tracks.json (primary)")
    p_decide.add_argument("--next-track", action="store_true",
                          help="pick the next track via the event-log rotation pointer")
    p_decide.add_argument("--repo", help="DEPRECATED: repo mode (prefer --track)")
    p_decide.add_argument("--seed", type=int, default=42)
    p_decide.add_argument("--dry-run", action="store_true")
    p_decide.set_defaults(func=cmd_decide)

    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("--tracks", default=os.path.join(HERE, "tracks.json"))
    p_run.add_argument("--repo-mode", action="store_true",
                       help="DEPRECATED: round-robin whole repos instead of tracks")
    p_run.add_argument("--interval", type=int, default=900)
    p_run.add_argument("--budget-total", type=float, default=2.00)
    p_run.add_argument("--max-iters", type=int, default=0)
    p_run.add_argument("--max-ticks", type=int, default=0,
                       help="stop after this many control polls (0 = unbounded)")
    p_run.add_argument("--state-dir", default=None,
                       help="override state directory (default: tools/ralph/state/)")
    p_run.add_argument("--seed", type=int, default=42)
    p_run.set_defaults(func=cmd_run)

    p_watch = sub.add_parser("watch")
    p_watch.add_argument("--refresh", type=int, default=3)
    p_watch.set_defaults(func=cmd_watch)

    p_events = sub.add_parser("events")
    p_events.add_argument("--replay", action="store_true",
                          help="verify then print reconstructed state as JSON")
    p_events.add_argument("--state-dir", default=None,
                          help="override state directory (default: tools/ralph/state/)")
    p_events.set_defaults(func=cmd_events)

    p_ratify = sub.add_parser("ratify", help="summarize human ratify status per track")
    p_ratify.add_argument("--tracks", default=os.path.join(HERE, "tracks.json"))
    p_ratify.set_defaults(func=cmd_ratify)

    p_announce = sub.add_parser("announce", parents=[common],
                                help="post the latest decision to Mastodon (post-commit)")
    p_announce.add_argument("--tracks", default=os.path.join(HERE, "tracks.json"))
    p_announce.add_argument("--state-dir", default=None,
                            help="override state directory (default: tools/ralph/state/)")
    p_announce.add_argument("--dry-run", action="store_true",
                            help="build + print the toot without posting")
    p_announce.set_defaults(func=cmd_announce)

    p_digest = sub.add_parser("digest", parents=[common],
                              help="post a once-daily ratify-rate digest toot")
    p_digest.add_argument("--tracks", default=os.path.join(HERE, "tracks.json"))
    p_digest.add_argument("--state-dir", default=None,
                          help="override state directory (default: tools/ralph/state/)")
    p_digest.add_argument("--dry-run", action="store_true",
                          help="build + print the digest without posting")
    p_digest.set_defaults(func=cmd_digest)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    finally:
        _flush_langfuse()   # ship any buffered spans (no-op when tracing is off)


if __name__ == "__main__":
    raise SystemExit(main())
