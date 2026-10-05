"""Unit tests for the banner classifier. Run: python3 -m unittest discover tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_account_watch import classify  # noqa: E402

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
  Not logged in · Run /login to sign in with your claude.ai account
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

# Scrollback far above the prompt is out of the tail window.
OLD_BANNER_SCROLLED_AWAY = "⚠ Usage limit reached · continuing automatically at 8am · esc or type to cancel\n" + (
    "⏺ step\n  ⎿  ok\n" * 30
) + PROMPT_BOX


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

    def test_old_banner_outside_tail(self):
        self.assertIsNone(classify(OLD_BANNER_SCROLLED_AWAY, tail=30))

    def test_empty(self):
        self.assertIsNone(classify(""))


if __name__ == "__main__":
    unittest.main()
