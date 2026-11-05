#!/usr/bin/env python3
"""Rule-level simulator for preset buddy packs (schema_version 1).

Pure-stdlib host-behaviour simulation of the shared game script:
game.start, touch events (tap / long_press / swipe), transition conditions,
var.set / var.increment, avatar actions (ignored), audio.play existence
checks, game.end outcomes, and the global timeout carried_away.

This proves the semantics of the shared rule scripts only; it does NOT
exercise any C runtime.
"""

import json
import os
import sys

TAP = "touch.tap"
LONG_PRESS = "touch.long_press"
SWIPE = "touch.swipe"
TIMER_ELAPSED = "timer.elapsed"

OPS_EQ = {
    "eq": lambda l, r: l == r,
    "neq": lambda l, r: l != r,
    "gt": lambda l, r: l > r,
    "gte": lambda l, r: l >= r,
    "lt": lambda l, r: l < r,
    "lte": lambda l, r: l <= r,
}


class SimulationError(Exception):
    pass


class BuddyGame:
    """Simulates one run of a preset game. Re-instantiate to restart."""

    def __init__(self, preset):
        self.preset = preset
        game = preset.get("game", {})
        self.nodes = {n["id"]: n for n in game.get("nodes", [])}
        self.initial_node = game["initial_node"]
        self.duration_sec = game["duration_sec"]
        self.variables_def = game.get("variables", [])
        self.resources = {
            r["resource_id"] for r in preset.get("resources", [])
        }
        self.reset()

    def reset(self):
        """Restart: reset variables, initial node, countdown and outcome."""
        self.vars = {v["name"]: v["initial"] for v in self.variables_def}
        self.node_id = self.initial_node
        self.elapsed = 0.0
        self.ended = False
        self.outcome = None
        self._run_on_enter(self.node_id)

    # ---- helpers -------------------------------------------------------
    def _node(self):
        return self.nodes[self.node_id]

    def _eval_value(self, spec):
        if isinstance(spec, dict) and "var" in spec:
            return self.vars[spec["var"]]
        return spec

    def _check_condition(self, cond):
        if cond is None:
            return True
        op = cond["op"]
        if op not in OPS_EQ:
            raise SimulationError("unknown condition op: %r" % op)
        return OPS_EQ[op](self._eval_value(cond["left"]),
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
            else:
                raise SimulationError("unknown action op: %r" % op)

    def _run_on_enter(self, node_id):
        self._run_actions(self.nodes[node_id].get("on_enter", []))

    # ---- public API ----------------------------------------------------
    def dispatch(self, event):
        """Feed one touch event; returns (node_id, outcome_or_None)."""
        if self.ended:
            raise SimulationError("game already ended (%s)" % self.outcome)
        if event not in (TAP, LONG_PRESS, SWIPE):
            raise SimulationError("unknown event: %r" % event)
        for tr in self._node().get("transitions", []):
            if tr["event"] != event:
                continue
            if not self._check_condition(tr.get("condition")):
                continue
            self._run_actions(tr.get("actions", []))
            self.node_id = tr["to"]
            self._run_on_enter(self.node_id)
            return self.node_id, self.outcome
        # no matching transition: stay in place
        return self.node_id, self.outcome

    def advance(self, seconds):
        """Advance the global countdown; fires timer.elapsed at duration."""
        if self.ended:
            return self.node_id, self.outcome
        self.elapsed += seconds
        if self.elapsed >= self.duration_sec:
            for node_id, node in self.nodes.items():
                if any(a.get("op") == "game.end" and a.get("outcome") == "carried_away"
                       for a in node.get("on_enter", [])):
                    self.node_id = node_id
                    break
            self.ended = True
            self.outcome = "carried_away"
        return self.node_id, self.outcome

    def timeout(self):
        return self.advance(self.duration_sec)


# ---- per-preset verification scripts -------------------------------------

def run_script(game, steps, expect_outcome, via_timeout=False):
    """steps: list of touch events ('tap'/'long_press'/'swipe').
    Returns (ok, detail)."""
    for ev in steps:
        game.dispatch(ev)
    if via_timeout:
        game.timeout()
    if game.outcome != expect_outcome:
        return False, "expected outcome %r, got %r (node=%r, vars=%r)" % (
            expect_outcome, game.outcome, game.node_id, game.vars)
    return True, "node=%r vars=%r" % (game.node_id, game.vars)


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
