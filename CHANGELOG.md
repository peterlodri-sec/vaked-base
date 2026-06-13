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
