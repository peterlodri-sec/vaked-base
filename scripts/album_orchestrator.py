#!/usr/bin/env python3
"""album_orchestrator.py — Full Album E2E Release Scaffold & Automation Engine for Vaked Constellation.

Album: "SOVEREIGN FREQUENCIES: THE FULL CONSTELLATION ALBUM" (8 Tracks, ~41 Minutes)
"""

from __future__ import annotations

import os
import sys
import math
import wave
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, "/Users/lodripeter/workspace/peterlodri-sec/vaked-sentinel/scripts")
import soundcloud_publisher
import youtube_publisher

ALBUM_TITLE = "<3-1:P-peter SOVEREIGN FREQUENCIES (THE FULL CONSTELLATION ALBUM)"
ARTIST = "Peter Lodri & vaked.dev"
GENRE = "Cybernetic Psytrance / Melodic Progressive"
LICENSE = "CC BY-NC-SA 4.0 International (Creative Commons Attribution-NonCommercial-ShareAlike 4.0)"
PURCHASE_URL = "https://patreon.com/peterlodri"

OUT_DIR = Path("/Users/lodripeter/.gemini/antigravity-cli/brain/58b8f08f-d1af-47fc-af4f-749696347093/scratch/album_sovereign_frequencies")
OUT_DIR.mkdir(parents=True, exist_ok=True)

manifest_path = OUT_DIR / "album_manifest.json"
cover_path = OUT_DIR / "album_box_cover_2048x2048.jpg"

print("=== 💿 FULL E2E ALBUM ORCHESTRATION ENGINE ===")

# ── 1. ALBUM TRACKLIST MANIFEST & CHAPTER TIMESTAMPS ──

TRACKS = [
    {"num": 1, "title": "<3-1:P-peter QUANTUM GALACTIC EYE", "key": "F minor", "bpm": 145, "dur": 210, "desc": "Cybernetic Diatonic Opening"},
    {"num": 2, "title": "<3-1:P-peter SINGULARITY HORIZON", "key": "C minor", "bpm": 145, "dur": 240, "desc": "Deep Sub Bass Attractor"},
    {"num": 3, "title": "<3-1:P-peter RECURSION ENGINE", "key": "G minor", "bpm": 145, "dur": 255, "desc": "Arpeggiated Pulse Mesh"},
    {"num": 4, "title": "<3-1:P-peter SPACE GHOST RIDER", "key": "D minor", "bpm": 145, "dur": 270, "desc": "High Resonance Elevation"},
    {"num": 5, "title": "<3-1:P-peter ULTRA LOVE GOD", "key": "A minor", "bpm": 145, "dur": 300, "desc": "Sovereign Elevation Anthem"},
    {"num": 6, "title": "<3-1:P-peter POLAR GALAXY MERGE", "key": "F# minor", "bpm": 145, "dur": 330, "desc": "Polar Attractor Fusion"},
    {"num": 7, "title": "<3-1:P-peter SMALL TALK (EXTENDED JOURNEY)", "key": "F# minor", "bpm": 145, "dur": 480, "desc": "8-Min Deep Ambient Journey"},
    {"num": 8, "title": "<3-1:P-peter COGITO ERGO SUM (FINALE)", "key": "C# minor", "bpm": 145, "dur": 360, "desc": "432Hz Resolution Finale"}
]

# Calculate YouTube Chapter Timestamps
chapters = []
current_sec = 0

for tr in TRACKS:
    m = current_sec // 60
    s = current_sec % 60
    time_str = f"{m:02d}:{s:02d}"
    chapters.append(f"{time_str} - Track {tr['num']:02d}: {tr['title']} ({tr['key']})")
    current_sec += tr['dur']

total_m = current_sec // 60
total_s = current_sec % 60
total_time_str = f"{total_m}m {total_s}s"

album_manifest = {
    "title": ALBUM_TITLE,
    "artist": ARTIST,
    "genre": GENRE,
    "license": LICENSE,
    "total_duration": total_time_str,
    "total_seconds": current_sec,
    "tracks": TRACKS,
    "chapters": chapters
}

with open(manifest_path, "w") as f:
    json.dump(album_manifest, f, indent=2)

print(f"  ✅ Album Manifest Synthesized: {manifest_path} ({len(TRACKS)} tracks, {total_time_str})")

# ── 2. MASTER 2048x2048 ALBUM BOX ARTWORK RENDERING ──

def render_album_box_art(out_file: Path):
    """Render 2048x2048 Master Album Box Artwork with 8-track constellation mesh."""
    img = Image.new("RGB", (2048, 2048), (5, 6, 10))
    draw = ImageDraw.Draw(img)

    # Multi-ring galaxy background
    cx, cy = 1024, 1024
    for r in range(960, 50, -20):
        color = (int(98 + r * 0.08), int(230 - r * 0.05), int(201 + r * 0.02))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=3)

    # Track orbital nodes
    for i, tr in enumerate(TRACKS):
        angle = i * (2 * math.pi / len(TRACKS))
        nx = int(cx + math.cos(angle) * 650)
        ny = int(cy + math.sin(angle) * 650)
        draw.ellipse([nx - 40, ny - 40, nx + 40, ny + 40], fill=(180, 139, 255, 200), outline=(98, 230, 201), width=4)

    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Courier New Bold.ttf", 64)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Supplemental/Courier New.ttf", 40)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = font_title

    draw.text((120, 1720), "<3-1:P-peter SOVEREIGN FREQUENCIES", fill=(98, 230, 201), font=font_title)
    draw.text((120, 1810), f"THE FULL CONSTELLATION ALBUM · 8 TRACKS · {total_time_str}", fill=(180, 139, 255), font=font_sub)
    draw.text((120, 1880), f"{LICENSE} · LOVETTA LANE EDITIONS", fill=(255, 207, 92), font=font_sub)

    img.save(out_file, "JPEG", quality=95)
    print(f"  ✅ 2048x2048 Master Album Box Artwork Rendered: {out_file}")

render_album_box_art(cover_path)

# ── 3. TELEGRAM ASCII FULL ALBUM SHOWCASE BROADCAST ──

def broadcast_telegram_album_showcase():
    """Broadcast full album ASCII card with chapters to Telegram."""
    chapters_formatted = "\n".join([f"  {c}" for c in chapters])
    
    ascii_album_card = f"""
🌌 ════════════════════════════════════════════════ 🌌
   ✦ SOVEREIGN FREQUENCIES: FULL ALBUM SCAFFOLD ✦     
   0 + 1 · THE FINE TOUCH FROM WITHIN               
 🌌 ════════════════════════════════════════════════ 🌌

 💿 Album:    {ALBUM_TITLE}
 ⏱ Duration: {total_time_str} ({len(TRACKS)} Master Tracks)
 📜 License:  CC BY-NC-SA 4.0 International
 💖 Support:  https://patreon.com/peterlodri

 🎼 ALBUM CHAPTER TIMESTAMPS:
{chapters_formatted}

 ⚡ Mesh status: FULL ALBUM SCAFFOLD READY FOR RELEASE
"""

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print(ascii_album_card)
        return

    import httpx
    card_text = ascii_album_card.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    msg = f"<code>{card_text}</code>"
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        httpx.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5.0)
        print("  ✅ Telegram ASCII Full Album Showcase Broadcasted!")
    except Exception as e:
        print("  ❌ Telegram Album Broadcast Exception:", e)

broadcast_telegram_album_showcase()

print("\n🎉 FULL E2E ALBUM SCAFFOLD FOR 'SOVEREIGN FREQUENCIES' COMPLETE & SYNTHESIZED!")
