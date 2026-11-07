"""规则包v1/v2校验器测试。

运行（仓库根目录）：
    python -m unittest discover -s shared/tests -v
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "tools"))

import validate_buddies as vb  # noqa: E402

PRESETS_DIR = REPO_ROOT / "shared" / "presets"


def load(name: str) -> dict:
    return json.loads((PRESETS_DIR / name).read_text(encoding="utf-8"))


def make_v2_minimal() -> dict:
    """返回一个可通过校验的最小v2规则包（swipe_duel模板简化版）。"""
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
            "pressure": {"initial": 50, "rise_per_sec": 3, "min": 0, "max": 100},
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
                            "event": "touch.tap",
                            "to": "start",
                            "condition": {"left": {"pressure": True}, "op": "lte", "right": 10},
                            "actions": [{"op": "game.end", "outcome": "escaped"}],
                        },
                    ],
                },
                {
                    "id": "carried_node",
                    "title": "被带跑",
                    "instruction": "失败",
                    "on_enter": [{"op": "game.end", "outcome": "carried_away"}],
                },
            ],
        },
        "resources": [],
    }


class PresetsValidTest(unittest.TestCase):
    def test_all_presets_pass(self):
        for path in vb.iter_manifest_files(PRESETS_DIR):
            with self.subTest(preset=path.name):
                errors = vb.validate_manifest(json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual(errors, [])

    def test_preset_files_exist(self):
        names = {p.name for p in vb.iter_manifest_files(PRESETS_DIR)}
        self.assertEqual(names, {"last-one.json", "do-now.json", "decide-now.json"})


class V2ValidTest(unittest.TestCase):
    def test_minimal_v2_passes(self):
        errors = vb.validate_manifest(make_v2_minimal())
        self.assertEqual(errors, [])

    def test_v2_duration_optional(self):
        data = make_v2_minimal()
        # minimal fixture already omits duration_sec
        errors = vb.validate_manifest(data)
        self.assertEqual(errors, [])

    def test_v2_duration_180_ok(self):
        data = make_v2_minimal()
        data["game"]["duration_sec"] = 180
        errors = vb.validate_manifest(data)
        self.assertEqual(errors, [])


class NegativeCasesTest(unittest.TestCase):
    def setUp(self):
        self.base = load("last-one.json")

    def check(self, mutate, fragment: str):
        data = copy.deepcopy(self.base)
        mutate(data)
        errors = vb.validate_manifest(data)
        self.assertTrue(errors, f"应报错: {fragment}")
        self.assertTrue(any(fragment in e for e in errors),
                        f"错误中应包含{fragment!r}，实际: {errors}")

    def test_bad_schema_version(self):
        self.check(lambda d: d.update(schema_version=3), "schema_version")

    def test_bad_duration_too_short(self):
        self.check(lambda d: d["game"].update(duration_sec=59), "duration_sec")

    def test_bad_duration_too_long(self):
        self.check(lambda d: d["game"].update(duration_sec=91), "duration_sec")

    def test_unknown_event(self):
        self.check(lambda d: d["game"]["nodes"][0]["transitions"][0].update(
            event="touch.pinch"), "白名单")

    def test_unknown_action_op(self):
        self.check(lambda d: d["game"]["nodes"][0]["transitions"][0].update(
            actions=[{"op": "avatar.fly", "value": "up"}]), "白名单")

    def test_unknown_expression_enum(self):
        self.check(lambda d: d["game"]["nodes"][0]["on_enter"][0].update(
            value="winking"), "封闭枚举")

    def test_unknown_avatar_face(self):
        self.check(lambda d: d["avatar"].update(face="oval"), "封闭枚举")

    def test_palette_too_small(self):
        self.check(lambda d: d["avatar"].update(palette=["#112233"]), "palette")

    def test_missing_transition_target(self):
        self.check(lambda d: d["game"]["nodes"][0]["transitions"][0].update(
            to="nowhere"), "不存在")

    def test_missing_initial_node(self):
        self.check(lambda d: d["game"].update(initial_node="ghost"), "initial_node")

    def test_undeclared_variable_in_condition(self):
        self.check(lambda d: d["game"]["nodes"][2]["transitions"][0]["condition"].update(
            left={"var": "ghost"}), "未声明变量")

    def test_bad_condition_op(self):
        self.check(lambda d: d["game"]["nodes"][2]["transitions"][0]["condition"].update(
            op="contains"), "白名单")

    def test_missing_carried_away_ending(self):
        def mutate(d):
            for n in d["game"]["nodes"]:
                n["transitions"] = [t for t in n["transitions"]
                                    if not any(a.get("op") == "game.end"
                                               for a in t.get("actions", []))]
                n["on_enter"] = [a for a in n.get("on_enter", [])
                                 if a.get("op") != "game.end"]
        self.check(mutate, "carried_away")

    def test_missing_escaped_ending(self):
        self.check(lambda d: d["game"]["nodes"][2]["transitions"][0]["actions"][0].update(
            outcome="carried_away"), "escaped")

    def test_escaped_unreachable(self):
        def mutate(d):
            d["game"]["nodes"][0]["transitions"] = [
                t for t in d["game"]["nodes"][0]["transitions"] if t["to"] != "refused"]
            d["game"]["nodes"][1]["transitions"] = []
        self.check(mutate, "不可达")

    def test_bad_resource_url(self):
        def mutate(d):
            d["resources"] = [{
                "resource_id": "voice", "kind": "audio", "url": "ftp://x/a.wav",
                "sha256": "0" * 64, "size": 1
            }]
        self.check(mutate, "builtin://")

    def test_bad_resource_sha256(self):
        def mutate(d):
            d["resources"] = [{
                "resource_id": "voice", "kind": "audio",
                "url": "builtin://voice",
                "sha256": "not-hex", "size": 1
            }]
        self.check(mutate, "sha256")

    def test_audio_resource_must_be_declared(self):
        self.check(lambda d: d["game"]["nodes"][0]["on_enter"].append(
            {"op": "audio.play", "resource_id": "missing"}), "未声明资源")

    def test_bad_content_hash(self):
        self.check(lambda d: d.update(content_hash="abc"), "content_hash")

    def test_missing_content_field(self):
        self.check(lambda d: d["content"].pop("personality"), "personality")


class V2NegativeCasesTest(unittest.TestCase):
    def setUp(self):
        self.base = make_v2_minimal()

    def check(self, mutate, fragment: str):
        data = copy.deepcopy(self.base)
        mutate(data)
        errors = vb.validate_manifest(data)
        self.assertTrue(errors, f"应报错: {fragment}")
        self.assertTrue(any(fragment in e for e in errors),
                        f"错误中应包含{fragment!r}，实际: {errors}")

    def test_v1_cannot_use_v2_event(self):
        def mutate(d):
            d["schema_version"] = 1
            d["game"]["nodes"][0]["transitions"][0]["event"] = "touch.swipe_left"
        self.check(mutate, "v1")

    def test_v1_cannot_use_pressure_adjust(self):
        def mutate(d):
            d["schema_version"] = 1
            d["game"]["nodes"][0]["transitions"][0]["actions"] = [
                {"op": "pressure.adjust", "value": 10}]
        self.check(mutate, "pressure.adjust")

    def test_v1_cannot_use_pressure_condition(self):
        def mutate(d):
            d["schema_version"] = 1
            d["game"]["nodes"][0]["transitions"][2]["condition"] = {
                "left": {"pressure": True}, "op": "lte", "right": 10}
        self.check(mutate, "schema_version 2")

    def test_missing_pressure(self):
        def mutate(d):
            del d["game"]["pressure"]
        self.check(mutate, "pressure")

    def test_missing_quips(self):
        def mutate(d):
            del d["game"]["quips"]
        self.check(mutate, "quips")

    def test_pressure_min_equals_initial(self):
        def mutate(d):
            d["game"]["pressure"]["min"] = 50
        self.check(mutate, "0<=min")

    def test_pressure_initial_equals_max(self):
        def mutate(d):
            d["game"]["pressure"]["initial"] = 100
        self.check(mutate, "initial<max")

    def test_pressure_out_of_bounds(self):
        def mutate(d):
            d["game"]["pressure"]["max"] = 1001
        self.check(mutate, "1000")

    def test_pressure_rise_zero(self):
        def mutate(d):
            d["game"]["pressure"]["rise_per_sec"] = 0
        self.check(mutate, "rise_per_sec")

    def test_pressure_rise_too_large(self):
        def mutate(d):
            d["game"]["pressure"]["rise_per_sec"] = 1001
        self.check(mutate, "rise_per_sec")

    def test_pressure_adjust_value_too_large(self):
        def mutate(d):
            d["game"]["nodes"][0]["transitions"][0]["actions"].append(
                {"op": "pressure.adjust", "value": 1001})
        self.check(mutate, "绝对值")

    def test_pressure_adjust_negative_value_too_large(self):
        def mutate(d):
            d["game"]["nodes"][0]["transitions"][0]["actions"].append(
                {"op": "pressure.adjust", "value": -1001})
        self.check(mutate, "绝对值")

    def test_condition_left_strict_one_key(self):
        def mutate(d):
            d["game"]["nodes"][0]["transitions"][2]["condition"]["left"] = {
                "var": "pushes", "remaining_sec": False}
        self.check(mutate, "condition.left")

    def test_condition_left_false_remaining_sec(self):
        def mutate(d):
            d["game"]["nodes"][0]["transitions"][2]["condition"]["left"] = {
                "remaining_sec": False}
        self.check(mutate, "condition.left")

    def test_quips_empty_side(self):
        def mutate(d):
            d["game"]["quips"]["escaped"] = []
        self.check(mutate, "非空")

    def test_quips_too_long(self):
        def mutate(d):
            d["game"]["quips"]["escaped"] = ["啊" * 41]
        self.check(mutate, "1—40")

    def test_quips_missing_side(self):
        def mutate(d):
            del d["game"]["quips"]["carried_away"]
        self.check(mutate, "carried_away")

    def test_v2_duration_too_short(self):
        def mutate(d):
            d["game"]["duration_sec"] = 59
        self.check(mutate, "duration_sec")

    def test_v2_duration_too_long(self):
        def mutate(d):
            d["game"]["duration_sec"] = 181
        self.check(mutate, "duration_sec")


if __name__ == "__main__":
    unittest.main()
