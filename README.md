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
  ⚠ Usage limit reached · limit resets 9:40pm
    Continuing automatically at 9:40pm · esc to cancel · /usage-credits to continue now
⏺ Usage limit reached again · continuing automatically at 9:40pm · esc to cancel
  ⎿  You've hit your session limit · resets 9:40pm (America/New_York)
  ⎿  You're out of usage credits. Run /usage-credits to keep using Fable 5.1 or /model to switch models.
  ⎿  You've reached your Fable limit. Run /usage-credits to continue or switch
     models with /model.
```

```text
✻ 401 API key is invalid. · Retrying in 13s · attempt 8/10
⏺ Please run /login · API Error: 401 API key is invalid.
  ⎿  API Error: 401 {"type":"error","error":{"type":"authentication_error",
       "message":"OAuth token has expired. Please run /login."}}
```

```text
  ⎿  Context limit reached · /compact or /clear to continue · auto-compact is off · /config to turn it on
```

```text
  What do you want to do?

  ❯ 1. Stop and wait for limit to reset
    2. Switch to usage credits
    3. Upgrade your plan

  Enter to confirm · Esc to cancel
```

Live captures from Claude Code 2.1.308 (2026-10-29), 2.1.304 (2026-10-19) and 2.1.280 (2026-10-05). The last block is the usage-limit picker Claude Code opens in place of the prompt box; since 0.3.1 a live picker counts as a usage limit, with or without its banner still on screen. The third family, a session that has filled its context window and is waiting for a human `/compact`, looks finished for exactly the same reason, so since 0.3.0 it is flagged too.

## What it surfaces

| Surface | Value | Where you see it |
|---|---|---|
| pane token `account` | `!! usage limit · resets 9:40pm`, `!! auth failed · /login` or `!! context limit · /compact` | `herdr agent list` / `agent get` → `tokens`; `$account` in Agent sidebar rows |
| pane token `account_detail` | the matched banner line (≤ 80 chars) | same |
| pane state label `idle` / `done` | the alert text | the sidebar status column reads `!! usage limit` instead of `idle` |
| workspace token `claude_alert` | `!! 2 usage limit, 1 context limit · /compact` | `$claude_alert` in Spaces sidebar rows |
| notification | `Claude usage limit: <pane name>` (once per incident) | herdr toast (system or in-app per your `[ui.toast]`) |

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
  --source visible`, and classifies the latest turn above the prompt box plus
  everything below it (the live `⚠` banner sits under the box, above a
  statusline that can run to 30+ rows).
- **One sweeper per herdr server.** herdr can run several servers at once
  (the default one plus named sessions such as `HERDR_SESSION=it`), and each
  runs the startup hook with its own socket. State is keyed per server under
  `servers/<key>/`, so a small session server cannot take the pid file away
  from the main one (that is what happened on 2026-10-19). A sweeper whose
  server socket disappears exits by itself.
- **No per-event hook.** `pane.agent_status_changed` fires on every turn of
  every pane and each run is a fresh `python3`; on a loaded Mac with ~120
  panes that cost more than it was worth. One sweep per minute is enough for
  this alert. The `event` entrypoint remains if you want to opt back in (see
  the comment in `herdr-plugin.toml`).
- **Classifier**: patterns are anchored to the *shape* of Claude Code's
  error lines (`⚠ …`, `⎿  …`, `⏺ Please run /login …`, `✻ 401 …`), never to
  bare phrases, so transcript text that merely *mentions* a banner does not
  match (a statusline row such as `provider: ▸5h 100%` or a teammate's quoted
  failure report is not a banner either). Only the **latest turn** counts:
  lines after the last `❯ <prompt>` echo, or after a `⏺ Usage limit reset`
  line (auto-continue does not echo the prompt it sends). A banner from a
  failed turn that is still on screen after a successful retry therefore
  clears on the next sweep. A logged-out verdict wins over a usage-limit
  verdict because it is the one you have to act on; a context-limit verdict
  comes last.
- **Token pushes** happen only when the text changes or the TTL needs a
  refresh, because every push redraws the sidebar for every attached client.

## Actions and panes

| Action | Does |
|---|---|
| `…claude-account-watch.sweep` | one pass now, prints incidents |
| `…claude-account-watch.status` | this server's sweeper pid, other servers' sweepers, open incidents |
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
| `TAIL_LINES` | `30` | non-empty lines above the prompt box the classifier inspects (everything below the box is always read) |
| `WATCH_AGENTS` | `claude` | comma list of herdr agent labels to watch |
| `NOTIFY` | `1` | `0` disables notifications |
| `TTL_FACTOR` | `3` | token TTL = interval × factor |

State lives in `HERDR_PLUGIN_STATE_DIR`, which herdr sets to `~/.local/state/herdr/plugins/johntrandall.claude-account-watch/`: `watch.log` there, and per herdr server `servers/<key>/incidents.json`, `rollups.json` and `sweeper.pid` (`<key>` is `default` for the main server, the session name for a named one). Run outside herdr, the script falls back to the same paths. Other tools may read `servers/<key>/incidents.json` as the current incident list: a JSON object keyed by pane id, each value holding `kind` (`usage_limit`, `logged_out` or `context_limit`), `detail` (the matched line), `first_seen` and `last_seen` (Unix seconds), `workspace_id` and `name`. It is replaced atomically on every sweep. `CAW_FORCE_PANES=w1:p2` is a test hook that watches those panes whatever herdr thinks is running in them.

## Limitations

- Detection is screen-based. A statusline taller than the scanned tail, or a
  banner that scrolls off the visible screen, is missed. Raise `TAIL_LINES`
  if your prompt area is tall.
- A session that Claude Code resumes automatically ("continuing
  automatically at 8am") clears on the next sweep after it resumes; the
  plugin does not resume anything itself.
- A pane whose Claude process has exited but whose screen still looks like
  Claude is still listed by herdr as a Claude agent; its alert clears
  because the latest turn is clean, not because the agent left.
- A picker you open yourself with `/rate-limit-options` reads as a usage limit until you close it.
- Only Claude Code's banner and picker wording as of 2.1.280–2.1.308 is recognised. Add
  patterns in `USAGE_LIMIT_PATTERNS` / `LOGGED_OUT_PATTERNS` and a fixture
  in `tests/` when Anthropic changes the text.

## Tests

```sh
python3 -m unittest discover tests
```

## License

MIT — see [LICENSE](LICENSE).
