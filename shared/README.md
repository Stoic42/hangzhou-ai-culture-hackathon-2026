# shared/ — 规则包v1共享契约（主机端）

本目录保存`offline-preset-buddy`的共享部分：规则包v1（BuddyManifest）静态校验器、
三只随固件预置的中文预设，以及主机端单元测试。设备运行时见`device/`，两者只通过
规则包v1 JSON耦合。

## v1范围

- 仅离线JSON规则包；`schema_version`必须为1，设备拒绝其他版本。
- 封闭白名单：事件`game.start/touch.tap/touch.long_press/touch.swipe/timer.elapsed`；
  动作`avatar.expression/avatar.motion/audio.play/timer.start/var.set/var.increment/game.end`。
  未知事件、动作或枚举一律拒绝，不静默替换。
- `game.duration_sec`必须在60—90秒之间；全局倒计时耗尽强制进入`carried_away`结局。
- 每个包必须同时存在`escaped`（破解成功）与`carried_away`（被搭子带跑）双结局，
  且`escaped`结局从`initial_node`图可达（`carried_away`含全局超时兜底）。
- 资源`url`只允许`builtin://`或`https://`，必须登记`sha256`（64位十六进制）与`size`。
  本feature预设引用同一个内置PCM反馈音（`builtin://feedback`），不使用远程资源。
- 不执行动态脚本、任意代码或未知动作；条件表达式只支持`left(var/remaining_sec)`、
  比较`op(eq/neq/gt/gte/lt/lte)`与常量`right`。

## 目录

- `tools/validate_buddies.py` — 静态校验器（Python 3.12标准库，无第三方依赖）。
- `presets/last-one.json` — 最后一条（熬夜）：点按接受追加，长按拒绝，拒绝3次`escaped`。
- `presets/do-now.json` — 现在做（拖延）：滑动累计行动，点按拖延清零，行动3次`escaped`。
- `presets/decide-now.json` — 快选吧（选择困难）：点按在A/B切换，滑动锁定，锁定2次`escaped`。
- `tests/test_validate_buddies.py` — 合法三预设与主要负例的unittest覆盖。

## 命令（仓库根目录执行）

```bash
# 校验三只预设（任一错误退出码非0）
py -3.12 shared/tools/validate_buddies.py shared/presets

# 运行共享契约单元测试
py -3.12 -m unittest discover -s shared/tests -v
```
