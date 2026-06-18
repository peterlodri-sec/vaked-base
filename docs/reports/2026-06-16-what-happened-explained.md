# What happened tonight — explained for everyone

*A single, self-contained walk-through of one small but complete piece of work on the
Vaked project. Written so a non-technical reader can follow the whole story and learn one
genuinely useful idea, with the exact technical steps at the end so anyone can reproduce
it. No prior knowledge assumed.*

---

## The one-sentence version

We took three "blueprints" for computer systems, asked a tool to turn them into real
configuration files, noticed the tool was printing a misleading line in its summary,
fixed that, and proved the fix worked — all on one laptop, with nothing sent anywhere.

If you only read one paragraph, that's it. The rest explains *why each part matters* and
*what's worth learning from it*.

---

## Part 1 — The big idea, with no jargon

Imagine you want to open a coffee shop. You could either:

- **(A)** Hire each person one by one, hand each a vague verbal instruction, and just
  *hope* nobody does something they shouldn't — like the new barista quietly rewriting the
  menu, or the dishwasher wiring money out of the till.
- **(B)** Write a single clear plan up front that says exactly who is allowed to do what:
  *the barista makes drinks, only the manager touches the till, the dishwasher never goes
  near the menu.* Then have a checker read that plan and refuse to open the shop if the
  plan lets anyone do something dangerous.

**Vaked is approach (B), but for computer systems.** You write a plan — Vaked calls it a
*capability graph* — that lists every "worker" (a program, a service, an AI agent) and
exactly what each one is *allowed* to do. A checker reads the plan before anything runs
and rejects it if the permissions are unsafe.

The key principle has a name: **least privilege** — give each part of a system the
*smallest* set of powers it needs, and no more. It's the same reason your house key
doesn't also open the bank vault. Most security disasters happen because something had
more power than it needed and that power got misused.

### Why write a *plan* instead of just configuring things directly?

Because a plan can be **checked by a machine before it runs**. A pile of hand-written
config files can only be checked by a human reading carefully and hoping they didn't miss
anything. Vaked turns "I hope this is safe" into "a checker proved this is safe." That's
the whole pitch.

---

## Part 2 — What "lowering" means

The Vaked plan is written for *humans* to read and reason about. But computers need
specific config files in specific formats to actually run. **Lowering** is the translation
step: it takes the one human-friendly plan and automatically generates all the
machine-specific files from it.

A kitchen analogy: the *recipe* is the plan (human-readable). *Lowering* is the prep cook
turning that one recipe into the actual labeled containers, timers, and station setups the
line needs. One source of truth → many derived outputs, all guaranteed to match the recipe.

Why this is powerful: if the plan and the running system can ever **disagree**, you have a
bug waiting to happen. By generating the config *from* the plan, they can't drift apart —
change the plan, re-run lowering, everything downstream updates together.

---

## Part 3 — What we actually did tonight, step by step

There were three plans (Vaked calls each a "block"):

1. **A web analytics service** — a small website-stats tool, described as a capability
   graph: which database it touches, which secret password it needs, which web address it
   answers on.
2. **An editorial pipeline** — a team of AI agents that research, draft, and fact-check
   articles. The crucial rule: **only one agent is allowed to publish.** Everyone else can
   read and suggest, but cannot push anything live.
3. **A "drive the project forward" loop** — a description of how a team of AI models sweeps
   through a to-do list, skips work already done, does the rest, and writes up the results.
   Again, only *one* member is allowed to actually commit changes.

### Step 1: Check the plans

We ran the checker on all three. All three passed cleanly — meaning the permissions are
internally consistent and nobody is granted a dangerous power they shouldn't have. (For the
editorial team, the checker confirms the "only one publisher" rule actually holds.)

### Step 2: Lower the plans into real files

We ran the lowering step. Each plan produced a folder of generated config files: the system
definitions, the supervision/restart logic, background workers, and a **provenance file**.

> **Provenance** is a receipt. For every generated file, it records a cryptographic
> fingerprint (a "hash") of exactly which part of the plan produced it. If anyone later
> tampers with a generated file, the fingerprint won't match — so you can always prove what
> came from where. This is the same idea as a tamper-evident seal on a medicine bottle.

### Step 3: We found a bug — in the *documentation*, not the system

Each lowering also produces a human-readable summary document. That summary has a section
called "Capability grants" — literally the part that's supposed to list *who is allowed to
do what*, the single most important thing for a security-minded reader.

The bug: that section was **hard-coded to always say "no permissions are declared here"** —
even for the editorial team and the project-loop, which both have detailed permission lists.
So the summary was *blank exactly where it mattered most.*

**Important nuance (this is the teachable part):** the *system itself was never wrong.* The
permissions were correctly enforced by the checker and correctly written into the
machine-config files. Only the **human-facing summary** under-reported. It's the difference
between a bank with correct vault locks but a misprinted lobby sign claiming "no vault here."
The money was always safe — but a person reading the sign would be misled. Both kinds of
correctness matter: the machine has to be right, *and* what the human reads has to be honest.

### Step 4: We fixed it and proved the fix

We changed the summary generator to actually read the permission lists and print them as a
table. We re-ran everything. Now the editorial summary clearly shows:

| Worker | Job | What it's allowed to do |
|---|---|---|
| editor | editor-in-chief | read+write files, internet, **publish**, manage memory |
| researcher | research | **read-only** files, local network, recall memory |
| drafter | drafting | **read-only** files, add to memory |
| factChecker | fact-check | **read-only** files, local network, recall memory |
| publisher | publish | read+write files, **publish**, recall memory |

You can now *see at a glance* that only `editor` and `publisher` can publish, and the three
read-only roles genuinely cannot. The blank-where-it-matters problem is gone. We confirmed
the analytics plan (which has no team) still correctly says "no permissions declared" — so
we didn't break the other case.

### Step 5: We checked our own work (and admitted limits)

Before calling it done, two independent reviewers re-verified every factual claim in our
write-up against the actual files, specifically hunting for exaggeration. Result: every
claim held up; one was flagged as slightly overstated (a quoted table had been reformatted
for readability) and we corrected the wording. We also openly noted what we did **not** do:
we verified the fix by running it and reading the output, but did not add an automated test
to lock the fix in permanently. That's the honest next step.

---

## Part 4 — The three things worth taking away (for anyone)

1. **Least privilege is a habit, not a feature.** Whether it's app permissions on your
   phone, who has the keys at work, or AI agents in a pipeline — give each part the minimum
   it needs. Most breaches are an over-powered component misbehaving.

2. **Two kinds of "correct" exist, and both matter.** A system can *behave* correctly while
   its *documentation lies* about it. Tonight's bug was purely the second kind. Don't trust
   a summary just because the machine works — check that what humans read actually reflects
   reality.

3. **Make claims you can prove, and write down what you didn't prove.** The strongest part
   of tonight's work wasn't the fix — it was checking the fix, having others re-check it,
   and stating plainly "we didn't add a test yet." Honest limits are more trustworthy than
   confident claims.

---

## Part 5 — Reproduce it yourself (technical appendix)

Everything below runs on a normal machine with Python 3 and the `vaked-base` repository. No
build, no compiler, no internet — `vakedc` is a pure Python tool.

```bash
# From the repo root:
cd vaked-base

# 1. Check the three plans — all should report "no diagnostics", exit 0.
python3 -m vakedc check vaked/examples/crabcc-umami.vaked
python3 -m vakedc check vaked/examples/editorial-pipeline.vaked
python3 -m vakedc check vaked/examples/session-drive-loop.vaked

# 2. Lower each plan into its own output folder.
python3 -m vakedc lower vaked/examples/crabcc-umami.vaked      --out .vaked/lower/crabcc-umami
python3 -m vakedc lower vaked/examples/editorial-pipeline.vaked --out .vaked/lower/editorial-pipeline
python3 -m vakedc lower vaked/examples/session-drive-loop.vaked --out .vaked/lower/session-drive-loop

# 3. See the result of the fix — the editorial team's permission table:
sed -n '/## Capability grants/,/daemon-channel/p' .vaked/lower/editorial-pipeline/gen/RUNTIME.md

# 4. Confirm the no-team plan still shows the fallback:
grep "No \`mesh\`" .vaked/lower/crabcc-umami/gen/RUNTIME.md
```

**What the fix changed:** four small edits in `vakedc/lower.py`, all in the documentation
generator (`emit_docs_runtime`) — none in the checker or the machine-config generators:

1. Added a `meshes` field to the `_RuntimeView` data structure.
2. Populated it from the plan's team declarations.
3. Rewrote the "Capability grants" section to print a real per-team table when teams exist,
   and keep the old "no teams" message otherwise.
4. Added provenance receipts for the team sections.

**Full details:** the technical report is alongside this file at
`docs/reports/2026-06-16-dogfood-lower-mesh-fix.md`.

---

*Scope note: this was a local, exploratory session. Nothing was published, committed, or
sent off the machine. The source plans were already saved in the repository; the generated
folders are local build output.*
