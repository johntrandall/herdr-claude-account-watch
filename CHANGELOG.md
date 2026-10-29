# Changelog

## 0.3.1 — 2026-10-29

Built after `watchbill-rules-practice-ho16` stopped at its weekly limit at 19:54 on 10-28 and sat unseen for 15 hours: the watch logged nothing for its pane, while it flagged the same weekly limit on a neighbouring pane an hour later.

- **The usage-limit picker is a usage limit.** Claude Code opens a picker in place of the prompt box (`What do you want to do?` · `❯ 1. Stop and wait for limit to reset` · …). 0.3.0 read the picker's `❯ 1.` select cursor as a prompt echo, cut every line above it (the banner included) out of the latest turn, and classified nothing. Verified by test: the three picker fixtures fail on 0.3.0 and pass on 0.3.1. The cursor is no longer an echo or the input box, and a live picker (no prompt box on screen) is matched on its own options, so it alerts even after its banner has scrolled away. The label takes the time from `Wait here, then continue automatically at 4pm` when the banner is gone.
- **One state folder.** Run outside herdr, the script used to fall back to `~/.local/state/herdr-claude-account-watch/`, which left an empty folder beside the live one that a reader took for proof the watch was dead. It now falls back to herdr's own plugin dirs.
- Tests: 29 (was 25), with a live 2.1.308 capture of the picker, ho16's shape (banner then picker), the auto-resume option, and a quoted picker above a live prompt box as a negative. A dry run over the 232 live Claude panes gave the same verdicts as 0.3.0 for every one.
- Not a bug: the two daemons are one per herdr server (`default` and `it`), as 0.3.0 designed.

## 0.3.0 — 2026-10-19

Built after the 5-hour window closed on a dozen panes at 20:45 and not one tab changed. Three defects, each verified in isolation against the live fleet (146 Claude panes).

- **One sweeper per herdr server.** After a reboot two servers (the default one and the `it` session server) ran the startup hook; the pid file was per plugin, so the one-pane session server owned the only sweeper and the 147-pane server went unwatched for six hours (`sweep: 1 panes` for 380 passes). pid, incidents, rollups and lock now live under `servers/<HERDR_SESSION | default | sock-…>/`; `status` lists the other servers' sweepers; a sweeper exits when its server socket is gone.
- **Claude Code 2.1.304 banner shapes.** `⚠ Usage limit reached · limit resets 9:40pm` (countdown on a second, glyphless line), `⏺ Usage limit reached (again) · continuing automatically at …`, `⎿  You're out of usage credits. Run /usage-credits to keep using …`. `⏺ Usage limit reset · continuing automatically` ends an incident (auto-continue sends its prompt without a `❯` echo).
- **Prompt-box anchoring.** The classifier reads the latest turn above the box plus everything below it, instead of a fixed 30-line tail that a 30-row statusline (sightline) filled entirely, hiding the banner.
- **Context limit is a third kind**: `⎿  Context limit reached · /compact or /clear to continue` → `!! context limit · /compact`. Same shape of failure: the pane looks idle and is stuck until a human acts.
- Usage-limit labels carry the reset time when the banner names one: `!! usage limit · resets 9:40pm`.
- Tests: 25 (was 10), with the 2.1.304 captures as fixtures, statusline rows and a teammate's quoted failure as negatives.

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
