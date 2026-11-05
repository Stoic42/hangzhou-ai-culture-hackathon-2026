"""校验一致性：shared 预设、设备收紧约束与 stub 生成包的发布校验。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from server.app.generation.validate import validate_for_publish
from server.app.library.publish import build_manifest
from server.app.providers.stub import StubGeneration
from server.app.resources import FEEDBACK_RESOURCE

_PRESETS_DIR = Path(__file__).resolve().parents[2] / "shared" / "presets"


def _load_presets() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(_PRESETS_DIR.glob("*.json"))]


def test_presets_pass_publish_validation():
    """三只 shared 预设经服务器发布校验应为空错误列表。

    预设 content_hash 是全零占位（shared 校验器只查格式），
    validate_for_publish 同样不核对 hash，故应通过。
    """
    presets = _load_presets()
    assert len(presets) == 3
    for preset in presets:
        assert validate_for_publish(preset) == [], preset["buddy_id"]


def _base_manifest() -> dict:
    return copy.deepcopy(_load_presets()[0])


def _only_device_limit_errors(manifest: dict) -> list[str]:
    """预设本身无错误，返回的错误应全部来自设备收紧约束。"""
    errors = validate_for_publish(manifest)
    assert errors, "改造后的包应当被拒绝"
    return errors


def test_device_limit_nodes_rejected():
    """17 个节点超过设备上限 16。"""
    m = _base_manifest()
    template = copy.deepcopy(m["game"]["nodes"][0])
    while len(m["game"]["nodes"]) <= 16:
        node = copy.deepcopy(template)
        node["id"] = f"n{len(m['game']['nodes'])}"
        m["game"]["nodes"].append(node)
    errors = _only_device_limit_errors(m)
    assert any("nodes" in e for e in errors)


def test_device_limit_transitions_rejected():
    """单节点 9 条 transitions 超过设备上限 8。"""
    m = _base_manifest()
    node = m["game"]["nodes"][0]
    template = copy.deepcopy(node["transitions"][0])
    while len(node["transitions"]) <= 8:
        node["transitions"].append(copy.deepcopy(template))
    errors = _only_device_limit_errors(m)
    assert any("transitions" in e for e in errors)


def test_device_limit_actions_rejected():
    """动作列表 7 个超过设备上限 6（on_enter 路径）。"""
    m = _base_manifest()
    node = m["game"]["nodes"][0]
    action = copy.deepcopy(node["on_enter"][0])
    while len(node["on_enter"]) <= 6:
        node["on_enter"].append(copy.deepcopy(action))
    errors = _only_device_limit_errors(m)
    assert any("on_enter" in e for e in errors)


def test_device_limit_actions_on_transition_rejected():
    """迁移 actions 列表 7 个同样超过设备上限 6。"""
    m = _base_manifest()
    node = m["game"]["nodes"][0]
    transition = node["transitions"][0]
    action = {"op": "var.increment", "name": "x", "value": 1}
    while len(transition["actions"]) <= 6:
        transition["actions"].append(copy.deepcopy(action))
    errors = _only_device_limit_errors(m)
    assert any("actions" in e for e in errors)


def test_device_limit_variables_rejected():
    """5 个变量超过设备上限 4。"""
    m = _base_manifest()
    var = copy.deepcopy(m["game"]["variables"][0])
    while len(m["game"]["variables"]) <= 4:
        v = copy.deepcopy(var)
        v["name"] = f"v{len(m['game']['variables'])}"
        m["game"]["variables"].append(v)
    errors = _only_device_limit_errors(m)
    assert any("variables" in e for e in errors)


def test_device_limit_resources_rejected():
    """5 个 resources 超过设备上限 4。"""
    m = _base_manifest()
    while len(m["resources"]) <= 4:
        m["resources"].append(copy.deepcopy(dict(FEEDBACK_RESOURCE)))
    errors = _only_device_limit_errors(m)
    assert any("resources" in e for e in errors)


def test_device_limit_theme_tags_rejected():
    """5 个 theme_tags 超过设备上限 4。"""
    m = _base_manifest()
    while len(m["content"]["theme_tags"]) <= 4:
        m["content"]["theme_tags"].append("标签")
    errors = _only_device_limit_errors(m)
    assert any("theme_tags" in e for e in errors)


def test_device_condition_right_must_be_int():
    """condition.right 为字符串违反设备端整数常量约束。"""
    m = _base_manifest()
    for node in m["game"]["nodes"]:
        for tr in node.get("transitions", []):
            if isinstance(tr.get("condition"), dict):
                tr["condition"]["right"] = "3"
                errors = _only_device_limit_errors(m)
                assert any("condition.right" in e for e in errors)
                return
    raise AssertionError("预设中没有 condition，无法构造该用例")


def test_stub_manifests_pass_publish_validation():
    """stub 生成的 manifest（经 build_manifest 构造）必过发布校验：20 个随机种子。"""
    generation = StubGeneration()
    for seed in range(20):
        text = f"stub识别：种子{seed}的坏习惯"
        content = generation.make_candidate_content(text)
        game, avatar = generation.make_game_and_avatar(content)
        manifest = build_manifest(f"bdy_seed_{seed}", content, game, avatar)
        assert validate_for_publish(manifest) == [], seed
