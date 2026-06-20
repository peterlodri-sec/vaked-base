# Vaked Issue E2E Delivery Tips — One Session, 6 PRs, 0 Regrets

**2026-06-20** · Vaked Engineering · 7-minute read

---

Today we shipped 6 PRs end-to-end in a single session: CI optimization, zig-build fix, Cloudflare Pages unblock, radio dev velocity, vakedc indent repair, and a .worktrees/ gitlink cleanup. Here's what worked.

## 1. Work in Dependency Order, Not Issue Order

The PRs formed a natural chain:

```
#355 (zig-build fix) → #358 (.worktrees/ gitlinks) → #357 (CI optimization)
```

Merge #355 first, and the landing-guru/zig-build failures on #357 and #358 disappear — they were inheriting broken state from main. Don't fight cascading failures. Fix the root, and the leaves heal themselves.

## 2. Admin-Merge Through Stale Checks

CI checks run against the branch's merge-base, not main. When you've merged a fix to main but the PR was branched earlier, the checks show stale failures. Don't wait for re-runs. Admin-merge when:

- You verified no conflicts locally (`git merge-base --is-ancestor` + test merge)
- The failing check was fixed in a previously merged PR
- The PR's own changes don't touch the failing area

Three of today's PRs merged via `--admin` because Cloudflare Pages showed stale failures — the fix was in a dependent PR already merged to main.

## 3. One Commit Per PR, Squashed

Every PR was a single commit with a conventional prefix:

```
fix(openrouterd): define SockFprog manually for Zig 0.16
ci: optimize workflows — consolidate, cache, tune crons
feat(radio): inject dev velocity into avatar node layout seed
```

Single-commit PRs are easier to review, revert, and `git bisect`. No "fix typo" follow-ups polluting the log.

## 4. Rebase Before Review, Then Stop

```bash
git fetch origin main
git rebase origin/main
git push --force-with-lease
```

One rebase at the end, right before handing off for review. Not after every merged dependency. Not mid-iteration. One clean rebase, then ship.

## 5. Sign Everything, Always

```bash
git config commit.gpgsign true
git config gpg.format ssh
git config user.signingkey ~/.ssh/id_ed25519.pub
```

Every commit in today's session was ED25519-signed. The pr-review agent flagged one as unsigned — it was wrong. But the discipline matters: signed commits prove authorship independent of GitHub's identity system.

## 6. Worktrees for Isolation, Not Fancy Names

```bash
git worktree add -b fix/issue-NNN-slug .claude/worktrees/issue-NNN main
```

Each PR got its own worktree. No stash juggling. No "wait, which branch am I on?" No `git reset --hard` panic when another session switches branches under you. Simple names, predictable locations, easy cleanup.

## 7. Let CI Tell You What Changed

Don't guess which PR broke what. Read the CI logs. When `zig-build` failed on PR #357 (CI optimization), the error was `linux.seccomp.SockFprog` not found — the Zig 0.16 stdlib had removed it. Five minutes of reading the CI log replaced an hour of guessing.

---

**Bottom line:** The session shipped 6 PRs, closed 3 issues, and left the CI pipeline consuming ~35% fewer cron minutes. No rollbacks. No broken main. No "let me just fix one more thing" scope creep.

The Vaked way: small, signed, dependency-ordered, CI-informed, one rebase, admin-merge through stale checks, worktree per PR, ship.

---

*Genesis: 7c242080 · Session: 2026-06-20*
