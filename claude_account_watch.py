#!/usr/bin/env python3
"""herdr plugin: flag Claude Code panes that are logged out or out of usage.

herdr classifies an agent pane as idle / working / blocked / done / unknown by
matching its screen. A Claude Code pane that has hit a usage limit, or whose
login has expired, shows a banner and then sits at an idle prompt -- so herdr
reports plain `idle`, identical to finished work, and the pane looks abandoned.

This plugin reads the visible screen of every Claude pane, recognises the
two banner families, and surfaces them WITHOUT taking lifecycle authority
(a `pane.report_agent` from a plugin would make herdr skip its own screen
detection for that pane). It uses display-only metadata instead:

  * pane token      `account`        -> "!! logged out" / "!! usage limit"
  * pane token      `account_detail` -> the matched banner line (<= 80 chars)
  * pane state label `idle`          -> the same alert text, so the sidebar
                                        row reads "!! usage limit" not "idle"
  * workspace token `claude_alert`   -> "2 panes: usage limit" rollup
  * one herdr notification per pane per incident

Everything carries a TTL, so a crashed watcher leaves no stale alerts.

Entrypoints (see herdr-plugin.toml):
  start   -- startup hook: spawn the background sweeper and exit
  stop    -- kill the sweeper
  status  -- print sweeper pid + current incidents
  sweep   -- one pass over every watched pane (also what the sweeper loops)
  event   -- event hook: re-check the pane named in HERDR_PLUGIN_EVENT_JSON
  check   -- `check <pane_id>`: classify one pane and print the verdict
  daemon  -- internal: the loop `start` spawns
  log     -- pane entrypoint: follow the watcher log

Only the Python standard library is used.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_SOURCE = "plugin:claude-account-watch"
TOKEN_ALERT = "account"
TOKEN_DETAIL = "account_detail"
WORKSPACE_TOKEN = "claude_alert"

# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

# Every pattern is anchored to the SHAPE of a Claude Code error line, not just
# its words: `⚠ <warning>` for live banners and `⎿  <error>` for a failed turn.
# Assistant prose (`⏺ …`) and tool output that merely *mention* these phrases
# (a transcript about limits, a `cat` of this file) must not match -- a
# plugin that cries wolf gets disabled.
#
# Verified against Claude Code 2.1.287 strings; see tests/test_classify.py.

USAGE_LIMIT_PATTERNS = [
    # ⚠ Usage limit reached · continuing automatically at 8am · esc or type to cancel
    # ⚠ Usage limit reached again after you continued · continuing automatically at 8am
    re.compile(r"^⚠\s*Usage limit reached\b.*\b(continuing automatically|esc or type)", re.I),
    # ⚠ /usage-credits to continue now
    re.compile(r"^⚠\s*/usage-credits to continue", re.I),
    # ⎿  You've hit your weekly limit · resets 8am (America/New_York)
    re.compile(r"^⎿\s*You.{0,3}ve hit your (weekly |session |5-hour |monthly )?limit\b.*\bresets\b", re.I),
    # ⎿  Credit balance is too low. Run /usage-credits to continue …
    re.compile(r"^⎿\s*Credit balance (is )?too low", re.I),
    # ⎿  API Error: 429 … rate_limit_error … (hard refusal, not the soft wait banner)
    re.compile(r"^⎿\s*API Error: 429\b.*\b(usage|rate_limit|limit)", re.I),
    # ⎿  You've reached your Fable limit. Run /usage-credits to continue or switch
    #    models with /model.                      (live capture, Claude Code 2.1.280, 2026-10-05)
    re.compile(r"^⎿\s*You.{0,3}ve reached your .{0,40}\blimit\b", re.I),
    re.compile(r"^⎿\s*.*\bRun /usage-credits to continue", re.I),
]

LOGGED_OUT_PATTERNS = [
    # ⎿  API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"OAuth token has expired. Please run /login."}}
    re.compile(r"^⎿\s*API Error: 401\b"),
    re.compile(r"^⎿\s*.*\bauthentication_error\b"),
    re.compile(r"^⎿\s*.*\b(Please run /login|run /login to (renew|sign in)|Run /login, then try again)", re.I),
    re.compile(r"^⎿\s*.*\b(OAuth )?token has expired\b", re.I),
    re.compile(r"^⎿\s*.*\bInvalid API key\b", re.I),
    # ⚠ … run /login …   (startup / renewal warnings)
    re.compile(r"^⚠.*(?<!\S)/login\b"),
    # ✻ 401 API key is invalid. · Retrying in 13s · attempt 8/10
    #                                            (live capture, Claude Code 2.1.280, 2026-10-05)
    re.compile(r"^\S?\s*401\b.*\b(API key is invalid|invalid|unauthori[sz]ed|authentication)", re.I),
    # ⏺ Please run /login · API Error: 401 API key is invalid.
    #                      (final state after the retries, live capture 2026-10-05)
    re.compile(r"^⏺\s*Please run /login\b"),
    re.compile(r"^⏺.*\bAPI Error: 401\b"),
    # Claude Code's own prompts, at line start only. Deliberately NOT matched:
    # a third-party statusline's "Not logged in" row -- it re-renders only on
    # the next turn, so it keeps claiming logged-out after a /login (2026-10-05).
    re.compile(r"^(Please run /login|Run /login to sign in)\b", re.I),
]

KIND_LABEL = {
    "usage_limit": "!! usage limit",
    "logged_out": "!! auth failed · /login",
}


def _candidate_lines(screen: str, tail: int) -> list[str]:
    """The last `tail` non-empty lines, each stripped of surrounding space."""
    lines = [ln.rstrip() for ln in screen.splitlines()]
    non_empty = [ln.strip() for ln in lines if ln.strip()]
    return non_empty[-tail:]


def classify(screen: str, tail: int = 30) -> tuple[str, str] | None:
    """Return (kind, matched_line) or None.

    Scans only the bottom of the visible screen: the banners sit directly
    above the prompt box. A login prompt is checked before a usage banner so
    a pane that is both logged out and over limit reports the actionable one.
    """
    lines = _candidate_lines(screen, tail)
    for line in reversed(lines):
        if any(pat.search(line) for pat in LOGGED_OUT_PATTERNS):
            return ("logged_out", line)
    for line in reversed(lines):
        if any(pat.search(line) for pat in USAGE_LIMIT_PATTERNS):
            return ("usage_limit", line)
    return None


# --------------------------------------------------------------------------
# Configuration + state
# --------------------------------------------------------------------------


def _env_dir(var: str, fallback: Path) -> Path:
    raw = os.environ.get(var)
    path = Path(raw) if raw else fallback
    path.mkdir(parents=True, exist_ok=True)
    return path


STATE_DIR = _env_dir("HERDR_PLUGIN_STATE_DIR", Path.home() / ".local" / "state" / "herdr-claude-account-watch")
CONFIG_DIR = _env_dir("HERDR_PLUGIN_CONFIG_DIR", Path.home() / ".config" / "herdr-claude-account-watch")
PID_FILE = STATE_DIR / "sweeper.pid"
LOG_FILE = STATE_DIR / "watch.log"
INCIDENTS_FILE = STATE_DIR / "incidents.json"


def load_config() -> dict:
    """Defaults, overridden by KEY=VALUE lines in <config dir>/.env."""
    cfg = {
        "SWEEP_INTERVAL_SECONDS": 60,
        "SCREEN_LINES": 80,
        "TAIL_LINES": 30,
        "WATCH_AGENTS": "claude",
        "NOTIFY": 1,
        "TTL_FACTOR": 3,
    }
    env_file = CONFIG_DIR / ".env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, _, value = raw.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key in cfg:
                cfg[key] = type(cfg[key])(value) if not isinstance(cfg[key], str) else value
    return cfg


def log(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} {msg}\n"
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line)
    if sys.stdout.isatty():
        sys.stdout.write(line)


def load_incidents() -> dict:
    try:
        return json.loads(INCIDENTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_incidents(data: dict) -> None:
    tmp = INCIDENTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(INCIDENTS_FILE)


# --------------------------------------------------------------------------
# herdr CLI
# --------------------------------------------------------------------------


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def herdr(*args: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        [herdr_bin(), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def herdr_json(*args: str) -> dict:
    proc = herdr(*args)
    if proc.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise RuntimeError(f"herdr {' '.join(args)}: non-JSON output") from exc


def list_watched_agents(cfg: dict) -> list[dict]:
    wanted = {a.strip() for a in cfg["WATCH_AGENTS"].split(",") if a.strip()}
    data = herdr_json("agent", "list")
    agents = data.get("result", {}).get("agents", [])
    watched = [a for a in agents if a.get("agent") in wanted and a.get("pane_id")]
    # Test hook: CAW_FORCE_PANES=w1:p2,w1:p3 watches those panes whatever herdr
    # thinks is running in them (lets a plain shell stand in for Claude).
    forced = {p.strip() for p in os.environ.get("CAW_FORCE_PANES", "").split(",") if p.strip()}
    if forced:
        seen = {a["pane_id"] for a in watched}
        panes = herdr_json("pane", "list").get("result", {}).get("panes", [])
        watched += [p for p in panes if p.get("pane_id") in forced and p["pane_id"] not in seen]
    return watched


def read_screen(pane_id: str, lines: int) -> str:
    proc = herdr("pane", "read", pane_id, "--source", "visible", "--lines", str(lines), "--format", "text")
    if proc.returncode != 0:
        raise RuntimeError(f"pane read {pane_id}: {proc.stderr.strip()}")
    return proc.stdout


# --------------------------------------------------------------------------
# Surfacing
# --------------------------------------------------------------------------


def _ttl_ms(cfg: dict) -> str:
    return str(int(cfg["SWEEP_INTERVAL_SECONDS"]) * int(cfg["TTL_FACTOR"]) * 1000)


def raise_alert(pane: dict, kind: str, line: str, cfg: dict, incidents: dict) -> None:
    pane_id = pane["pane_id"]
    label = KIND_LABEL[kind]
    detail = line[:80]
    herdr(
        "pane", "report-metadata", pane_id,
        "--source", PLUGIN_SOURCE,
        "--token", f"{TOKEN_ALERT}={label}",
        "--token", f"{TOKEN_DETAIL}={detail}",
        "--state-label", f"idle={label}",
        "--state-label", f"done={label}",
        "--ttl-ms", _ttl_ms(cfg),
    )
    prior = incidents.get(pane_id)
    if prior and prior.get("kind") == kind:
        prior["last_seen"] = time.time()
        prior["detail"] = detail
        return
    incidents[pane_id] = {
        "kind": kind,
        "detail": detail,
        "first_seen": time.time(),
        "last_seen": time.time(),
        "workspace_id": pane.get("workspace_id"),
        "name": pane.get("name") or pane.get("terminal_title_stripped") or "",
    }
    title = pane.get("name") or pane.get("terminal_title_stripped") or pane_id
    log(f"ALERT {pane_id} [{title}] {kind}: {detail}")
    if int(cfg["NOTIFY"]):
        herdr(
            "notification", "show", f"Claude {label.lstrip('! ')}: {title}",
            "--body", f"{pane_id} · {detail}",
            "--sound", "request",
        )


def clear_alert(pane_id: str, incidents: dict) -> None:
    herdr(
        "pane", "report-metadata", pane_id,
        "--source", PLUGIN_SOURCE,
        "--clear-token", TOKEN_ALERT,
        "--clear-token", TOKEN_DETAIL,
        "--clear-state-labels",
    )
    gone = incidents.pop(pane_id, None)
    if gone:
        log(f"CLEAR {pane_id} [{gone.get('name', '')}] {gone['kind']} resolved")


ROLLUPS_FILE = STATE_DIR / "rollups.json"


def update_workspace_rollups(incidents: dict, known_workspaces: set[str], cfg: dict) -> None:
    """Set the `claude_alert` workspace token where incidents exist; clear it
    only on workspaces we set it on earlier (tracked in rollups.json)."""
    try:
        previously_set = set(json.loads(ROLLUPS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        previously_set = set()
    by_ws: dict[str, dict[str, int]] = {}
    for inc in incidents.values():
        ws = inc.get("workspace_id")
        if not ws:
            continue
        by_ws.setdefault(ws, {}).setdefault(inc["kind"], 0)
        by_ws[ws][inc["kind"]] += 1
    now_set: set[str] = set()
    for ws, counts in by_ws.items():
        parts = [f"{n} {KIND_LABEL[k].lstrip('! ')}" for k, n in sorted(counts.items())]
        herdr(
            "workspace", "report-metadata", ws,
            "--source", PLUGIN_SOURCE,
            "--token", f"{WORKSPACE_TOKEN}=!! " + ", ".join(parts),
            "--ttl-ms", _ttl_ms(cfg),
        )
        now_set.add(ws)
    for ws in (previously_set - now_set) & (known_workspaces | previously_set):
        herdr("workspace", "report-metadata", ws, "--source", PLUGIN_SOURCE, "--clear-token", WORKSPACE_TOKEN)
    ROLLUPS_FILE.write_text(json.dumps(sorted(now_set)), encoding="utf-8")


# --------------------------------------------------------------------------
# Passes
# --------------------------------------------------------------------------


def check_pane(pane: dict, cfg: dict, incidents: dict) -> tuple[str, str] | None:
    pane_id = pane["pane_id"]
    try:
        screen = read_screen(pane_id, int(cfg["SCREEN_LINES"]))
    except RuntimeError as exc:
        log(f"skip {pane_id}: {exc}")
        return None
    verdict = classify(screen, int(cfg["TAIL_LINES"]))
    # A `⎿` match on a pane herdr sees as `working` is most likely transcript
    # (a tool result that printed a banner-shaped line): the real banners end
    # the turn. Spinner-shaped matches (`✻ 401 … Retrying`) ARE working panes,
    # so they are exempt from this gate.
    if verdict and pane.get("agent_status") == "working" and verdict[1].startswith("⎿"):
        verdict = None
    if verdict:
        raise_alert(pane, verdict[0], verdict[1], cfg, incidents)
    elif pane_id in incidents:
        clear_alert(pane_id, incidents)
    return verdict


def sweep(cfg: dict) -> dict:
    started = time.time()
    incidents = load_incidents()
    agents = list_watched_agents(cfg)
    live_panes = {a["pane_id"] for a in agents}
    # Panes that vanished since the last pass: drop their incidents silently.
    for stale in [p for p in incidents if p not in live_panes]:
        gone = incidents.pop(stale)
        log(f"DROP {stale} [{gone.get('name', '')}] pane gone")
    for pane in agents:
        check_pane(pane, cfg, incidents)
    update_workspace_rollups(incidents, {a["workspace_id"] for a in agents if a.get("workspace_id")}, cfg)
    save_incidents(incidents)
    log(f"sweep: {len(agents)} panes, {len(incidents)} incident(s), {time.time() - started:.1f}s")
    return incidents


def event_hook(cfg: dict) -> None:
    raw = os.environ.get("HERDR_PLUGIN_EVENT_JSON") or "{}"
    try:
        event = json.loads(raw)
    except ValueError:
        event = {}
    pane_id = event.get("pane_id") or (event.get("pane") or {}).get("pane_id") or os.environ.get("HERDR_PANE_ID")
    if not pane_id:
        return
    incidents = load_incidents()
    agents = [a for a in list_watched_agents(cfg) if a["pane_id"] == pane_id]
    if not agents:
        return
    check_pane(agents[0], cfg, incidents)
    update_workspace_rollups(incidents, {agents[0].get("workspace_id")} - {None}, cfg)
    save_incidents(incidents)


# --------------------------------------------------------------------------
# Sweeper lifecycle
# --------------------------------------------------------------------------


def _running_pid() -> int | None:
    """The sweeper's pid, or None. A pid is trusted only if the process is
    alive AND its command line is this script's daemon -- a stale pid file
    must never make `stop` signal an unrelated, recycled pid."""
    try:
        pid = int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    try:
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if "claude_account_watch.py" not in cmd or " daemon" not in cmd:
        return None
    return pid


def start_sweeper() -> None:
    pid = _running_pid()
    if pid:
        print(f"sweeper already running (pid {pid})")
        return
    with LOG_FILE.open("a", encoding="utf-8") as out:
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "daemon"],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            start_new_session=True,
            cwd=str(STATE_DIR),
        )
    PID_FILE.write_text(str(proc.pid))
    log(f"sweeper started pid {proc.pid}")
    print(f"sweeper started (pid {proc.pid}); log: {LOG_FILE}")


def stop_sweeper() -> None:
    pid = _running_pid()
    if not pid:
        print("sweeper not running")
        PID_FILE.unlink(missing_ok=True)
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.2)
    else:
        os.kill(pid, signal.SIGKILL)
        log(f"sweeper pid {pid} ignored SIGTERM for 10s; sent SIGKILL")
    PID_FILE.unlink(missing_ok=True)
    log(f"sweeper stopped pid {pid}")
    print(f"sweeper stopped (pid {pid})")


def daemon(cfg: dict) -> None:
    PID_FILE.write_text(str(os.getpid()))
    stop = {"flag": False}

    def _term(_signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)
    log(f"sweeper loop every {cfg['SWEEP_INTERVAL_SECONDS']}s")
    while not stop["flag"]:
        started = time.time()
        try:
            sweep(load_config())
        except Exception as exc:  # keep the loop alive; herdr may be restarting
            log(f"sweep error: {exc}")
        remaining = int(cfg["SWEEP_INTERVAL_SECONDS"]) - (time.time() - started)
        while remaining > 0 and not stop["flag"]:
            time.sleep(min(1.0, remaining))
            remaining -= 1
    log("sweeper exiting")


def status() -> None:
    pid = _running_pid()
    print(f"sweeper: {'running pid ' + str(pid) if pid else 'NOT running'}")
    print(f"state:   {STATE_DIR}")
    print(f"config:  {CONFIG_DIR / '.env'} ({'present' if (CONFIG_DIR / '.env').is_file() else 'defaults'})")
    incidents = load_incidents()
    if not incidents:
        print("incidents: none")
        return
    print(f"incidents: {len(incidents)}")
    for pane_id, inc in sorted(incidents.items()):
        age = int(time.time() - inc["first_seen"])
        print(f"  {pane_id:<10} {inc['kind']:<12} {age:>6}s  [{inc.get('name', '')}] {inc['detail']}")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    cfg = load_config()
    if cmd == "start":
        start_sweeper()
    elif cmd == "stop":
        stop_sweeper()
    elif cmd == "status":
        status()
    elif cmd == "sweep":
        incidents = sweep(cfg)
        print(f"sweep done: {len(incidents)} incident(s)")
        for pane_id, inc in sorted(incidents.items()):
            print(f"  {pane_id:<10} {inc['kind']:<12} [{inc.get('name', '')}] {inc['detail']}")
    elif cmd == "event":
        event_hook(cfg)
    elif cmd == "check":
        if len(argv) < 3:
            print("usage: check <pane_id>", file=sys.stderr)
            return 2
        screen = read_screen(argv[2], int(cfg["SCREEN_LINES"]))
        verdict = classify(screen, int(cfg["TAIL_LINES"]))
        print(json.dumps({"pane_id": argv[2], "verdict": verdict}))
    elif cmd == "daemon":
        daemon(cfg)
    elif cmd == "log":
        os.execvp("tail", ["tail", "-n", "40", "-F", str(LOG_FILE)])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
