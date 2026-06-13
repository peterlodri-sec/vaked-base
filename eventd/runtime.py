"""eventd.runtime — the phase-3 runtime-operational fold (state = fold).

eventd's state model is *the fold over the log* (design phase 3). The
state-dependency layer (``eventd.statedep``) already folds the RFC 0004
artifacts into a ``DependencyIndex``; this module folds the **runtime
operational** events — workflow runs and their step lifecycle — that
``agent-supervisord``'s ``workflow_engine`` emits as it drives a run of a
lowered ``gen/workflow/<name>.json`` (the supervisord design).

This is the OPERATIONAL fold (which runs/steps exist and their status); the
arena-backed reconstruction of typed graph-node *content* stays gated on the
#16 arena. The oracle defines the fold semantics the BEAM/Zig ports reproduce.

Event vocabulary (logged payloads, ``kind`` + ``v`` like statedep; run/step
are opaque string ids, ``attempt`` is a 1-based int):

  run_started   {run, workflow}
  step_started  {run, step, agent, attempt}
  step_finished {run, step}
  step_failed   {run, step, attempt}
  run_finished  {run, status}            status ∈ completed|failed|aborted

Fold semantics (deterministic, latest-event-wins in log order):

  * a step's ``status`` is the last lifecycle event for it
    (``running`` → ``done`` / ``failed``);
  * ``attempts`` is the highest ``attempt`` seen for the step (retries emit a
    fresh ``step_started`` with the next attempt number);
  * a run's ``status`` is ``running`` until a ``run_finished`` sets it;
  * events referencing a run before its ``run_started`` are tolerated (the run
    is created lazily) — the log is the time axis, a torn prefix shouldn't
    crash the fold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

KIND_RUN_STARTED = "run_started"
KIND_STEP_STARTED = "step_started"
KIND_STEP_FINISHED = "step_finished"
KIND_STEP_FAILED = "step_failed"
KIND_RUN_FINISHED = "run_finished"

RUNTIME_V = 1

_RUN_STATUS = ("completed", "failed", "aborted")


def _require_int(name: str, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    return value


def _attempt_of(payload: dict) -> int:
    """Read ``attempt`` from a RAW log payload without laundering: a clean int
    (not bool) is kept; anything else (float drift, bool, missing, string from
    a foreign/hand-written writer) folds to 1. The constructors already reject
    bad attempts; the fold is the cross-runtime boundary the BEAM/Zig ports
    reproduce, so it must not silently ``int()``-coerce ``2.9`` to ``2``."""
    a = payload.get("attempt", 1)
    return a if (isinstance(a, int) and not isinstance(a, bool)) else 1


# --------------------------------------------------------------------------- #
# Payload constructors (the logged form the workflow_engine appends)
# --------------------------------------------------------------------------- #

def run_started(run: str, workflow: str) -> dict:
    return {"kind": KIND_RUN_STARTED, "v": RUNTIME_V,
            "run": run, "workflow": workflow}


def step_started(run: str, step: str, agent: str, attempt: int = 1) -> dict:
    return {"kind": KIND_STEP_STARTED, "v": RUNTIME_V, "run": run,
            "step": step, "agent": agent,
            "attempt": _require_int("attempt", attempt)}


def step_finished(run: str, step: str) -> dict:
    return {"kind": KIND_STEP_FINISHED, "v": RUNTIME_V, "run": run,
            "step": step}


def step_failed(run: str, step: str, attempt: int) -> dict:
    return {"kind": KIND_STEP_FAILED, "v": RUNTIME_V, "run": run,
            "step": step, "attempt": _require_int("attempt", attempt)}


def run_finished(run: str, status: str) -> dict:
    if status not in _RUN_STATUS:
        raise ValueError(f"run status must be one of {_RUN_STATUS}: {status!r}")
    return {"kind": KIND_RUN_FINISHED, "v": RUNTIME_V, "run": run,
            "status": status}


# --------------------------------------------------------------------------- #
# The fold
# --------------------------------------------------------------------------- #

@dataclass
class StepState:
    status: str = "pending"        # running | done | failed (pending = unseen)
    attempts: int = 0


@dataclass
class RunState:
    workflow: str | None = None
    status: str = "running"        # running until a run_finished sets it
    steps: dict = field(default_factory=dict)   # step name -> StepState


class RuntimeState:
    """Fold of the runtime-operational events in a verified log: ``runs`` maps
    a run id to its :class:`RunState`. Build with :meth:`fold`."""

    def __init__(self):
        self.runs: dict[str, RunState] = {}

    def _run(self, run_id: str) -> RunState:
        return self.runs.setdefault(run_id, RunState())

    def _step(self, run_id: str, step: str) -> StepState:
        return self._run(run_id).steps.setdefault(step, StepState())

    @classmethod
    def fold(cls, entries: list[dict]) -> "RuntimeState":
        st = cls()
        for e in entries:
            p = e.get("payload", {})
            kind = p.get("kind")
            if kind == KIND_RUN_STARTED:
                run = st._run(p["run"])
                run.workflow = p.get("workflow")
                # last-event-wins: any run_started (re)sets status to running.
                # run ids are assumed unique per run; a reused id therefore
                # resurrects a finished run — accepted, by the same torn-prefix
                # / log-is-the-time-axis tolerance as lazy run creation.
                run.status = "running"
            elif kind == KIND_STEP_STARTED:
                s = st._step(p["run"], p["step"])
                s.status = "running"
                s.attempts = max(s.attempts, _attempt_of(p))
            elif kind == KIND_STEP_FINISHED:
                st._step(p["run"], p["step"]).status = "done"
            elif kind == KIND_STEP_FAILED:
                s = st._step(p["run"], p["step"])
                s.status = "failed"
                s.attempts = max(s.attempts, _attempt_of(p))
            elif kind == KIND_RUN_FINISHED:
                # validate on read (the fold is the port-parity surface): an
                # unrecognized terminal status is malformed — a finish we can't
                # classify is not a success, so it folds to "failed".
                status = p.get("status")
                st._run(p["run"]).status = (
                    status if status in _RUN_STATUS else "failed")
        return st

    def summary(self) -> dict:
        """A JSON-able view for the CLI: per run, its workflow/status and a
        step-status histogram, plus run/step totals. Deterministic (runs and
        steps emitted in sorted id order)."""
        runs = {}
        for rid in sorted(self.runs):
            r = self.runs[rid]
            hist = {}
            for sname in sorted(r.steps):
                hist[r.steps[sname].status] = hist.get(
                    r.steps[sname].status, 0) + 1
            runs[rid] = {"workflow": r.workflow, "status": r.status,
                         "steps": len(r.steps), "by_status": hist}
        return {"runs": runs, "total_runs": len(self.runs)}
