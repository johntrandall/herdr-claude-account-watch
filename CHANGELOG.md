# Changelog

## 0.1.0 — 2026-10-05

- Initial release: detects the Claude Code usage-limit banner family and the
  logged-out / `/login` banner family on the visible screen of every Claude
  pane; surfaces them as display-only pane tokens, an `idle` state label, a
  workspace rollup token, and one herdr notification per incident.
- Background sweeper (startup hook) plus `pane.agent_status_changed` event hook.
