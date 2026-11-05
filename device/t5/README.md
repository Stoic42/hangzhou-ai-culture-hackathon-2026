# T5设备端

《当代妖怪收容所》的T5-E1-Touch-AMOLED-1.75-G应用：offline-preset-buddy 设备端。
主界面滑动选择三只本地预设搭子，点按进入离线游戏，长按查看详情；生成页显示离线不可用。
游戏页按规则包v1执行触摸迁移、条件、变量与倒计时，倒计时归零强制"被搭子带跑"结局。

## 工具链

使用官方TuyaOpen。SDK位于开发机项目外的`F:\t5open`，不进入公开仓库。

```powershell
. F:\t5open\export.ps1
subst.exe W: F:\Project\hangzhou-ai-culture-hackathon-2026\worktrees\offline-preset-buddy   # 如W:映射失效
Set-Location W:\device\t5
tos.py build
tos.py flash   # 选择实际CH342 A号烧录口（本机初次识别COM4）
tos.py monitor # 选择实际CH342 B号日志口（本机初次识别COM8）
```

## 源码结构

- `src/main.c` — 启动入口：日志、硬件注册、音频编解码、LVGL vendor，随后进入搭子应用。
- `src/buddy_engine.c/.h` — 规则包v1解析与校验（对照`shared/tools/validate_buddies.py`的
  封闭白名单、时长60—90、双结局与escaped图可达性），以及单线程GameSession状态机
  （触摸/计时事件、条件求值、变量、倒计时归零强制carried_away）。不执行任何动态脚本。
- `src/buddy_ui.c/.h` — LVGL界面：主界面轮播（滑动手势切换、点按开局、长按详情）、
  详情页、生成页离线不可用提示、游戏页（左上固定返回、1秒LVGL timer倒计时、
  参数化形象按face/eyes/mouth/palette绘制并区分7种expression与5种motion）。
- `src/ui_text.h` — 全部界面中文字符串。
- `src/builtin_assets.h` + `src/generated/` — 生成的固件资产（见下）。
- `tools/gen_assets.py` — 资产生成器。

## 预设与资源嵌入方式

预设规则包、反馈音频与中文字体均编译进固件，不依赖Flash文件系统或SD卡：

1. `shared/presets/*.json`被minify后以C字符串数组嵌入（`generated/builtin_presets.c`），
   设备启动时用cJSON解析并做完整校验；非法包只记录错误日志，不会出现在可选列表。
2. `shared/assets/feedback.pcm`（16kHz mono 16bit）以字节数组嵌入
   （`generated/feedback_pcm.c`）。资源表登记其size与SHA-256；开局前用`tal_sha256_ret`
   校验嵌入数据与固件资源表一致，manifest声明与固件表不符或散列错误时拒绝开局。
3. UI中文使用SimSun子集字体（`generated/buddy_font.c`），由`lv_font_conv`基于
   SDK内置`SimSun.woff`生成，只包含预设文本与`src/ui_text.h`中的界面字符
   （SDK自带的1000部首版SimSun字体无法覆盖全部预设文案，故生成子集字体）。

重新生成资产（修改预设、`ui_text.h`或feedback.pcm后必须执行，需要Node.js/npx联网）：

```bash
py -3.12 device/t5/tools/gen_assets.py --sdk F:\t5open   # 仓库根目录执行
```

## 验收提示

- 状态与错误日志（预设校验结果、节点迁移、结局、放弃/重开）输出到日志串口，
  可在`tos.py monitor`中观察，不刷屏。
- 断网即可完整游玩；固件内无任何网络、Wi-Fi、下载或动态代码路径。
