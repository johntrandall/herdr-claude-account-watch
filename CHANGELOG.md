# Changelog

## 0.2.0 — 2026-10-05

Tested end to end in a dedicated herdr workspace against a real Claude Code
2.1.280 session with an invalid API key and a real session on an account whose
model limit was at 100%.

- Patterns for the banner shapes Claude actually prints: `⎿  You've reached
  your <model> limit. Run /usage-credits …`, `✻ 401 API key is invalid. ·
  Retrying …`, `⏺ Please run /login · API Error: 401 …`. Bare-phrase matching
  removed after it flagged assistant prose that talked about logouts.
- Only the latest turn (after the last `❯ <prompt>` echo) is classified, so an
  alert clears once a later turn succeeds even while the old banner is still
  on screen. Third-party statusline "Not logged in" rows are ignored (stale
  until the next render).
- Per-event hook removed (one python3 per status change across ~120 panes was
  measurable on a loaded Mac); the sweeper is the only runner.
- Passes are serialized with a file lock; the incidents temp file is
  pid-unique (two concurrent hooks previously raced on `tmp.replace`).
- Pane / workspace tokens are re-pushed only on change or TTL refresh.
- `stop` verifies the pid is this script's daemon and escalates to SIGKILL
  after 10 s.

## 0.1.0 — 2026-10-05

- Initial release: detects the Claude Code usage-limit banner family and the
  logged-out / `/login` banner family on the visible screen of every Claude
  pane; surfaces them as display-only pane tokens, an `idle` state label, a
  workspace rollup token, and one herdr notification per incident.
- Background sweeper (startup hook) plus `pane.agent_status_changed` event hook.
