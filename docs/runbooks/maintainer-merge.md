# Maintainer sign + ack + merge (local, M3 & M1)

**How do I sign before I merge?** GitHub's "Merge" button signs the merge commit with
*GitHub's* web-flow key, not yours. To put **your** signature on it, do the merge
**locally** as a GPG-signed commit (or attest with a signed tag). One alias does all three:
**comment-ack → signed merge → push**.

## Install (one-time, `~/.zshrc` on both Macs)

```bash
# vack <pr#> — maintainer review-ack + GPG-signed merge of a vaked-base PR, from local.
vack() {
  local pr="$1" repo="peterlodri-sec/vaked-base"
  [ -z "$pr" ] && { echo "usage: vack <pr#>"; return 1; }
  export GPG_TTY=$(tty)                                  # so pinentry can prompt
  local br; br=$(gh pr view "$pr" --repo "$repo" --json headRefName -q .headRefName) || return 1
  echo "→ ack + signed-merge #$pr ($br)"
  gh pr comment "$pr" --repo "$repo" \
     --body "✅ Reviewed; GPG-signed merge by maintainer (genesis 7c242080)." || return 1
  git fetch origin --quiet && git checkout main && git pull --ff-only origin main || return 1
  git merge --no-ff --gpg-sign -m "Merge #$pr ($br) — maintainer-signed · genesis 7c242080" \
     "origin/$br" || { echo "merge conflict — resolve, then: git commit -S && git push"; return 1; }
  git push origin main && echo "✓ #$pr signed-merged. Verify: git log --show-signature -1"
}
```

Reload: `source ~/.zshrc`. Use: `vack 318`.

## What it does (and why it's honest)

1. **ack** — posts a maintainer comment on the PR (the human review is on record).
2. **signed merge** — `git merge --no-ff --gpg-sign` makes a merge commit signed with
   *your* key (`23AA373A…`, uid `Peter Lodri (vaked-genesis 7c242080)`). GitHub shows
   **Verified**, and `git log --show-signature` proves it locally.
3. **push** — lands it on `main`.

## Notes / fallbacks

- **Branch protection:** if a direct push to `main` is blocked, either merge via the
  GitHub UI and then attest with a signed tag:
  `git fetch && git tag -s ack-pr<PR>-$(date +%Y%m%d) origin/main -m "signed-merge #<PR>" && git push origin --tags`
  — or temporarily allow the push (owner).
- **Auto-sign everything** (optional): `git config --global commit.gpgsign true` +
  `git config --global user.signingkey 23AA373AEBD74C4F035A728E745B0B0DDB08A55B`.
  (Leave off if you don't want a passphrase prompt on every commit.)
- **Conflict:** the alias stops and tells you to resolve, then `git commit -S && git push`.
- This is the *signed* analogue of `seals-anchor-*` tags: a key the repo can't forge,
  applied at the human's decision point.
