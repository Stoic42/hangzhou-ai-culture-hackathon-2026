"""规则包v1校验器测试。

运行（仓库根目录）：
    py -3.12 -m unittest discover -s shared/tests -v
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


class PresetsValidTest(unittest.TestCase):
    def test_all_presets_pass(self):
        for path in vb.iter_manifest_files(PRESETS_DIR):
            with self.subTest(preset=path.name):
                errors = vb.validate_manifest(json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual(errors, [])

    def test_preset_files_exist(self):
        names = {p.name for p in vb.iter_manifest_files(PRESETS_DIR)}
        self.assertEqual(names, {"last-one.json", "do-now.json", "decide-now.json"})


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
        self.check(lambda d: d.update(schema_version=2), "schema_version")

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


if __name__ == "__main__":
    unittest.main()
