"""ralph-vastai — GPU cloud client for the ralph decision loop.
  1:1 API with @vaked/openrouter-ts/src/vastai.ts
  Python stdlib only. Guarded — no-op when VAST_API_KEY is unset.
  GENESIS_SEAL: 7c242080
"""
import json, os, urllib.request, urllib.parse, ssl, time
BASE = "https://console.vast.ai/api/v0"
API_KEY = os.environ.get("VAST_API_KEY", "")
def _api(method: str, path: str, body: dict | None = None) -> dict:
    if not API_KEY:
        return {"error": "VAST_API_KEY not set", "offers": []}
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e), "offers": [], "instances": []}
def search_offers(query: str, limit: int = 5) -> list[dict]:
    q = urllib.parse.quote(f"{query} verified=true")
    result = _api("GET", f"/bundles/?q={q}&limit={limit}")
    return result.get("offers", [])
def show_instances() -> list[dict]:
    result = _api("GET", "/instances/")
    return result.get("instances", [])
def create_instance(offer_id: int, image: str = "pytorch/pytorch", disk: int = 32) -> dict:
    return _api("POST", "/asks/", {
        "client_id": "ralph-vaked",
        "image": image,
        "disk": disk,
        "ask_contract_id": offer_id,
    })
def destroy_instance(instance_id: int) -> dict:
    return _api("DELETE", f"/instances/{instance_id}/")
def start_instance(instance_id: int) -> dict:
    return _api("PUT", f"/instances/{instance_id}/", {"actual_status": "running"})
def stop_instance(instance_id: int) -> dict:
    return _api("PUT", f"/instances/{instance_id}/", {"actual_status": "stopped"})
def cheapest_gpu(gpu_name: str = "RTX_4090", min_gpus: int = 1) -> dict | None:
    """Ralph-specific: find the cheapest GPU offer for a given GPU name."""
    offers = search_offers(f"gpu_name={gpu_name} num_gpus>={min_gpus}")
    if not offers:
        return None
    return min(offers, key=lambda o: o.get("dph_total", float("inf")))
def launch_cheapest(gpu_name: str = "RTX_4090", image: str = "pytorch/pytorch", disk: int = 32) -> dict:
    """Ralph-specific: find and launch the cheapest GPU in one call."""
    offer = cheapest_gpu(gpu_name)
    if not offer:
        return {"error": f"No {gpu_name} offers found"}
    result = create_instance(offer["id"], image, disk)
    result["offer"] = {"gpu_name": offer.get("gpu_name"), "dph_total": offer.get("dph_total")}
    return result
# ── CLI for testing ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: vastai.py search|instances|cheapest|launch")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "search":
        offers = search_offers(sys.argv[2] if len(sys.argv) > 2 else "RTX_4090")
        for o in offers[:5]:
            print(f"  {o['gpu_name']} x{o['num_gpus']} ${o['dph_total']}/hr id={o['id']}")
    elif cmd == "instances":
        for i in show_instances():
            print(f"  #{i['id']} {i['gpu_name']} {i['actual_status']} ${i['dph_total']}/hr")
    elif cmd == "cheapest":
        c = cheapest_gpu(sys.argv[2] if len(sys.argv) > 2 else "RTX_4090")
        print(f"  {c['gpu_name']} ${c['dph_total']}/hr id={c['id']}" if c else "No offers")
    elif cmd == "launch":
        r = launch_cheapest(sys.argv[2] if len(sys.argv) > 2 else "RTX_4090")
        print(json.dumps(r, indent=2))