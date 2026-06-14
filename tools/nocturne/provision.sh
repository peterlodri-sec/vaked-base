#!/usr/bin/env bash
# nocturne provisioning — rent / wait / self-destruct a Vast.ai GPU under hard cost caps.
#
# THE COST LYNCHPIN: `rent` arms a detached `watch-and-destroy` that force-destroys the
# instance after MAX_MINUTES no matter what — so even if the orchestrator crashes, the box
# cannot keep billing. Always-teardown is not best-effort here; it is a separate watchdog.
#
# Subcommands:
#   search                 print cheapest matching offers (no spend)
#   rent                   search -> create cheapest under cap -> wait running -> arm watchdog
#   ssh   "<cmd>"          run a command on the rented box (uses saved ssh coords)
#   put   <local> <remote> scp a file/dir up;   get <remote> <local>  scp down
#   destroy                destroy the instance + cancel the watchdog (idempotent)
#
# Flags: --dry-run (print the exact plan + estimate, rent/destroy nothing, exit 0)
#
# Env (with defaults sized for the karpathy-matched H100 validation):
#   VAST_API_KEY (required for real ops)   GPU_NAME=H100_SXM   MAX_DPH=3.0   NUM_GPUS=1
#   DISK_GB=64   IMAGE=pytorch/pytorch:2.9.1-cuda12.8-cudnn9-runtime   MAX_MINUTES=150
#   MIN_CUDA=12.8   MIN_RELIABILITY=0.95   STATE_DIR=tools/nocturne/state
set -euo pipefail

GPU_NAME="${GPU_NAME:-H100_SXM}"
MAX_DPH="${MAX_DPH:-3.0}"
NUM_GPUS="${NUM_GPUS:-1}"
DISK_GB="${DISK_GB:-64}"
IMAGE="${IMAGE:-pytorch/pytorch:2.9.1-cuda12.8-cudnn9-runtime}"
MAX_MINUTES="${MAX_MINUTES:-150}"
MIN_CUDA="${MIN_CUDA:-12.8}"
MIN_RELIABILITY="${MIN_RELIABILITY:-0.95}"
STATE_DIR="${STATE_DIR:-$(cd "$(dirname "$0")/state" && pwd)}"
INST_FILE="$STATE_DIR/.instance"
WATCH_FILE="$STATE_DIR/.watchdog.pid"
DRY=0; [[ "${1:-}" == "--dry-run" ]] && { DRY=1; shift; }
CMD="${1:-search}"; shift || true

QUERY="gpu_name=${GPU_NAME} num_gpus=${NUM_GPUS} cuda_max_good>=${MIN_CUDA} \
reliability2>=${MIN_RELIABILITY} dph_total<=${MAX_DPH} rentable=true disk_space>=${DISK_GB}"

log() { echo "[provision] $*" >&2; }
need_key() { [[ -n "${VAST_API_KEY:-}" ]] || { log "FATAL: VAST_API_KEY not set"; exit 2; }; }
auth() { need_key; vastai set api-key "$VAST_API_KEY" >/dev/null; }

cheapest_offer() {  # -> "<offer_id> <dph>"
  vastai search offers "$QUERY" -o 'dph_total' --raw \
    | python3 -c 'import json,sys; o=json.load(sys.stdin); print(o[0]["id"], o[0]["dph_total"]) if o else sys.exit("no offers under cap")'
}

case "$CMD" in
  search)
    log "query: $QUERY"
    if [[ $DRY -eq 1 ]]; then
      log "DRY-RUN — would run: vastai search offers \"$QUERY\" -o dph_total"
      log "est. ceiling: \$${MAX_DPH}/hr × $((MAX_MINUTES))min = \$$(python3 -c "print(round(${MAX_DPH}*${MAX_MINUTES}/60,2))")"
      exit 0
    fi
    auth; vastai search offers "$QUERY" -o 'dph_total' | head -15
    ;;

  rent)
    if [[ $DRY -eq 1 ]]; then
      log "DRY-RUN plan:"
      log "  1) vastai search offers \"$QUERY\" -o dph_total  (pick cheapest)"
      log "  2) vastai create instance <id> --image $IMAGE --disk $DISK_GB --ssh --direct --onstart-cmd <bootstrap>"
      log "  3) poll 'vastai show instance <id> --raw' until actual_status=running + ssh ready"
      log "  4) arm watch-and-destroy: destroy after ${MAX_MINUTES}min unconditionally"
      log "  est. ceiling: \$$(python3 -c "print(round(${MAX_DPH}*${MAX_MINUTES}/60,2))") (\$${MAX_DPH}/hr cap)"
      exit 0
    fi
    auth
    read -r OID DPH < <(cheapest_offer)
    log "cheapest offer $OID @ \$${DPH}/hr (cap \$${MAX_DPH})"
    NEW=$(vastai create instance "$OID" --image "$IMAGE" --disk "$DISK_GB" --ssh --direct --raw \
          | python3 -c 'import json,sys; print(json.load(sys.stdin)["new_contract"])')
    echo "$NEW" > "$INST_FILE"
    log "instance $NEW created; waiting for running…"
    for _ in $(seq 1 60); do
      ST=$(vastai show instance "$NEW" --raw | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("actual_status"), d.get("ssh_host") or "", d.get("ssh_port") or "")')
      read -r STATUS SSH_HOST SSH_PORT <<<"$ST"
      [[ "$STATUS" == "running" && -n "$SSH_HOST" ]] && break
      sleep 10
    done
    [[ "${STATUS:-}" == "running" ]] || { log "instance never reached running — destroying"; vastai destroy instance "$NEW" || true; exit 1; }
    printf '%s %s %s\n' "$NEW" "$SSH_HOST" "$SSH_PORT" > "$INST_FILE"
    log "running: ssh -p $SSH_PORT root@$SSH_HOST"
    # arm the self-destruct watchdog (detached; survives orchestrator death)
    ( sleep "$((MAX_MINUTES*60))"; vastai set api-key "$VAST_API_KEY" >/dev/null 2>&1; \
      vastai destroy instance "$NEW" >/dev/null 2>&1; echo "[watchdog] destroyed $NEW after ${MAX_MINUTES}min" >&2 ) &
    echo $! > "$WATCH_FILE"
    log "watch-and-destroy armed (pid $(cat "$WATCH_FILE"), ${MAX_MINUTES}min hard cap)"
    ;;

  ssh|put|get)
    [[ -f "$INST_FILE" ]] || { log "no instance"; exit 1; }
    read -r _ HOST PORT < "$INST_FILE"
    SSHOPT="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
    case "$CMD" in
      ssh)  ssh $SSHOPT -p "$PORT" "root@$HOST" "$@" ;;
      put)  scp $SSHOPT -P "$PORT" -r "$1" "root@$HOST:$2" ;;
      get)  scp $SSHOPT -P "$PORT" -r "root@$HOST:$1" "$2" ;;
    esac
    ;;

  destroy)
    if [[ $DRY -eq 1 ]]; then log "DRY-RUN — would destroy $(cat "$INST_FILE" 2>/dev/null || echo '<none>')"; exit 0; fi
    [[ -f "$WATCH_FILE" ]] && { kill "$(cat "$WATCH_FILE")" 2>/dev/null || true; rm -f "$WATCH_FILE"; }
    if [[ -f "$INST_FILE" ]]; then
      auth; ID=$(cut -d' ' -f1 "$INST_FILE")
      vastai destroy instance "$ID" && log "destroyed $ID" || log "destroy reported error (may already be gone)"
      rm -f "$INST_FILE"
    else
      log "no instance to destroy"
    fi
    ;;

  *) log "unknown subcommand: $CMD"; exit 2 ;;
esac
