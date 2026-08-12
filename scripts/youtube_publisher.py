#!/usr/bin/env python3
"""youtube_publisher.py — Automated YouTube Data API v3 Music Video Publisher for Channel UCiHo-77epw2s8nPd1XYwmSQ.
"""

from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

log = logging.getLogger("youtube-publisher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def publish_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    client_secret_path: str = "/Users/lodripeter/workspace/peterlodri-sec/vaked-sentinel/client_secret.json",
    token_path: str = "/Users/lodripeter/workspace/peterlodri-sec/vaked-sentinel/youtube_token.json",
    is_cc_license: bool = True
) -> str | None:
    """Upload MP4 music video to YouTube Channel UCiHo-77epw2s8nPd1XYwmSQ."""
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if not os.path.exists(client_secret_path):
            log.error("❌ client_secret.json hiányzik a megadott útvonalon: %s", client_secret_path)
            return None
        log.info("🔑 Initializing OAuth Flow for YouTube Channel UCiHo-77epw2s8nPd1XYwmSQ...")
        flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        log.info("✅ Credentials Saved to %s!", token_path)

    youtube = build("youtube", "v3", credentials=creds)

    # YouTube Data API disallows < and > in video titles and descriptions
    clean_title = title.replace("<", "[").replace(">", "]")
    clean_description = description.replace("<", "[").replace(">", "]")

    body = {
        "snippet": {
            "title": clean_title,
            "description": clean_description,
            "tags": tags or ["Cybernetic Psytrance", "Lovetta Lane", "Vaked Dev", "Polar Attractor"],
            "categoryId": "10" # 10 = Music Category
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "license": "creativeCommon" if is_cc_license else "youtube"
        }
    }

    log.info("📺 YouTube videó feltöltése folyamatban: %s...", title)
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = request.execute()
    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    log.info("✅ Sikeres YouTube Feltöltés! Link: %s", video_url)
    return video_url

if __name__ == "__main__":
    import sys
    video_file = sys.argv[1] if len(sys.argv) > 1 else None
    if video_file and os.path.exists(video_file):
        publish_to_youtube(
            video_file,
            title="<3-1:P-peter POLAR GALAXY MERGE (Official 4K Visualizer)",
            description=(
                "🌌 <3-1:P-peter POLAR GALAXY MERGE — Sovereign Frequencies EP Vol. 2\n\n"
                "🎵 Audio: 24-bit / 96kHz Lossless Master\n"
                "📜 License: CC BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike)\n"
                "💖 Lovetta Lane Support: https://patreon.com/peterlodri\n\n"
                "vaked.dev constellation · 0 + 1 · fine touch from within"
            )
        )
    else:
        print("Usage: python3 youtube_publisher.py <video.mp4>")
