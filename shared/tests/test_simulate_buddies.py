# -*- coding: utf-8 -*-
"""Unit tests for shared/tools/simulate_buddies.py (rule-level semantics)."""

import json
import os
import sys
import unittest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.simulate_buddies import (  # noqa: E402
    BuddyGame, SimulationError, load_presets,
    TAP, LONG_PRESS, SWIPE,
)

PRESETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "presets")


class SimulateBuddiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.presets = load_presets(PRESETS_DIR)

    def _game(self, name):
        return BuddyGame(self.presets[name])

    # ---- success paths -------------------------------------------------
    def test_last_one_three_long_press_escapes(self):
        g = self._game("last-one.json")
        for _ in range(3):
            g.dispatch(LONG_PRESS)
        self.assertEqual(g.outcome, "escaped")

    def test_do_now_three_swipes_escape(self):
        g = self._game("do-now.json")
        for _ in range(3):
            g.dispatch(SWIPE)
        self.assertEqual(g.outcome, "escaped")

    def test_decide_now_two_swipes_escape(self):
        g = self._game("decide-now.json")
        g.dispatch(SWIPE)
        g.dispatch(SWIPE)
        self.assertEqual(g.outcome, "escaped")

    # ---- mechanics -----------------------------------------------------
    def test_do_now_tap_resets_counter(self):
        g = self._game("do-now.json")
        g.dispatch(SWIPE)
        self.assertEqual(g.vars["actions_done"], 1)
        g.dispatch(TAP)
        self.assertEqual(g.vars["actions_done"], 0)
        for _ in range(3):
            g.dispatch(SWIPE)
        self.assertEqual(g.outcome, "escaped")

    def test_decide_now_tap_toggles_nodes(self):
        g = self._game("decide-now.json")
        self.assertEqual(g.node_id, "offer_a")
        g.dispatch(TAP)
        self.assertEqual(g.node_id, "offer_b")
        g.dispatch(TAP)
        self.assertEqual(g.node_id, "offer_a")
        g.dispatch(SWIPE)
        self.assertEqual(g.node_id, "locked")
        g.dispatch(TAP)
        self.assertEqual(g.node_id, "offer_a")
        g.dispatch(SWIPE)
        g.dispatch(SWIPE)
        self.assertEqual(g.outcome, "escaped")

    # ---- dual outcomes / timeout ---------------------------------------
    def test_last_one_timeout_carried_away(self):
        g = self._game("last-one.json")
        g.timeout()
        self.assertEqual(g.outcome, "carried_away")
        self.assertEqual(g.node_id, "carried_node")

    def test_do_now_timeout_carried_away(self):
        g = self._game("do-now.json")
        g.advance(70)
        self.assertEqual(g.outcome, "carried_away")

    def test_decide_now_timeout_carried_away(self):
        g = self._game("decide-now.json")
        g.timeout()
        self.assertEqual(g.outcome, "carried_away")

    # ---- reset ---------------------------------------------------------
    def test_reset_restores_variables_node_countdown_outcome(self):
        g = self._game("do-now.json")
        g.dispatch(SWIPE)
        g.dispatch(SWIPE)
        g.dispatch(TAP)
        g.advance(30)
        self.assertEqual(g.vars["actions_done"], 0)
        self.assertNotEqual(g.outcome, "escaped")
        g.reset()
        self.assertEqual(g.vars["actions_done"], 0)
        self.assertEqual(g.node_id, "nudge")
        self.assertEqual(g.elapsed, 0.0)
        self.assertFalse(g.ended)
        self.assertIsNone(g.outcome)

    def test_reset_after_end_allows_fresh_timeout(self):
        g = self._game("last-one.json")
        g.dispatch(LONG_PRESS)
        g.dispatch(LONG_PRESS)
        g.dispatch(LONG_PRESS)
        self.assertEqual(g.outcome, "escaped")
        g.reset()
        g.timeout()
        self.assertEqual(g.outcome, "carried_away")

    # ---- audio existence -----------------------------------------------
    def test_audio_missing_resource_raises(self):
        preset = json.loads(json.dumps(self.presets["last-one.json"]))
        preset["resources"] = []
        with self.assertRaises(SimulationError):
            BuddyGame(preset)

    def test_dispatch_after_end_raises(self):
        g = self._game("decide-now.json")
        g.dispatch(SWIPE)
        g.dispatch(SWIPE)
        with self.assertRaises(SimulationError):
            g.dispatch(TAP)


if __name__ == "__main__":
    unittest.main()
