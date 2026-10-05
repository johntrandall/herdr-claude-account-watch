# herdr Claude Account Watch

A [herdr](https://herdr.dev) plugin that flags Claude Code panes which are
**logged out** or have **hit a usage limit**.

herdr classifies each agent pane from its screen as `idle`, `working`,
`blocked`, `done` or `unknown`. A Claude Code pane that has run out of plan
usage, or whose login has expired, prints a banner and then sits at an idle
prompt. herdr reports it as plain `idle`, which is indistinguishable from
finished work, so a fleet of parked agents looks like a fleet of completed
ones. This plugin reads the visible screen of every Claude pane, recognises
the two banner families, and makes them visible in the sidebar, in
`herdr agent list`, and as a desktop notification.

```text
⚠ Usage limit reached · continuing automatically at 8am · esc or type to cancel
⚠ /usage-credits to continue now
  ⎿  You've hit your weekly limit · resets 8am (America/New_York)
```

```text
  ⎿  API Error: 401 {"type":"error","error":{"type":"authentication_error",
       "message":"OAuth token has expired. Please run /login."}}
```

## What it surfaces

| Surface | Value | Where you see it |
|---|---|---|
| pane token `account` | `!! usage limit` or `!! logged out` | `herdr agent list` / `agent get` → `tokens`; `$account` in Agent sidebar rows |
| pane token `account_detail` | the matched banner line (≤ 80 chars) | same |
| pane state label `idle` / `done` | the alert text | the sidebar status column reads `!! usage limit` instead of `idle` |
| workspace token `claude_alert` | `!! 2 usage limit, 1 logged out` | `$claude_alert` in Spaces sidebar rows |
| notification | `Claude usage limit: <pane name>` | herdr toast (system or in-app per your `[ui.toast]`) |

Everything is **display-only metadata** (`pane.report_metadata`), never
`pane.report_agent`. Taking lifecycle authority would make herdr skip its own
screen detection for that pane, and you would lose `working` / `idle`
tracking. All tokens carry a TTL of three sweep intervals, so a dead watcher
leaves no stale alerts behind. Alerts clear on the next sweep after the
banner disappears.

## Install

```sh
herdr plugin install johntrandall/herdr-claude-account-watch
herdr plugin action invoke johntrandall.claude-account-watch.start
```

Requires `python3` (3.9+, standard library only) and herdr ≥ 0.9.0.

The sweeper is normally started by the plugin's startup hook when herdr
restores a session. herdr does not run startup hooks on `plugin install`,
`link` or `enable`, so start it once by hand as above.

Show the tokens in your sidebar (`~/.config/herdr/config.toml`):

```toml
[ui.sidebar.spaces]
rows = [["state_icon", "workspace"], ["$claude_alert"]]
```

then `herdr server reload-config`.

## How it works

- **Sweeper** (`start` / `stop` / `status` actions, or the startup hook):
  a detached `python3` loop that, every 60 s, runs `herdr agent list`,
  reads the visible screen of each Claude pane with `herdr pane read
  --source visible`, and classifies the bottom 30 non-empty lines.
- **Event hook** on `pane.agent_status_changed`: re-checks just the pane
  that changed, so a login error that interrupts a working turn is flagged
  within a second. The usage-limit banner does not change herdr's state
  (the pane stays `idle`), which is why the sweep exists too.
- **Classifier**: a banner line must start with one of Claude Code's banner
  glyphs (`⚠ ⎿ ✗ ✘ ⏺ ●`) or begin with the banner text itself. Transcript
  text that merely *mentions* "Usage limit reached" does not match. A
  logged-out verdict wins over a usage-limit verdict because it is the one
  you have to act on.

## Actions and panes

| Action | Does |
|---|---|
| `…claude-account-watch.sweep` | one pass now, prints incidents |
| `…claude-account-watch.status` | sweeper pid + open incidents |
| `…claude-account-watch.start` / `.stop` | sweeper lifecycle |
| pane `log` (popup) | follows the watcher log |

Command line, from the plugin directory:

```sh
python3 claude_account_watch.py check w1:p3     # classify one pane, print JSON
python3 claude_account_watch.py sweep
python3 claude_account_watch.py status
```

## Configuration

Optional `KEY=VALUE` lines in `$(herdr plugin config-dir johntrandall.claude-account-watch)/.env`:

| Key | Default | Meaning |
|---|---|---|
| `SWEEP_INTERVAL_SECONDS` | `60` | sweeper period |
| `SCREEN_LINES` | `80` | lines read from each pane's visible screen |
| `TAIL_LINES` | `30` | bottom non-empty lines the classifier inspects |
| `WATCH_AGENTS` | `claude` | comma list of herdr agent labels to watch |
| `NOTIFY` | `1` | `0` disables notifications |
| `TTL_FACTOR` | `3` | token TTL = interval × factor |

State lives in `HERDR_PLUGIN_STATE_DIR` (`watch.log`, `incidents.json`,
`sweeper.pid`). `CAW_FORCE_PANES=w1:p2` is a test hook that watches those
panes whatever herdr thinks is running in them.

## Limitations

- Detection is screen-based. A statusline taller than the scanned tail, or a
  banner that scrolls off the visible screen, is missed. Raise `TAIL_LINES`
  if your prompt area is tall.
- A session that Claude Code resumes automatically ("continuing
  automatically at 8am") clears on the next sweep after it resumes; the
  plugin does not resume anything itself.
- Only Claude Code's banner wording as of 2.1.287 is recognised. Add
  patterns in `USAGE_LIMIT_PATTERNS` / `LOGGED_OUT_PATTERNS` and a fixture
  in `tests/` when Anthropic changes the text.

## Tests

```sh
python3 -m unittest discover tests
```

## License

MIT — see [LICENSE](LICENSE).
