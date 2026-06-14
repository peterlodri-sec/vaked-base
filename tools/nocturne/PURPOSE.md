# nocturne — purpose & research goal

> The driver injects this file's spirit as the mission frame: nocturne exists to run **real
> overnight ML experiments**, keep only what **measurably** wins, and stay silent otherwise.

## Purpose

nocturne is the fleet's **empirical** researcher — the third abstain-by-default sibling to `ralph`
(reasons over project structure) and `optitron` (crawls the literature). Where they think and read,
nocturne **runs experiments**: each night it rents a single Vast.ai GPU, ports Karpathy's
`autoresearch` mutate→train→keep/discard loop onto proven rent/teardown/secrets scaffolding, and
chases a lower `val_bpb` under a fixed 5-minute-per-trial budget — then **tears the box down**.

Abstaining is success. A night that beats nothing produces a ledger entry and nothing else. Only a
result that **clears the committed baseline AND is re-confirmed on independent seeds AND is novel**
is escalated — via an `agent` issue that `workflow_dispatch`es `swe_af` to open a *promote-the-
baseline* PR (never auto-merged). A hallucinated or lucky-seed "win" is a failure worse than silence.

## The bet

GPU dollars are the dominant risk, so the design inverts the usual trust: the GHA side is only the
**clock, the wallet, and the scribe** — it never trains. The rented box does the work behind a hard
`$/hr` cap and a `watch-and-destroy` self-destruct that fires even if the orchestrator dies. The
question nocturne tests: **can a budgeted, abstain-by-default nightly loop — one structured
OpenRouter mutation per trial, measured against a frozen `evaluate_bpb` — compound a
version-controlled baseline of real training improvements that a human mostly *ratifies*?**

Measured as the baseline advances: **win-rate** (nights that clear the gate), **\$/confirmed-win**,
and **ratify-rate** of the resulting swe_af PRs.
