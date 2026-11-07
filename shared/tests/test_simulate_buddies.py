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
    TAP, LONG_PRESS, SWIPE, SHAKE,
    SWIPE_LEFT, SWIPE_RIGHT, SWIPE_UP, SWIPE_DOWN, RAPID_TAP,
)

PRESETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "presets")


def make_v2_minimal() -> dict:
    """Return a minimal v2 pack for simulator tests."""
    return {
        "schema_version": 2,
        "buddy_id": "bdy_test_v2",
        "content_hash": "0" * 64,
        "content": {
            "name": "测试妖怪",
            "personality": "测试性格",
            "gameplay_summary": "测试玩法",
            "theme_tags": ["测试"],
        },
        "avatar": {
            "face": "round",
            "eyes": "sleepy",
            "mouth": "small",
            "palette": ["#18243A", "#FFD166"],
            "motion_style": "drowsy",
        },
        "game": {
            "initial_node": "start",
            "variables": [{"name": "pushes", "type": "int", "initial": 0}],
            "pressure": {"initial": 50, "rise_per_sec": 5, "min": 0, "max": 100},
            "quips": {
                "escaped": ["你赢了"],
                "carried_away": ["你输了"],
            },
            "nodes": [
                {
                    "id": "start",
                    "title": "开始",
                    "instruction": "向左滑",
                    "transitions": [
                        {
                            "event": "touch.swipe_left",
                            "to": "start",
                            "actions": [
                                {"op": "var.increment", "name": "pushes", "value": 1},
                                {"op": "pressure.adjust", "value": -20},
                            ],
                        },
                        {
                            "event": "touch.swipe",
                            "to": "start",
                            "actions": [
                                {"op": "pressure.adjust", "value": 10},
                            ],
                        },
                        {
                            "event": "touch.rapid_tap",
                            "to": "start",
                            "actions": [
                                {"op": "pressure.adjust", "value": -15},
                            ],
                        },
                        {
                            "event": "imu.shake",
                            "to": "start",
                            "actions": [
                                {"op": "pressure.adjust", "value": -10},
                            ],
                        },
                    ],
                },
                {
                    "id": "escaped_node",
                    "title": "破解成功",
                    "instruction": "赢了",
                    "on_enter": [{"op": "game.end", "outcome": "escaped"}],
                },
                {
                    "id": "carried_node",
                    "title": "被带跑",
                    "instruction": "输了",
                    "on_enter": [{"op": "game.end", "outcome": "carried_away"}],
                },
            ],
        },
        "resources": [],
    }


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

    # ---- new v2 presets -----------------------------------------------
    def test_swipe_duel_three_correct_swipes_escape(self):
        g = self._game("swipe-duel.json")
        g.dispatch(SWIPE_LEFT)
        g.dispatch(SWIPE_RIGHT)
        g.dispatch(SWIPE_LEFT)
        self.assertEqual(g.outcome, "escaped")

    def test_swipe_duel_wrong_direction_loses(self):
        g = self._game("swipe-duel.json")
        g.dispatch(SWIPE_RIGHT)
        g.dispatch(SWIPE_RIGHT)
        g.advance(60)
        self.assertEqual(g.outcome, "carried_away")

    def test_rhythm_tap_rapid_taps_escape(self):
        g = self._game("rhythm-tap.json")
        for ms in range(100, 1000, 100):
            g.dispatch(TAP, now_ms=ms)
        self.assertEqual(g.outcome, "escaped")

    def test_rhythm_tap_slow_taps_lose(self):
        g = self._game("rhythm-tap.json")
        for ms in (100, 600, 1100, 1600):
            g.dispatch(TAP, now_ms=ms)
        g.advance(120)
        self.assertEqual(g.outcome, "carried_away")

    def test_shake_off_five_shakes_escape(self):
        g = self._game("shake-off.json")
        for _ in range(5):
            g.dispatch(SHAKE)
        self.assertEqual(g.outcome, "escaped")

    def test_shake_off_tapping_loses(self):
        g = self._game("shake-off.json")
        for _ in range(3):
            g.dispatch(TAP)
        g.advance(60)
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


class V2SimulateTest(unittest.TestCase):
    def _game(self):
        return BuddyGame(make_v2_minimal())

    def test_pressure_erodes_to_carried_away(self):
        g = self._game()
        g.advance(10)  # 50 + 10*5 = 100 >= max
        self.assertEqual(g.outcome, "carried_away")

    def test_pressure_relief_to_escaped(self):
        g = self._game()
        # 50 - 3*20 = -10 <= min
        for _ in range(3):
            g.dispatch(SWIPE_LEFT)
        self.assertEqual(g.outcome, "escaped")

    def test_pressure_adjust_counts_mistakes_and_relieves(self):
        g = self._game()
        g.dispatch(SWIPE)  # +10, mistake
        g.dispatch(SWIPE_LEFT)  # -20, relieve
        g.dispatch(SWIPE)  # +10, mistake
        self.assertEqual(g.mistakes, 2)
        self.assertEqual(g.relieves, 1)

    def test_directional_swipe_falls_back_to_generic(self):
        g = self._game()
        g.dispatch(SWIPE_RIGHT)
        self.assertEqual(g.pressure, 60)

    def test_directional_swipe_matches_before_fallback(self):
        g = self._game()
        g.dispatch(SWIPE_LEFT)
        self.assertEqual(g.vars["pushes"], 1)
        self.assertEqual(g.pressure, 30)

    def test_shake_event(self):
        g = self._game()
        g.dispatch(SHAKE)
        self.assertEqual(g.pressure, 40)

    def test_rapid_tap_fires_within_window(self):
        g = self._game()
        g.dispatch(TAP, now_ms=100)
        self.assertEqual(g.combo_count, 1)
        g.dispatch(TAP, now_ms=200)
        self.assertEqual(g.combo_count, 2)
        self.assertEqual(g.combo_peak, 2)
        # rapid_tap action relieves 15
        self.assertEqual(g.pressure, 35)

    def test_rapid_tap_resets_after_long_gap(self):
        g = self._game()
        g.dispatch(TAP, now_ms=100)
        g.dispatch(TAP, now_ms=600)
        self.assertEqual(g.combo_count, 1)
        self.assertEqual(g.combo_peak, 1)
        self.assertEqual(g.pressure, 50)

    def test_rapid_tap_matches_in_new_node(self):
        preset = make_v2_minimal()
        preset["game"]["nodes"].insert(1, {
            "id": "neutral",
            "title": "中立",
            "instruction": "等待连击",
            "transitions": [{
                "event": "touch.rapid_tap",
                "to": "carried_node",
                "actions": [{"op": "game.end", "outcome": "carried_away"}],
            }],
        })
        # tap moves to neutral, rapid_tap on neutral ends carried_away
        preset["game"]["nodes"][0]["transitions"].append({
            "event": "touch.tap",
            "to": "neutral",
            "actions": [],
        })
        g = BuddyGame(preset)
        g.dispatch(TAP, now_ms=100)
        self.assertEqual(g.node_id, "neutral")
        g.dispatch(TAP, now_ms=200)
        self.assertEqual(g.outcome, "carried_away")

    def test_v2_no_duration_no_timeout(self):
        preset = make_v2_minimal()
        # minimal fixture already has no duration_sec
        g = BuddyGame(preset)
        # pressure would end it long before 1000s; just verify no timeout error
        g.advance(1)
        self.assertIsNone(g.outcome)

    def test_v2_duration_ceiling(self):
        preset = make_v2_minimal()
        preset["game"]["duration_sec"] = 60
        preset["game"]["pressure"] = {"initial": 10, "rise_per_sec": 1, "min": 0, "max": 100}
        g = BuddyGame(preset)
        g.advance(60)
        self.assertEqual(g.outcome, "carried_away")


if __name__ == "__main__":
    unittest.main()
