"""Vaked Swarm — Agentic Inbox bridge.

Sends swarm monologues, audit reports, and graveyard notices
through the Cloudflare Agentic Inbox email endpoint.
"""
import json, time, hashlib, urllib.request, os, ssl

INBOX_URL = "https://agentic-inbox.cabotage.workers.dev"
SENDER = "swarm@vaked.dev"


def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via the Agentic Inbox API."""
    payload = {
        "to": to,
        "from": SENDER,
        "subject": subject,
        "text": body,
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(
            f"{INBOX_URL}/api/send",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def send_monologue():
    """Send the current monologue as a daily email."""
    try:
        mono_path = "/var/www/monologue/index.json"
        if not os.path.isfile(mono_path):
            mono_path = None
        line = "the swarm has no words today."
        if mono_path:
            with open(mono_path) as f:
                data = json.load(f)
            line = data.get("line", line)

        body = f"""{line}

---
vaked swarm · https://constellation.vaked.dev
genesis seal: 7c242080
sent via agentic inbox
"""
        return send_email("peter.lodri@gmail.com", f"swarm: {line[:60]}", body)
    except Exception as e:
        return {"error": str(e)}


def send_audit_report():
    """Send the latest Ralph audit as an email."""
    try:
        reflection_dir = "notes/REFLECTIONS"
        files = sorted(os.listdir(reflection_dir))
        if not files:
            return {"error": "no reflections found"}

        latest = files[-1]
        with open(os.path.join(reflection_dir, latest)) as f:
            report = f.read()

        subject = f"Ralph Audit: {latest.split('-')[0]}"
        return send_email("peter.lodri@gmail.com", subject, report)
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "monologue"
    if cmd == "monologue":
        print(json.dumps(send_monologue(), indent=2))
    elif cmd == "audit":
        print(json.dumps(send_audit_report(), indent=2))
    elif cmd == "test":
        result = send_email(
            "peter.lodri@gmail.com",
            "vaked swarm: inbox test",
            "The swarm sends greetings through the agentic inbox. All nodes active. Trust: 1.000. Genesis seal holds.\n\n— vaked swarm · constellation.vaked.dev"
        )
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python3 inbox.py [monologue|audit|test]")
