"""Vaked Swarm — Agentic Inbox bridge via MCP protocol.

Connects to the Cloudflare Agentic Inbox through the MCP server.
Uses Cloudflare Access Service Token for auth.
"""
import json, time, os, ssl, subprocess

INBOX_MCP = "https://agentic-inbox.cabotage.workers.dev/mcp"

# Cloudflare Access service token (machine-to-machine, permanent)
CF_CLIENT_ID = "9b552a3d613b258acedda2d8b9589f2a.access"
CF_CLIENT_SECRET = "015b5ef996b08af7f85623e70d195ed798d9270f5c0df0777f8c22b110a32628"
SENDER = "swarm@vaked.dev"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def mcp_initialize() -> str:
    """Initialize MCP session, return session ID from response header."""
    try:
        result = subprocess.run([
            "curl", "-sk", "-D", "-", "--connect-timeout", "10", "--max-time", "20",
            "-H", f"CF-Access-Client-Id: {CF_CLIENT_ID}",
            "-H", f"CF-Access-Client-Secret: {CF_CLIENT_SECRET}",
            "-H", "Content-Type: application/json",
            "-H", "Accept: application/json, text/event-stream",
            "-d", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "vaked-swarm", "version": "0.1"}}}),
            INBOX_MCP,
        ], capture_output=True, text=True, timeout=25)
        for line in result.stdout.split("\n"):
            if "mcp-session-id:" in line.lower():
                return line.split(":", 1)[1].strip()
        return ""
    except Exception as e:
        return ""


def _mcp_call(method: str, params: dict = None, session_id: str = "") -> dict:
    """Raw MCP call via curl."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    headers = [
        "-H", f"CF-Access-Client-Id: {CF_CLIENT_ID}",
        "-H", f"CF-Access-Client-Secret: {CF_CLIENT_SECRET}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json, text/event-stream",
    ]
    if session_id:
        headers.extend(["-H", f"Mcp-Session-Id: {session_id}"])
    
    try:
        result = subprocess.run(
            ["curl", "-sk", "--connect-timeout", "10", "--max-time", "20",
             *headers, "-d", json.dumps(payload), INBOX_MCP],
            capture_output=True, text=True, timeout=25)
        if result.returncode == 0 and result.stdout.strip():
            # Parse SSE format: "event: message\ndata: {json}\n\n"
            for line in result.stdout.split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
        if result.stdout.strip():
            return json.loads(result.stdout)  # fallback: plain JSON
        return {"error": result.stderr[:200] if result.stderr else "no response"}
    except Exception as e:
        return {"error": str(e)}


def list_mailboxes() -> list:
    """List available mailboxes in the Agentic Inbox."""
    session_id = mcp_initialize()
    if not session_id:
        return []
    result = _mcp_call("tools/call", {"name": "list_mailboxes", "arguments": {}}, session_id)
    text = result.get("result", {}).get("content", [{}])[0].get("text", "[]")
    try:
        mailboxes = json.loads(text)
        if isinstance(mailboxes, list):
            return [m.get("id", "") for m in mailboxes]
    except:
        pass
    return []


def send_via_mcp(to: str, subject: str, body: str) -> dict:
    """Send an email through the Agentic Inbox MCP server."""
    session_id = mcp_initialize()
    if not session_id:
        return {"error": "failed to initialize MCP session"}
    
    return _mcp_call("tools/call", {
        "name": "send_email",
        "arguments": {
            "to": to,
            "subject": subject,
            "text": body,
            "bodyHtml": f"<pre>{body}</pre>",
            "from": SENDER,
            "mailboxId": "agent@aginbx.com",
        },
    }, session_id)


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
        return send_via_mcp("peter.lodri@gmail.com", f"swarm: {line[:60]}", body)
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
        return send_via_mcp("peter.lodri@gmail.com", subject, report)
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
        result = send_via_mcp(
            "peter.lodri@gmail.com",
            "vaked swarm: inbox test",
            "The swarm sends greetings through the agentic inbox. All nodes active. Trust: 1.000. Genesis seal holds.\n\n— vaked swarm · constellation.vaked.dev"
        )
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python3 inbox.py [monologue|audit|test]")
