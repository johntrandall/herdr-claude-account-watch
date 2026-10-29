"""Unit tests for the banner classifier. Run: python3 -m unittest discover tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_account_watch import classify, label_for  # noqa: E402

PROMPT_BOX = """
╭──────────────────────────────────────────────────────────────╮
│ >                                                            │
╰──────────────────────────────────────────────────────────────╯
  ⏵⏵ auto mode on · 1 shell · ← for agents
"""

WEEKLY_LIMIT = """
⏺ Running the migration now.

⚠ Usage limit reached · continuing automatically at 8am · esc or type to cancel
⚠ /usage-credits to continue now
  ⎿  You've hit your weekly limit · resets 8am (America/New_York)
""" + PROMPT_BOX

LIMIT_AGAIN = """
⚠ Usage limit reached again after you continued · continuing automatically at 8am
""" + PROMPT_BOX

CREDITS = """
⏺ Fetching…
  ⎿  Credit balance is too low. Run /usage-credits to continue or switch models with /model.
""" + PROMPT_BOX

LOGGED_OUT_API = """
⏺ Reading the file.
  ⎿  API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"OAuth token has expired. Please run /login."}}
""" + PROMPT_BOX

LOGGED_OUT_BANNER = """
⚠ Your session has expired · run /login to renew
""" + PROMPT_BOX

CLEAN_WORKING = """
⏺ I'll check what herdr plugins exist and whether any detect limits.

✻ Galloping… (12s · ↓ 1.2k tokens · esc to interrupt)
""" + PROMPT_BOX

# A transcript that merely TALKS about the banners (this very project's
# session) must not trip the watcher: no banner glyph at line start.
CLEAN_MENTIONS = """
⏺ The sweep greps each pane tail for "Usage limit reached" and for
  "Please run /login"; neither string appears in herdr's own detection
  manifest, so a parked pane reads as idle.

  The weekly-limit-recovery skill says: hit your weekly limit · resets 8am
""" + PROMPT_BOX

# Assistant prose that talks about logouts (the live false positive that
# shipped the glyph-anchored patterns, 2026-10-05).
ASSISTANT_PROSE = """
⏺ I swept 140 live herdr panes plus recent session transcripts for any logout/auth
  banner — "Please run /login", "authentication_error", "API Error: 401" — and
  found none. Usage limit reached never appears either.
""" + PROMPT_BOX

# A third-party statusline that reports login state (stale until the next
# turn re-renders it). Not Claude's banner: must NOT match.
STATUSLINE_LOGIN_ROW = """
⏺ Done.
  identity: host: devbox | account: default
                                     Not logged in · Run /login
  runtime:  Fable 5.1 | 885k/1.0m (88%)
""" + PROMPT_BOX

# Live captures from a real Claude Code 2.1.280 pane, 2026-10-05 (not the
# wording the older docs quoted).
REAL_MODEL_LIMIT = """
❯ Reply with the single word ok.
  ⎿  You've reached your Fable limit. Run /usage-credits to continue or switch
     models with /model.
✻ Churned for 1s · done 4:30 PM
""" + PROMPT_BOX

REAL_INVALID_KEY_RETRYING = """
❯ Reply with the single word ok.
✻ 401 API key is invalid. · Retrying in 13s · attempt 8/10
""" + PROMPT_BOX

REAL_INVALID_KEY_FINAL = """
❯ Reply with the single word ok.
⏺ Please run /login · API Error: 401 API key is invalid.
✻ Sautéed for 3m 7s · done 4:32 PM
""" + PROMPT_BOX

# Recovery: the failed turn's banner is still on screen, but a later prompt
# succeeded. Only the latest turn counts, so this must be clean.
RECOVERED_AFTER_BANNER = """
❯ Reply with the single word ok.
  ⎿  You've reached your Fable limit. Run /usage-credits to continue or switch
     models with /model.
✻ Cogitated for 1s · done 4:40 PM
❯ Reply with the single word ok.
⏺ ok
✻ Pondered for 2s · done 4:43 PM
""" + PROMPT_BOX

# Scrollback far above the prompt is out of the tail window.
OLD_BANNER_SCROLLED_AWAY = "⚠ Usage limit reached · continuing automatically at 8am · esc or type to cancel\n" + (
    "⏺ step\n  ⎿  ok\n" * 30
) + PROMPT_BOX

# Live captures from Claude Code 2.1.304, 2026-10-19 (5-hour window hit on
# account claude2 across a dozen panes; none of the 0.2.0 patterns matched the
# new ⚠ shape, whose countdown moved to a second line under the prompt box).
V2_1_304_BANNER_UNDER_BOX = """
⏺ Revising the plan for round 1's eight findings plus ho2's answers.
  Made 1 scratchpad edit +181 (ctrl+o to expand)
  ⎿  You've hit your session limit · resets 9:40pm (America/New_York)
⏺ Usage limit reached · continuing automatically at 9:40pm · esc to cancel
───────────────────────────────────────────────── applications-rules-split ─
❯
──────────────────────────────────────────────────────────────────────────────
  ⚠ Usage limit reached · limit resets 9:40pm
    Continuing automatically at 9:40pm · esc to cancel · /usage-credits to continue now
  goal: You are applications-rules-split, a rules lead in the application-funnel system…
"""

# Only the live banner under the box, the transcript above is ordinary work
# (the pane was mid-turn when the window closed; herdr still says `working`).
V2_1_304_BANNER_ONLY = """
⏺ Migrate written; now the stage-move rules (drags, reopen, skipped steps, "I sent it").
⏺ Searching for 1 pattern… (ctrl+o to expand)
✢ Harmonizing… (3m 8s · ↓ 16.3k tokens)
──────────────────────────────────────────────── applications-rules-packet ─
❯
──────────────────────────────────────────────────────────────────────────────
  ⚠ Usage limit reached · limit resets 9:40pm
    Continuing automatically at 9:40pm · esc to cancel · /usage-credits to continue now
  goal: You are applications-rules-packet, a rules lead…
"""

V2_1_304_REACHED_AGAIN = """
⏺ Usage limit reached · continuing automatically at 9:40pm · esc to cancel
✻ Sautéed for 32m 19s · done 8:48 PM
❯ Of course every action should be logged and every run should have a run record.
⏺ Usage limit reached again · continuing automatically at 9:40pm · esc to cancel
  ⎿  You've hit your session limit · resets 9:40pm (America/New_York)
     Use your limit reset to reset it now: clau.de/reset
✻ Baked for 0s · done 8:50 PM
""" + PROMPT_BOX

V2_1_304_OUT_OF_CREDITS = """
❯ continue
  ⎿  You're out of usage credits. Run /usage-credits to keep using Fable 5.1 or /model to switch models.
""" + PROMPT_BOX

# After the window reset the pane resumes by itself and prints a reset line;
# the auto-continue prompt is NOT echoed as `❯ …`, so the reset line is the
# only thing separating the old banner from the new turn.
V2_1_304_RESET_RESUMED = """
⏺ Usage limit reached · continuing automatically at 8:01pm · esc to cancel
  ⎿  You've hit your session limit · resets 8:01pm (America/New_York)
⏺ Usage limit reset · continuing automatically
⏺ The watch resumed cleanly after the limit pause: the probe is clean and the hourly cron is still armed.
✻ Crunched for 19s · done 8:01 PM
""" + PROMPT_BOX

V2_1_304_CONTEXT_LIMIT = """
› Message from @admin-technical-dc: Tailscale is back up as of 2026-10-15 ~09:30 EDT (ctrl+o to expand)
  ⎿  Context limit reached · /compact or /clear to continue · auto-compact is off · /config to turn it on
✻ Cooked for 0s · done Thursday 9:30 AM
────────────────────────────────────────────────────── devonthink-steward ─
❯
──────────────────────────────────────────────────────────────────────────────
  ⚠ link-bridge not running (sightline README)
"""

# sightline's statusline rows name the limit too; they re-render lazily and
# must not be read as a banner (`provider: ▸5h 100%`, `└ ⚠ stale: rate limited`).
V2_1_304_STATUSLINE_ONLY = """
⏺ Clean tick: no anomalies. Nothing to log.
✻ Brewed for 5s · done 8:24 PM
──────────────────────────────────────────────────────────────────────────────
❯
──────────────────────────────────────────────────────────────────────────────
  provider: ▸5h 100% @9:39pm | 7d all 27% @oct 25, 7:59pm (since oct 18) | 7d fable 42%
  └ ⚠ stale: rate limited — retry in 7m06s as of 8:45pm
  ├▸claude2  5h 99% @9:39pm (57m) | 7d 26% @oct 25, 7:59pm (5d 23h) | fable 42%
"""

# A teammate's failure report quotes the banner inside assistant output.
V2_1_304_SUBAGENT_QUOTE = """
⏺ Agent "Build c2 classify and cards" failed: Agent terminated early due to an API error: You've hit your session limit · resets 9:40pm (America/New_York)
  (rate_limit, HTTP 429, request id req_011CgCZunR41vAWToc78Lx9o, model sent to the API: claude-opus-5-5)
⏺ Picking that up myself.
""" + PROMPT_BOX


# --- Claude Code 2.1.308: the usage-limit picker (2026-10-29) ---------------
# Live capture of the picker, opened in a TEST pane with /rate-limit-options
# (the same component Claude Code opens by itself at a limit). It replaces the
# prompt box: no bare `❯` line, and its own `❯` is a select cursor.
V2_1_308_DIALOG = """
 ▐▛███▛█   Claude Code v2.1.308
▝▜██████▀  Sonnet 5.5 · Claude Max
 ▝▝   ▝▝   ~/admin-technical
❯ /rate-limit-options
────────────────────────────────────────────────────────────────────────────────
  What do you want to do?

  ❯ 1. Stop and wait for limit to reset
    2. Switch to usage credits
    3. Upgrade your plan

  Enter to confirm · Esc to cancel
──────────────────────────────────────────────────────── TEST-rate-limit-dialog ─
"""

# The shape ho16 sat at for 15 hours (its transcript has the banner; the
# architect saw the picker): the failed turn's banner, then the picker. 0.3.0
# read `❯ 1. Stop…` as a prompt echo, cut the banner away, and saw nothing.
V2_1_308_BANNER_THEN_DIALOG = """
❯ Carry on with the practice checks.
⏺ Reading the next card.
  ⎿  You've hit your weekly limit · resets Oct 30 at 4pm (America/New_York)
────────────────────────────────────────────────────────────────────────────────
  What do you want to do?

  ❯ 1. Stop and wait for limit to reset
    2. Switch to usage credits
    3. Upgrade your plan

  Enter to confirm · Esc to cancel
───────────────────────────────────────────────── watchbill-rules-practice-ho16 ─
"""

# The picker alone (banner scrolled away), with the auto-resume option.
V2_1_308_DIALOG_AUTO_RESUME = """
⏺ Reading the next card.
────────────────────────────────────────────────────────────────────────────────
  What do you want to do?

  ❯ 1. Stop and wait for limit to reset
    2. Wait here, then continue automatically at 4pm
    3. Switch to usage credits

  Enter to confirm · Esc to cancel
──────────────────────────────────────────────────────────────────────────────────
"""

# The picker's text quoted in a transcript (a `cat` of this file) above a
# live prompt box is not a live picker.
V2_1_308_DIALOG_QUOTED = """
⏺ Bash(sed -n 1,20p tests/test_classify.py)
  What do you want to do?
  ❯ 1. Stop and wait for limit to reset
    2. Switch to usage credits
⏺ That is the picker the fix keys on.
────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────
"""


class ClassifyTests(unittest.TestCase):
    def test_weekly_limit(self):
        kind, line = classify(WEEKLY_LIMIT)
        self.assertEqual(kind, "usage_limit")
        self.assertIn("limit", line.lower())

    def test_limit_again_after_continue(self):
        self.assertEqual(classify(LIMIT_AGAIN)[0], "usage_limit")

    def test_credit_balance(self):
        self.assertEqual(classify(CREDITS)[0], "usage_limit")

    def test_logged_out_api_error(self):
        kind, line = classify(LOGGED_OUT_API)
        self.assertEqual(kind, "logged_out")
        self.assertIn("/login", line)

    def test_logged_out_banner(self):
        self.assertEqual(classify(LOGGED_OUT_BANNER)[0], "logged_out")

    def test_logged_out_wins_over_limit(self):
        both = LOGGED_OUT_API.replace(PROMPT_BOX, "") + WEEKLY_LIMIT
        self.assertEqual(classify(both)[0], "logged_out")

    def test_clean_working(self):
        self.assertIsNone(classify(CLEAN_WORKING))

    def test_mentions_do_not_trip(self):
        self.assertIsNone(classify(CLEAN_MENTIONS))

    def test_assistant_prose_does_not_trip(self):
        self.assertIsNone(classify(ASSISTANT_PROSE))

    def test_statusline_login_row_ignored(self):
        self.assertIsNone(classify(STATUSLINE_LOGIN_ROW))

    def test_real_model_limit_capture(self):
        self.assertEqual(classify(REAL_MODEL_LIMIT)[0], "usage_limit")

    def test_real_invalid_key_retrying_capture(self):
        self.assertEqual(classify(REAL_INVALID_KEY_RETRYING)[0], "logged_out")

    def test_real_invalid_key_final_capture(self):
        self.assertEqual(classify(REAL_INVALID_KEY_FINAL)[0], "logged_out")

    def test_recovered_after_banner_is_clean(self):
        self.assertIsNone(classify(RECOVERED_AFTER_BANNER))

    def test_old_banner_outside_tail(self):
        self.assertIsNone(classify(OLD_BANNER_SCROLLED_AWAY, tail=30))

    def test_empty(self):
        self.assertIsNone(classify(""))



    # --- Claude Code 2.1.304 shapes (2026-10-19) ---------------------------

    def test_2_1_304_banner_under_box(self):
        kind, line = classify(V2_1_304_BANNER_UNDER_BOX)
        self.assertEqual(kind, "usage_limit")
        self.assertEqual(label_for(kind, line), "!! usage limit · resets 9:40pm")

    def test_2_1_304_banner_only_working_pane(self):
        kind, line = classify(V2_1_304_BANNER_ONLY)
        self.assertEqual(kind, "usage_limit")
        self.assertTrue(line.startswith("⚠"), line)

    def test_2_1_304_reached_again(self):
        self.assertEqual(classify(V2_1_304_REACHED_AGAIN)[0], "usage_limit")

    def test_2_1_304_out_of_credits(self):
        self.assertEqual(classify(V2_1_304_OUT_OF_CREDITS)[0], "usage_limit")

    def test_2_1_304_reset_line_clears(self):
        self.assertIsNone(classify(V2_1_304_RESET_RESUMED))

    def test_2_1_304_context_limit(self):
        kind, line = classify(V2_1_304_CONTEXT_LIMIT)
        self.assertEqual(kind, "context_limit")
        self.assertEqual(label_for(kind, line), "!! context limit · /compact")

    def test_2_1_304_statusline_rows_ignored(self):
        self.assertIsNone(classify(V2_1_304_STATUSLINE_ONLY))

    def test_2_1_304_subagent_quote_ignored(self):
        self.assertIsNone(classify(V2_1_304_SUBAGENT_QUOTE))

    # --- Claude Code 2.1.308 usage-limit picker (2026-10-29) ---------------

    def test_2_1_308_dialog_alone(self):
        kind, line = classify(V2_1_308_DIALOG)
        self.assertEqual(kind, "usage_limit")
        self.assertIn("Stop and wait for limit to reset", line)

    def test_2_1_308_banner_then_dialog(self):
        kind, line = classify(V2_1_308_BANNER_THEN_DIALOG)
        self.assertEqual(kind, "usage_limit")
        self.assertTrue(line.startswith("⎿"), line)
        self.assertEqual(label_for(kind, line), "!! usage limit · resets 4pm")

    def test_2_1_308_dialog_auto_resume_names_time(self):
        kind, line = classify(V2_1_308_DIALOG_AUTO_RESUME)
        self.assertEqual(kind, "usage_limit")
        self.assertEqual(label_for(kind, line), "!! usage limit · resets 4pm")

    def test_2_1_308_quoted_dialog_ignored(self):
        self.assertIsNone(classify(V2_1_308_DIALOG_QUOTED))

    def test_label_without_time(self):
        self.assertEqual(label_for("usage_limit", "⚠ Usage limit reached"), "!! usage limit")


if __name__ == "__main__":
    unittest.main()
