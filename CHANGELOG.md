## [unreleased] — 2026-06-13

### agents
- feat(agents): add vaked-provost product-owner / coordination agent (#138)
- refactor(agents): reduce stderr noise + trim gh issue list payload (#150)

### ci
- ci(diagrams): drift-guard CI workflow + fix noisy diff output (#142)
- ci(nix-check): add store cache, drop --all-systems, add path filters (#149)
- chore(ci): run provost hourly + harden against the OTel batch-thread panic (#139)
- ci-agents: operator briefing, commit-signature provenance, versioned/Telegram footer (#135)

### compiler
- refactor(pr-review): split 2.9k-line main.rs into focused modules (#154)
- fix(pr-review): panic=unwind so the OTel batch-thread panic doesn't abort the review (#140)
- pr-review: fix Langfuse tracing, link traces↔PR, tune DeepSeek cache (#133)

### docs
- docs(protocol): SPIRE PQC design — RFC 0007 Q3 research spike (#146)
- docs(yardmaster): don't SPKI-pin behind Cloudflare/CDN (#136)

### language
- feat(language): design note 0018 — crypto/seal capability domain (RFC 0007 Q4) (#144)

### runtime
- feat(runtime): sandboxd Python reference scaffold — process/filesystem membrane (#15 pattern) (#148)
- feat(runtime): memoryd Python reference implementation (#15 pattern) (#147)

### tools
- feat(tools): sealed-image spike — provenance schema + sign/verify (RFC 0007 Q5) (#145)

### chore
- chore: gitignore .claude/worktrees/ (ephemeral agent isolation workspaces) (#143)
- hardening(telebot): unprivileged systemd unit + credential store (#134)
- feat(telebot): interactive Telegram control surface for the agent fleet (#131)
- feat(telebot): deploy paths — host script + bounded GitHub Actions runtime (#137)
- hcp-litany: ratify Decision #2, add Decisions #3 and #4 (#132)

### diagrams
- fix(diagrams): regenerate SVGs with d2 v0.7.1 to fix drift detection
- fix(diagrams): normalize committed SVG before diffing in --check mode

## [unreleased] — 2026-06-13

### agents
- feat(agents): add vaked-provost product-owner / coordination agent (#138)
- feat(telebot): deploy paths — host script + bounded GitHub Actions runtime (#137)
- feat(telebot): interactive Telegram control surface for the agent fleet (#131)
- feat: telegram-post workflow + agent posting protocol (#129)
- ci-agents: operator briefing, commit-signature provenance, versioned/Telegram footer (#135)
- hardening(telebot): unprivileged systemd unit + credential store (#134)
- pr-review: fix Langfuse tracing, link traces↔PR, tune DeepSeek cache (#133)
- hcp-litany: ratify Decision #2, add Decisions #3 and #4 (#132)

### ci
- ci(nix-check): add store cache, drop --all-systems, add path filters (#149)
- chore(ci): run provost hourly + harden against the OTel batch-thread panic (#139)
- fix(ci): fix YAML parse error in label-tagger.yml (#128)

### runtime
- feat(runtime): sandboxd Python reference scaffold — process/filesystem membrane (#15 pattern) (#148)
- feat(runtime): memoryd Python reference implementation (#15 pattern) (#147)

### docs
- docs(protocol): SPIRE PQC design — RFC 0007 Q3 research spike (#146)
- docs(yardmaster): don't SPKI-pin behind Cloudflare/CDN (#136)

### tools
- feat(tools): sealed-image spike — provenance schema + sign/verify (RFC 0007 Q5) (#145)

### chore
- chore: gitignore .claude/worktrees/ (ephemeral agent isolation workspaces) (#143)

### fix
- fix(pr-review): panic=unwind so the OTel batch-thread panic doesn't abort the review (#140)
- fix(yardmaster): mastodon broadcast empty-base default + egress-aware TLS pinning (#127)
- fix(bin/vaked): Codex P2 — verify gate, webhook validation, path traversal (#126)

### compiler
- fix(bin/vaked): Codex P2 — verify gate, webhook validation, path traversal (#126)

## [unreleased] — 2026-06-13

### agents
- feat(agents): add vaked-provost product-owner / coordination agent (#138)
- feat(agents): add vaked-label-tagger CI agent (#125)
- ci-agents: operator briefing, commit-signature provenance, versioned/Telegram footer (#135)

### ci
- ci(nix-check): add store cache, drop --all-systems, add path filters (#149)
- chore(ci): run provost hourly + harden against the OTel batch-thread panic (#139)
- fix(ci): fix YAML parse error in label-tagger.yml (#128)

### chore
- chore: gitignore .claude/worktrees/ (ephemeral agent isolation workspaces) (#143)

### compiler
- fix(bin/vaked): Codex P2 — verify gate, webhook validation, path traversal (#126)
- extend bin/vaked: lifecycle, gateway, webhook, mcp, verify, self-auth, man, docs (#124)

### docs
- docs(yardmaster): don't SPKI-pin behind Cloudflare/CDN (#136)

### fix
- fix(pr-review): panic=unwind so the OTel batch-thread panic doesn't abort the review (#140)
- pr-review: fix Langfuse tracing, link traces↔PR, tune DeepSeek cache (#133)
- fix(yardmaster): mastodon broadcast empty-base default + egress-aware TLS pinning (#127)

### protocol
- hcp-litany: ratify Decision #2, add Decisions #3 and #4 (#132)

### runtime
- hardening(telebot): unprivileged systemd unit + credential store (#134)
- feat(telebot): deploy paths — host script + bounded GitHub Actions runtime (#137)
- feat(telebot): interactive Telegram control surface for the agent fleet (#131)

### tools
- feat(tools): sealed-image spike — provenance schema + sign/verify (RFC 0007 Q5) (#145)

### feat
- feat: telegram-post workflow + agent posting protocol (#129)
- feat(yardmaster): graduate to active + always-on Mastodon/Telegram broadcast (#123)

## [unreleased] — 2026-06-13

### agents
- feat(agents): add vaked-provost product-owner / coordination agent (#138)
- feat(agents): add vaked-label-tagger CI agent (#125)
- feat(yardmaster): graduate to active + always-on Mastodon/Telegram broadcast (#123)
- feat(yardmaster): merge-train conductor for the fan-out agent fleet (#121)
- ci-agents: operator briefing, commit-signature provenance, versioned/Telegram footer (#135)

### ci
- ci(nix-check): add store cache, drop --all-systems, add path filters (#149)
- chore(ci): run provost hourly + harden against the OTel batch-thread panic (#139)
- fix(ci): fix YAML parse error in label-tagger.yml (#128)

### compiler
- fix(bin/vaked): Codex P2 — verify gate, webhook validation, path traversal (#126)
- extend bin/vaked: lifecycle, gateway, webhook, mcp, verify, self-auth, man, docs (#124)

### docs
- docs(yardmaster): don't SPKI-pin behind Cloudflare/CDN (#136)

### protocol
- RFC 0007: post-quantum Litany & sealed image-as-code attestation + d2 render pipeline (#122)
- hcp-litany: ratify Decision #2, add Decisions #3 and #4 (#132)

### runtime
- feat(telebot): deploy paths — host script + bounded GitHub Actions runtime (#137)
- feat(telebot): interactive Telegram control surface for the agent fleet (#131)
- feat: telegram-post workflow + agent posting protocol (#129)
- hardening(telebot): unprivileged systemd unit + credential store (#134)
- fix(yardmaster): mastodon broadcast empty-base default + egress-aware TLS pinning (#127)

### tools
- pr-review: fix Langfuse tracing, link traces↔PR, tune DeepSeek cache (#133)
- fix(pr-review): panic=unwind so the OTel batch-thread panic doesn't abort the review (#140)

## [unreleased] — 2026-06-13

### agents
- feat(agents): add vaked-provost product-owner / coordination agent (#138)
- feat(agents): add vaked-label-tagger CI agent (#125)
- feat(yardmaster): graduate to active + always-on Mastodon/Telegram broadcast (#123)
- feat(yardmaster): merge-train conductor for the fan-out agent fleet (#121)
- hardening(telebot): unprivileged systemd unit + credential store (#134)
- feat(telebot): interactive Telegram control surface for the agent fleet (#131)
- feat: telegram-post workflow + agent posting protocol (#129)
- fix(yardmaster): mastodon broadcast empty-base default + egress-aware TLS pinning (#127)

### ci
- fix(ci): fix YAML parse error in label-tagger.yml (#128)
- ci: add nix-check job (nix flake check) with verbose Telegram report (#111)

### compiler
- feat(vakedz): first Zig front-end — verified parse parity + ralphloop-cache (#120)
- add bin/vaked — agent-optimized compiler CLI entry bin (#119)
- extend bin/vaked: lifecycle, gateway, webhook, mcp, verify, self-auth, man, docs (#124)
- fix(bin/vaked): Codex P2 — verify gate, webhook validation, path traversal (#126)

### docs
- docs(yardmaster): don't SPKI-pin behind Cloudflare/CDN (#136)

### protocol
- RFC 0007: post-quantum Litany & sealed image-as-code attestation + d2 render pipeline (#122)
- hcp-litany: ratify Decision #2, add Decisions #3 and #4 (#132)

### runtime
- Add GitHub-backed send_later fallback for PR self-check-ins (#110)

### tools
- pr-review: fix Langfuse tracing, link traces↔PR, tune DeepSeek cache (#133)

### chore
- Optimization pass on #103: fix 10K-worker parse bug, de-soup (-99k lines), claims ledger (#112)

## new_tag
null

## labels
[]

## comment
null

## milestone
null

# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

<!-- vaked-label-tagger prepends entries here in changelog mode -->
