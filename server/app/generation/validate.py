"""规则包发布前校验：复用 shared 校验器 + 设备侧硬约束收紧。

只有通过 validate_for_publish 全量校验的规则包才允许发布，
保证“过服务器校验即可在 T5 真机运行”。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# 直接加载 shared/tools/validate_buddies.py，保证与设备共用同一份白名单语义
_SHARED_VALIDATOR = (
    Path(__file__).resolve().parents[3] / "shared" / "tools" / "validate_buddies.py"
)
_spec = importlib.util.spec_from_file_location("shared_validate_buddies", _SHARED_VALIDATOR)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise RuntimeError(f"无法加载 shared 校验器: {_SHARED_VALIDATOR}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("shared_validate_buddies", _mod)
_spec.loader.exec_module(_mod)

validate_manifest_shared = _mod.validate_manifest

# 设备侧硬上限（device/t5/src/buddy_engine.h），Python 校验器不含这些约束
MAX_NODES = 16
MAX_TRANSITIONS_PER_NODE = 8
MAX_ACTIONS_PER_LIST = 6
MAX_VARIABLES = 4
MAX_RESOURCES = 4
MAX_THEME_TAGS = 4
MAX_PALETTE = 4  # shared 校验器已含 2—4，此处仅明示来源


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_device_limits(data: dict) -> list[str]:
    """镜像 buddy_engine.c 的容量上限与更严格的 condition 约束。"""
    errors: list[str] = []

    content = data.get("content") or {}
    tags = content.get("theme_tags")
    if isinstance(tags, list) and len(tags) > MAX_THEME_TAGS:
        errors.append(f"theme_tags超过设备上限{MAX_THEME_TAGS}个")

    game = data.get("game") or {}
    variables = game.get("variables")
    if isinstance(variables, list) and len(variables) > MAX_VARIABLES:
        errors.append(f"variables超过设备上限{MAX_VARIABLES}个")

    nodes = game.get("nodes")
    if isinstance(nodes, list):
        if len(nodes) > MAX_NODES:
            errors.append(f"nodes超过设备上限{MAX_NODES}个")
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id")
            on_enter = node.get("on_enter")
            if isinstance(on_enter, list) and len(on_enter) > MAX_ACTIONS_PER_LIST:
                errors.append(f"节点{nid!r}的on_enter超过设备上限{MAX_ACTIONS_PER_LIST}个动作")
            transitions = node.get("transitions")
            if isinstance(transitions, list):
                if len(transitions) > MAX_TRANSITIONS_PER_NODE:
                    errors.append(
                        f"节点{nid!r}的transitions超过设备上限{MAX_TRANSITIONS_PER_NODE}条")
                for tr in transitions:
                    if not isinstance(tr, dict):
                        continue
                    actions = tr.get("actions")
                    if isinstance(actions, list) and len(actions) > MAX_ACTIONS_PER_LIST:
                        errors.append(
                            f"节点{nid!r}的迁移actions超过设备上限{MAX_ACTIONS_PER_LIST}个")
                    # 设备端 condition.right 只接受整数常量（比 shared 更严格）
                    cond = tr.get("condition")
                    if isinstance(cond, dict) and "right" in cond:
                        if not _is_int(cond["right"]):
                            errors.append(
                                f"节点{nid!r}的condition.right必须为整数（设备约束）")

    resources = data.get("resources")
    if isinstance(resources, list) and len(resources) > MAX_RESOURCES:
        errors.append(f"resources超过设备上限{MAX_RESOURCES}个")

    return errors


def validate_for_publish(manifest: dict) -> list[str]:
    """发布前完整校验：shared 语义 + 设备收紧。"""
    errors = validate_manifest_shared(manifest)
    if isinstance(manifest, dict):
        errors.extend(validate_device_limits(manifest))
    return errors
