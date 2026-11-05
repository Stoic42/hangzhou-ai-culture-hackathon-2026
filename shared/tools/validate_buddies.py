"""规则包v1静态校验器（主机端，Python 3.12标准库）。

用法（仓库根目录）：
    py -3.12 shared/tools/validate_buddies.py shared/presets

校验目录内所有 *.json；任一错误即该包不可运行，进程退出码非0。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
DURATION_MIN_SEC = 60
DURATION_MAX_SEC = 90

EVENTS = {"game.start", "touch.tap", "touch.long_press", "touch.swipe", "timer.elapsed"}
ACTIONS = {
    "avatar.expression", "avatar.motion", "audio.play",
    "timer.start", "var.set", "var.increment", "game.end",
}
COMPARE_OPS = {"eq", "neq", "gt", "gte", "lt", "lte"}
OUTCOMES = {"escaped", "carried_away"}

AVATAR_FACES = {"round", "square", "bean"}
AVATAR_EYES = {"sleepy", "wide", "side", "dot"}
AVATAR_MOUTHS = {"small", "grin", "flat", "open"}
AVATAR_MOTION_STYLES = {"drowsy", "jittery", "still", "bouncy"}
AVATAR_EXPRESSIONS = {"neutral", "pleading", "happy", "smug", "anxious", "sleepy", "angry"}
AVATAR_MOTIONS = {"still", "breathe", "shake", "bounce", "nod"}

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_manifest(data: object) -> list[str]:
    """校验单个BuddyManifest（已解析JSON），返回错误列表；空列表=合法。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest必须是JSON对象"]

    def err(msg: str) -> None:
        errors.append(msg)

    # schema_version
    if data.get("schema_version") != SCHEMA_VERSION:
        err(f"schema_version必须是{SCHEMA_VERSION}，实际为{data.get('schema_version')!r}")

    buddy_id = data.get("buddy_id")
    if not isinstance(buddy_id, str) or not buddy_id:
        err("buddy_id必须是非空字符串")

    content_hash = data.get("content_hash")
    if not isinstance(content_hash, str) or not _HEX64_RE.match(content_hash):
        err("content_hash必须是64位小写十六进制字符串")

    # content 四字段
    content = data.get("content")
    if not isinstance(content, dict):
        err("content必须是对象")
    else:
        for field in ("name", "personality", "gameplay_summary"):
            if not isinstance(content.get(field), str) or not content[field].strip():
                err(f"content.{field}必须是非空字符串")
        tags = content.get("theme_tags")
        if (not isinstance(tags, list) or not tags
                or not all(isinstance(t, str) and t for t in tags)):
            err("content.theme_tags必须是非空字符串数组")

    # avatar 封闭枚举
    avatar = data.get("avatar")
    if not isinstance(avatar, dict):
        err("avatar必须是对象")
    else:
        _check_enum(avatar, "face", AVATAR_FACES, err)
        _check_enum(avatar, "eyes", AVATAR_EYES, err)
        _check_enum(avatar, "mouth", AVATAR_MOUTHS, err)
        _check_enum(avatar, "motion_style", AVATAR_MOTION_STYLES, err)
        palette = avatar.get("palette")
        if (not isinstance(palette, list) or not 2 <= len(palette) <= 4
                or not all(isinstance(c, str) and _COLOR_RE.match(c) for c in palette)):
            err("avatar.palette必须是2—4个#RRGGBB颜色")

    # game
    game = data.get("game")
    if not isinstance(game, dict):
        err("game必须是对象")
        return errors

    duration = game.get("duration_sec")
    if not _is_int(duration) or not DURATION_MIN_SEC <= duration <= DURATION_MAX_SEC:
        err(f"game.duration_sec必须是{DURATION_MIN_SEC}—{DURATION_MAX_SEC}的整数")

    variables = game.get("variables")
    var_names: set[str] = set()
    if not isinstance(variables, list):
        err("game.variables必须是数组")
    else:
        for i, var in enumerate(variables):
            if not isinstance(var, dict):
                err(f"variables[{i}]必须是对象")
                continue
            name = var.get("name")
            if not isinstance(name, str) or not name:
                err(f"variables[{i}].name必须是非空字符串")
            elif name in var_names:
                err(f"变量{name!r}重复声明")
            else:
                var_names.add(name)
            if var.get("type") != "int":
                err(f"变量{name!r}的type必须是int")
            if not _is_int(var.get("initial")):
                err(f"变量{name!r}的initial必须是整数")

    nodes = game.get("nodes")
    node_ids: list[str] = []
    if not isinstance(nodes, list) or not nodes:
        err("game.nodes必须是非空数组")
        nodes = []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            err(f"nodes[{i}]必须是对象")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            err(f"nodes[{i}].id必须是非空字符串")
        elif node_id in node_ids:
            err(f"节点id {node_id!r}重复")
        else:
            node_ids.append(node_id)
        for field in ("title", "instruction"):
            if not isinstance(node.get(field), str) or not node[field].strip():
                err(f"节点{node_id!r}缺少非空{field}")
        _check_actions(node.get("on_enter", []), var_names,
                       f"节点{node_id!r}的on_enter", err)
        transitions = node.get("transitions", [])
        if not isinstance(transitions, list):
            err(f"节点{node_id!r}的transitions必须是数组")
            continue
        for j, tr in enumerate(transitions):
            where = f"节点{node_id!r}的transitions[{j}]"
            if not isinstance(tr, dict):
                err(f"{where}必须是对象")
                continue
            event = tr.get("event")
            if event not in EVENTS:
                err(f"{where}的事件{event!r}不在白名单{sorted(EVENTS)}内")
            to = tr.get("to")
            if not isinstance(to, str) or not to:
                err(f"{where}缺少目标节点to")
            elif to not in [n for n in node_ids]:
                # 目标存在性在节点收集后统一检查
                pass
            _check_condition(tr.get("condition"), var_names, where, err)
            _check_actions(tr.get("actions", []), var_names, where, err)

    id_set = set(node_ids)
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        for tr in node.get("transitions", []) if isinstance(node.get("transitions", []), list) else []:
            if isinstance(tr, dict) and isinstance(tr.get("to"), str) and tr["to"] not in id_set:
                err(f"节点{node.get('id')!r}的迁移目标{tr['to']!r}不存在")

    initial = game.get("initial_node")
    if not isinstance(initial, str) or initial not in id_set:
        err(f"game.initial_node {initial!r}不存在于节点表中")

    # 双结局与图可达性
    all_actions: list[dict] = []
    for node in nodes if isinstance(nodes, list) else []:
        if isinstance(node, dict):
            if isinstance(node.get("on_enter"), list):
                all_actions.extend(a for a in node["on_enter"] if isinstance(a, dict))
            trs = node.get("transitions")
            if isinstance(trs, list):
                for tr in trs:
                    if isinstance(tr, dict) and isinstance(tr.get("actions"), list):
                        all_actions.extend(a for a in tr["actions"] if isinstance(a, dict))
    outcomes = {a.get("outcome") for a in all_actions if a.get("op") == "game.end"}
    if "escaped" not in outcomes:
        err("缺少game.end escaped（破解成功）结局")
    if "carried_away" not in outcomes:
        err("缺少game.end carried_away（被搭子带跑）结局")

    if initial in id_set and isinstance(nodes, list):
        reachable: set[str] = set()
        stack = [initial]
        edges: dict[str, list[str]] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            tos = []
            trs = node.get("transitions")
            if isinstance(trs, list):
                for tr in trs:
                    if isinstance(tr, dict) and isinstance(tr.get("to"), str):
                        tos.append(tr["to"])
            edges[node.get("id")] = tos
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            stack.extend(edges.get(cur, []))
        escaped_nodes = {n.get("id") for n in nodes
                         if isinstance(n, dict)
                         and any(a.get("op") == "game.end" and a.get("outcome") == "escaped"
                                 for a in (n.get("on_enter") or [])
                                 if isinstance(a, dict))}
        carried_nodes = {n.get("id") for n in nodes
                         if isinstance(n, dict)
                         and any(a.get("op") == "game.end" and a.get("outcome") == "carried_away"
                                 for a in (n.get("on_enter") or [])
                                 if isinstance(a, dict))}
        # 结局动作也可能在迁移actions里：结局节点=含game.end动作的节点或其迁移目标
        end_targets: dict[str, str] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            trs = node.get("transitions")
            if not isinstance(trs, list):
                continue
            for tr in trs:
                if not isinstance(tr, dict):
                    continue
                for a in tr.get("actions") or []:
                    if isinstance(a, dict) and a.get("op") == "game.end" and isinstance(tr.get("to"), str):
                        end_targets[tr["to"]] = a.get("outcome")
        for target, outcome in end_targets.items():
            (escaped_nodes if outcome == "escaped" else carried_nodes).add(target)
        if not (escaped_nodes & reachable):
            err("从initial_node不可达任何escaped结局节点")
        # 全局超时强制carried_away，因此图不可达carried_away时仍视为可达（默认结局）

    # resources
    resources = data.get("resources")
    resource_ids: set[str] = set()
    if not isinstance(resources, list):
        err("resources必须是数组")
    else:
        seen_ids: set[str] = set()
        for i, res in enumerate(resources):
            where = f"resources[{i}]"
            if not isinstance(res, dict):
                err(f"{where}必须是对象")
                continue
            rid = res.get("resource_id")
            if not isinstance(rid, str) or not rid:
                err(f"{where}.resource_id必须是非空字符串")
            elif rid in seen_ids:
                err(f"资源id {rid!r}重复")
            else:
                resource_ids.add(rid)
            if res.get("kind") != "audio":
                err(f"{where}.kind必须是audio")
            url = res.get("url")
            if not isinstance(url, str) or not (
                    url.startswith("builtin://") or url.startswith("https://")):
                err(f"{where}.url只允许builtin://或https://前缀")
            sha = res.get("sha256")
            if not isinstance(sha, str) or not _HEX64_RE.match(sha):
                err(f"{where}.sha256必须是64位小写十六进制字符串")
            if not _is_int(res.get("size")) or res["size"] < 0:
                err(f"{where}.size必须是非负整数")

    for action in all_actions:
        if action.get("op") == "audio.play" and action.get("resource_id") not in resource_ids:
            err(f"audio.play引用未声明资源{action.get('resource_id')!r}")

    return errors


def _check_enum(obj: dict, field: str, allowed: set[str], err) -> None:
    value = obj.get(field)
    if value not in allowed:
        err(f"avatar.{field}={value!r}不在封闭枚举{sorted(allowed)}内")


def _check_condition(cond: object, var_names: set[str], where: str, err) -> None:
    if cond is None:
        return
    if not isinstance(cond, dict):
        err(f"{where}的condition必须是对象")
        return
    left = cond.get("left")
    if isinstance(left, dict) and set(left) == {"var"}:
        if left["var"] not in var_names:
            err(f"{where}的condition引用了未声明变量{left['var']!r}")
        left_type = "int"
    elif isinstance(left, dict) and set(left) == {"remaining_sec"} and left["remaining_sec"] is True:
        left_type = "int"
    else:
        err(f"{where}的condition.left只允许{{'var': name}}或{{'remaining_sec': true}}")
        left_type = None
    op = cond.get("op")
    if op not in COMPARE_OPS:
        err(f"{where}的condition.op {op!r}不在白名单{sorted(COMPARE_OPS)}内")
    right = cond.get("right")
    if isinstance(right, bool) or not isinstance(right, (int, str)):
        err(f"{where}的condition.right必须是常量")
    elif left_type == "int" and not _is_int(right):
        err(f"{where}的condition.right类型与左侧不一致，应为整数")


def _check_actions(actions: object, var_names: set[str], where: str, err) -> None:
    if actions is None:
        return
    if not isinstance(actions, list):
        err(f"{where}的动作列表必须是数组")
        return
    for i, action in enumerate(actions):
        loc = f"{where}的动作[{i}]"
        if not isinstance(action, dict):
            err(f"{loc}必须是对象")
            continue
        op = action.get("op")
        if op not in ACTIONS:
            err(f"{loc}的op {op!r}不在白名单{sorted(ACTIONS)}内")
            continue
        if op == "avatar.expression" and action.get("value") not in AVATAR_EXPRESSIONS:
            err(f"{loc}的expression值{action.get('value')!r}不在封闭枚举内")
        elif op == "avatar.motion" and action.get("value") not in AVATAR_MOTIONS:
            err(f"{loc}的motion值{action.get('value')!r}不在封闭枚举内")
        elif op == "audio.play":
            if not isinstance(action.get("resource_id"), str) or not action["resource_id"]:
                err(f"{loc}缺少resource_id")
        elif op == "timer.start":
            if not _is_int(action.get("seconds")) or action["seconds"] <= 0:
                err(f"{loc}的seconds必须是正整数")
        elif op in ("var.set", "var.increment"):
            if action.get("name") not in var_names:
                err(f"{loc}引用了未声明变量{action.get('name')!r}")
            if op == "var.set" and not _is_int(action.get("value")):
                err(f"{loc}的value必须是整数")
            if op == "var.increment" and not _is_int(action.get("value")):
                err(f"{loc}的value必须是整数")
        elif op == "game.end" and action.get("outcome") not in OUTCOMES:
            err(f"{loc}的outcome {action.get('outcome')!r}必须是escaped或carried_away")


def iter_manifest_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.json") if p.is_file())


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法: py -3.12 shared/tools/validate_buddies.py <presets目录>", file=sys.stderr)
        return 2
    root = Path(argv[1])
    if not root.is_dir():
        print(f"错误: 目录不存在: {root}", file=sys.stderr)
        return 2
    files = iter_manifest_files(root)
    if not files:
        print(f"错误: 目录内没有*.json: {root}", file=sys.stderr)
        return 2
    total_errors = 0
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"FAIL {path}: JSON解析失败: {exc}")
            total_errors += 1
            continue
        errors = validate_manifest(data)
        if errors:
            total_errors += len(errors)
            print(f"FAIL {path}")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"OK   {path}")
    print(f"共校验{len(files)}个规则包，错误{total_errors}个")
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
