#!/usr/bin/env python3
"""Rule-level simulator for preset buddy packs (schema_version 1 and 2).

Pure-stdlib host-behaviour simulation of the shared game script:
game.start, touch events (tap / long_press / swipe / directional swipes /
rapid_tap / shake), transition conditions, var.set / var.increment,
avatar actions (ignored), audio.play existence checks, game.end outcomes,
pressure erosion/relief, combo timing, and the global timeout (v1) /
fallback timeout (v2).

This proves the semantics of the shared rule scripts only; it does NOT
exercise any C runtime.
"""

import json
import os
import sys

TAP = "touch.tap"
LONG_PRESS = "touch.long_press"
SWIPE = "touch.swipe"
SWIPE_LEFT = "touch.swipe_left"
SWIPE_RIGHT = "touch.swipe_right"
SWIPE_UP = "touch.swipe_up"
SWIPE_DOWN = "touch.swipe_down"
RAPID_TAP = "touch.rapid_tap"
SHAKE = "imu.shake"
TIMER_ELAPSED = "timer.elapsed"

DIRECTIONAL_SWIPES = {SWIPE_LEFT, SWIPE_RIGHT, SWIPE_UP, SWIPE_DOWN}
TOUCH_EVENTS = {TAP, LONG_PRESS, SWIPE, RAPID_TAP} | DIRECTIONAL_SWIPES
ALL_EVENTS = TOUCH_EVENTS | {SHAKE, TIMER_ELAPSED}

OPS_EQ = {
    "eq": lambda l, r: l == r,
    "neq": lambda l, r: l != r,
    "gt": lambda l, r: l > r,
    "gte": lambda l, r: l >= r,
    "lt": lambda l, r: l < r,
    "lte": lambda l, r: l <= r,
}

COMBO_WINDOW_MS = 400


class SimulationError(Exception):
    pass


class BuddyGame:
    """Simulates one run of a preset game. Re-instantiate to restart."""

    def __init__(self, preset):
        self.preset = preset
        game = preset.get("game", {})
        self.nodes = {n["id"]: n for n in game.get("nodes", [])}
        self.initial_node = game["initial_node"]
        self.schema_version = preset.get("schema_version", 1)
        self.duration_sec = game.get("duration_sec", 0)
        self.variables_def = game.get("variables", [])
        self.resources = {
            r["resource_id"] for r in preset.get("resources", [])
        }
        if self.schema_version >= 2:
            self.pressure_cfg = game.get("pressure")
            if self.pressure_cfg is None:
                raise SimulationError("schema_version 2 requires game.pressure")
        else:
            self.pressure_cfg = None
        self.reset()

    def reset(self):
        """Restart: reset variables, initial node, countdown, pressure and outcome."""
        self.vars = {v["name"]: v["initial"] for v in self.variables_def}
        self.node_id = self.initial_node
        self.elapsed = 0.0
        self.elapsed_sec = 0
        self.ended = False
        self.outcome = None
        self.pressure = self.pressure_cfg["initial"] if self.pressure_cfg else 0
        self.combo_peak = 0
        self.combo_count = 0
        self.last_tap_ms = 0
        self.mistakes = 0
        self.relieves = 0
        self._run_on_enter(self.node_id)

    # ---- helpers -------------------------------------------------------
    def _node(self):
        return self.nodes[self.node_id]

    def _eval_value(self, spec):
        if isinstance(spec, dict) and "var" in spec:
            return self.vars[spec["var"]]
        return spec

    def _eval_left(self, left):
        if isinstance(left, dict) and left.get("remaining_sec") is True:
            return self.remaining_sec()
        if isinstance(left, dict) and left.get("pressure") is True:
            return self.pressure
        return self._eval_value(left)

    def remaining_sec(self):
        if self.duration_sec <= 0:
            return 0
        return max(0, self.duration_sec - int(self.elapsed))

    def _check_condition(self, cond):
        if cond is None:
            return True
        op = cond["op"]
        if op not in OPS_EQ:
            raise SimulationError("unknown condition op: %r" % op)
        return OPS_EQ[op](self._eval_left(cond["left"]),
                          self._eval_value(cond["right"]))

    def _run_actions(self, actions):
        for action in actions or []:
            op = action["op"]
            if op == "var.set":
                self.vars[action["name"]] = action["value"]
            elif op == "var.increment":
                self.vars[action["name"]] = self.vars[action["name"]] + \
                    action["value"]
            elif op in ("avatar.expression", "avatar.motion"):
                pass  # avatar actions are intentionally ignored
            elif op == "audio.play":
                if action["resource_id"] not in self.resources:
                    raise SimulationError(
                        "missing audio resource: %r" % action["resource_id"])
            elif op == "game.end":
                self.ended = True
                self.outcome = action["outcome"]
            elif op == "pressure.adjust":
                self.pressure += action["value"]
                if action["value"] > 0:
                    self.mistakes += 1
                elif action["value"] < 0:
                    self.relieves += 1
            else:
                raise SimulationError("unknown action op: %r" % op)

    def _run_on_enter(self, node_id):
        self._run_actions(self.nodes[node_id].get("on_enter", []))

    def _check_pressure(self):
        if self.schema_version < 2 or self.ended:
            return
        if self.pressure >= self.pressure_cfg["max"]:
            self._enter_outcome_node("carried_away")
        elif self.pressure <= self.pressure_cfg["min"]:
            self._enter_outcome_node("escaped")

    def _enter_outcome_node(self, outcome):
        for node_id, node in self.nodes.items():
            if any(a.get("op") == "game.end" and a.get("outcome") == outcome
                   for a in node.get("on_enter", [])):
                self.node_id = node_id
                break
        self.ended = True
        self.outcome = outcome

    def _try_match(self, event):
        for tr in self._node().get("transitions", []):
            if tr["event"] != event:
                continue
            if not self._check_condition(tr.get("condition")):
                continue
            self._run_actions(tr.get("actions", []))
            self.node_id = tr["to"]
            self._run_on_enter(self.node_id)
            return True
        return False

    # ---- public API ----------------------------------------------------
    def dispatch(self, event, now_ms=0):
        """Feed one event; returns (node_id, outcome_or_None).
        now_ms is required for rapid_tap timing."""
        if self.ended:
            raise SimulationError("game already ended (%s)" % self.outcome)
        if event not in ALL_EVENTS:
            raise SimulationError("unknown event: %r" % event)

        if event == TIMER_ELAPSED:
            self.elapsed += 1
            self.elapsed_sec = int(self.elapsed)
            if self.schema_version >= 2:
                self.pressure += self.pressure_cfg["rise_per_sec"]
            self._check_pressure()
            if not self.ended and self.duration_sec > 0 and self.elapsed >= self.duration_sec:
                self._enter_outcome_node("carried_away")
            return self.node_id, self.outcome

        # combo tracking for taps
        if event == TAP and now_ms > 0:
            if self.last_tap_ms == 0 or (now_ms - self.last_tap_ms) > COMBO_WINDOW_MS:
                self.combo_count = 1
            else:
                self.combo_count += 1
            self.last_tap_ms = now_ms
            if self.combo_count > self.combo_peak:
                self.combo_peak = self.combo_count

        handled = self._try_match(event)
        if handled:
            self._check_pressure()

        if event == TAP and now_ms > 0 and self.combo_count >= 2 and not self.ended:
            if self._try_match(RAPID_TAP):
                self._check_pressure()
                handled = True

        if not handled and event in DIRECTIONAL_SWIPES and not self.ended:
            if self._try_match(SWIPE):
                self._check_pressure()
                handled = True

        return self.node_id, self.outcome

    def timeout(self):
        """Run until the global duration ceiling expires (v1 or v2 with duration_sec).
        For v2 packs without duration_sec this only advances one tick; use advance()
        to run a specific number of seconds."""
        if self.duration_sec <= 0:
            return self.dispatch(TIMER_ELAPSED)
        while not self.ended and self.elapsed < self.duration_sec:
            self.dispatch(TIMER_ELAPSED)
        return self.node_id, self.outcome

    def advance(self, seconds):
        for _ in range(int(seconds)):
            if self.ended:
                break
            self.dispatch(TIMER_ELAPSED)
        return self.node_id, self.outcome


# ---- per-preset verification scripts -------------------------------------

def run_script(game, steps, expect_outcome, via_timeout=False):
    """steps: list of (event, now_ms?) tuples or plain event strings.
    Returns (ok, detail)."""
    for item in steps:
        if isinstance(item, tuple):
            game.dispatch(*item)
        else:
            game.dispatch(item)
    if via_timeout:
        game.timeout()
    if game.outcome != expect_outcome:
        return False, "expected outcome %r, got %r (node=%r, vars=%r, pressure=%r)" % (
            expect_outcome, game.outcome, game.node_id, game.vars, game.pressure)
    return True, "node=%r vars=%r pressure=%r" % (game.node_id, game.vars, game.pressure)


def check_last_one(preset):
    results = []
    ok, detail = run_script(BuddyGame(preset),
                            [LONG_PRESS, LONG_PRESS, LONG_PRESS], "escaped")
    results.append(("3x long_press -> escaped", ok, detail))
    ok, detail = run_script(BuddyGame(preset), [], "carried_away",
                            via_timeout=True)
    results.append(("timeout -> carried_away", ok, detail))
    return results


def check_do_now(preset):
    results = []
    ok, detail = run_script(BuddyGame(preset), [SWIPE, SWIPE, SWIPE],
                            "escaped")
    results.append(("3x swipe -> escaped", ok, detail))
    ok, detail = run_script(BuddyGame(preset),
                            [SWIPE, TAP, SWIPE, SWIPE, SWIPE], "escaped")
    results.append(("tap resets; 3 fresh swipes -> escaped", ok, detail))
    ok, detail = run_script(BuddyGame(preset), [], "carried_away",
                            via_timeout=True)
    results.append(("timeout -> carried_away", ok, detail))
    return results


def check_decide_now(preset):
    results = []
    ok, detail = run_script(BuddyGame(preset), [SWIPE, SWIPE], "escaped")
    results.append(("2x swipe -> escaped", ok, detail))
    ok, detail = run_script(BuddyGame(preset),
                            [TAP, TAP, SWIPE, TAP, SWIPE, SWIPE], "escaped")
    results.append(("tap toggles nodes; 2 locks -> escaped", ok, detail))
    ok, detail = run_script(BuddyGame(preset), [], "carried_away",
                            via_timeout=True)
    results.append(("timeout -> carried_away", ok, detail))
    return results


CHECKERS = {
    "last-one.json": check_last_one,
    "do-now.json": check_do_now,
    "decide-now.json": check_decide_now,
}


def load_presets(presets_dir):
    presets = {}
    for name in sorted(os.listdir(presets_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(presets_dir, name), "r", encoding="utf-8") as f:
            presets[name] = json.load(f)
    return presets


def main(argv):
    presets_dir = argv[1] if len(argv) > 1 else "shared/presets"
    presets = load_presets(presets_dir)
    if not presets:
        print("no preset JSON files found in %s" % presets_dir)
        return 2

    failures = 0
    for name, preset in presets.items():
        checker = CHECKERS.get(name)
        print("== %s (%s) ==" % (name, preset.get("buddy_id", "?")))
        if checker is None:
            print("  SKIP: no verification script")
            continue
        # audio resource existence is enforced during simulation
        for label, ok, detail in checker(preset):
            print("  %s %s  [%s]" % ("PASS" if ok else "FAIL", label, detail))
            if not ok:
                failures += 1

    # dual-outcome summary
    print("-- dual outcome coverage --")
    for name, preset in presets.items():
        checker = CHECKERS.get(name)
        if checker is None:
            continue
        outs = []
        for label, ok, detail in checker(preset):
            if not ok:
                outs = None
                break
            if "escaped" in label:
                outs.append("escaped")
            if "carried_away" in label:
                outs.append("carried_away")
        both = outs is not None and "escaped" in outs and "carried_away" in outs
        print("  %s %s" % ("PASS" if both else "FAIL", name))
        if not both:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
