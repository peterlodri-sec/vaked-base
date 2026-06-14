#!/usr/bin/env bash
# PreCompact hook — fires before context compaction.
# 1. Mines mempalace async (non-blocking).
# 2. Emits a compaction prompt to stdout so Claude Code uses it as compaction context.

set -euo pipefail

# Mine mempalace in background if available
TRANSCRIPT="${CLAUDE_CODE_TRANSCRIPT_PATH:-}"
if command -v mempalace >/dev/null 2>&1 && [ -n "$TRANSCRIPT" ]; then
  nohup mempalace mine "$(dirname "$TRANSCRIPT")" --mode convos --agent claude-code \
    >> "${TMPDIR:-/tmp}/mempalace-compact-$(date +%s).log" 2>&1 &
fi

# Emit compaction instructions — Claude Code includes this in the compact summary
cat <<'COMPACT_PROMPT'
COMPACT INSTRUCTIONS — preserve these elements verbatim in the summary:
1. Current task goal (one sentence) and active branch name.
2. Files modified this session (full paths, one per line).
3. Architectural decisions made (bullet list, max 5).
4. Pending TODOs or next steps (bullet list).
5. Any unresolved errors or failing tests (exact message).
6. Active skill/mode: wenyan-ultra internal communication is ON; artifact gate (English-only Write/Edit/git/PR) is ON.
7. Self-checkin schedule (PR number + next check-in time if set).

Omit: raw file contents, resolved discussions, tool outputs no longer relevant, raw log dumps.
COMPACT_PROMPT

exit 0
