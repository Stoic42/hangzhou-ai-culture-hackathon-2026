# 玩法改版实施计划（gameplay-v2）

日期：2026-11-07。依据：[ADR 002](../../requirements/adrs/002-pressure-value-replaces-countdown.md) 与 `docs/project/decisions.md` 2026-11-07 小节。
分支：`feat/gameplay-v2`（基于 main 77633e8）。

## 总目标

消除"干等倒计时判负"的枯燥，扩充输入动词与玩法模板，接入板载 KEY 键与 QMI8658 IMU。

## 核心设计（所有任务共同遵守）

### 规则包 v2（schema_version: 2）

相对 v1 的变化：

1. **压力值取代倒计时主导胜负**
   - `game.pressure` 对象：`{"initial": 50, "rise_per_sec": 3, "min": 0, "max": 100}`，四字段均必填整数，0<=min<initial<max<=1000，rise_per_sec>=1。
   - 压力每秒钟自动上涨 rise_per_sec（侵蚀式）。压力 >= max 自动判 `carried_away`；压力 <= min 自动判 `escaped`。
   - 新动作 op `pressure.adjust`：字段 `value` 为整数（负值降压=奖励，正值升压=惩罚），由规则挂在正确/错误操作上。
   - `game.duration_sec` 在 v2 中变为**可选兜底上限**（60—180 秒），到时仍未分胜负才判 `carried_away`；不再是主要失败机制。v1 包保持原语义（duration 60—90 秒必填、归零判负）。
   - 条件判断的左操作数新增 `{"pressure": true}`（与现有 `{"var": name}`、`{"remaining_sec": true}` 并列互斥）。

2. **新事件**
   - `touch.swipe_left` / `touch.swipe_right` / `touch.swipe_up` / `touch.swipe_down`：方向滑动。原 `touch.swipe` 保留（v1 兼容；v2 中任意方向滑动也同时触发一次 `touch.swipe` 事件，方向事件先匹配）。
   - `touch.rapid_tap`：连点事件。引擎维护连击计数：两次 tap 间隔 <=400ms 则连击+1，否则重置为 1；每当连击数 >=2 时额外发出一次 `touch.rapid_tap` 事件（规则可用 `var.increment` 计数）。
   - `imu.shake`：摇晃事件，由平台层注入（引擎只消费事件，不做传感器检测）。
   - 引擎会话记录统计：`elapsed_sec`、`combo_peak`（最大连击）、`mistakes`（升压动作触发次数）、`relieves`（降压动作触发次数），供结局评级使用。

3. **吐槽文案与评级**
   - `game.quips` 必填对象：`{"escaped": [至少1条], "carried_away": [至少1条]}`，每条 1—40 字。
   - 评级不由规则包决定，由会话统计按固定公式计算（S/A/B/C）：以结束时压力距危险边界的余量、elapsed、combo_peak 加权；具体公式在任务4固件实现，公式常量集中在引擎头文件。

4. **校验**：`shared/tools/validate_buddies.py` 与 `server/app/generation/validate.py` 支持 v2 全部新字段的封闭白名单校验；`schema_version` 只接受 1 或 2，v2 包必须含 pressure 与 quips，v1 包不含这两者的校验不受影响。`simulate_buddies.py` 支持 v2 事件与压力模拟。

### 四个玩法模板（任务3/5 共用）

1. **拒绝×3（refuse）**：现有 last_one 迁移到 v2 结构（加 pressure 与 quips）。
2. **方向滑动对抗（swipe_duel）**：妖怪从某方向逼近（节点标题/表情提示方向），玩家朝指定方向滑动将其推回；推回 N 次（默认3）压力清空获胜；滑错方向升压。
3. **连点节奏（rhythm_tap）**：玩家在时限窗口内连点驱赶妖怪；用 rapid_tap 计数，达到 N 次（默认8）降压大胜；中途停顿超窗连击清零（由引擎连击重置自然实现）。
4. **摇晃甩掉（shake_off）**：妖怪缠在身上，摇晃 N 次（默认5）甩掉；每次 shake 降压，错误触摸微升压。

### 硬件（任务2/6）

- KEY＝IO12（上拉、按下低电平）。单击=返回上一级；游戏中单击=直接退出并记 `carried_away`（播 quips）；按住>=500ms=PTT 开始录音，松开结束（本任务只留钩子与状态机，录音链路接现有 buddy 创建流程）。
- QMI8658：I2C 地址 0x6B，SCL=IO20、SDA=IO21（与触摸/RTC 共总线），INT1=IO7。SHAKE 检测：加速度三轴合加速度与 1g 偏差滑动窗口峰值 > 阈值（默认 0.6g）且 300ms 内未重复触发 → 注入一次 `imu.shake`。阈值做成编译期常量便于任务7调参。

## 任务拆分

### 任务1：规则包 v2 + 引擎新事件与压力值（平台无关）

- `device/t5/src/buddy_engine.h/.c`：
  - `schema_version` 1/2 双版本解析校验；v2 解析 pressure/quips。
  - 新事件枚举：`BUDDY_EVENT_SWIPE_LEFT/RIGHT/UP/DOWN`、`BUDDY_EVENT_RAPID_TAP`、`BUDDY_EVENT_SHAKE`；方向滑动先匹配方向事件，无匹配再回落 `BUDDY_EVENT_SWIPE`。
  - 引擎内连击计数（tap 间隔<=400ms；需要会话增加 `last_tap_ms`，事件入口传入当前毫秒tick：`buddy_session_handle` 增加 `now_ms` 参数或新增带参函数，保持旧签名兼容可用宏/内联包装）。
  - 压力值：`session.pressure`；每秒 tick（沿用现有 timer 路径）自动 +rise_per_sec；触及 min/max 自动出结局（min→escaped，max→carried_away）；`pressure.adjust` 动作；条件左值 `pressure`。
  - 兜底：v2 有 duration_sec 时到时判 carried_away；无 duration_sec 不判。
  - 会话统计字段 elapsed_sec/combo_peak/mistakes/relieves。
  - quips 解析进 buddy 结构（2×最多4条，每条<=40字）。
- `shared/tools/validate_buddies.py`、`shared/tools/simulate_buddies.py` 同步支持 v2。
- 测试：扩充主机侧引擎测试（沿用现有 34 项测试的框架与运行方式，位置在 device/t5 现有测试处），覆盖：压力侵蚀判负、压力清空判胜、方向事件优先于无方向回落、连击窗口与重置、shake 事件、v1 包回归不变。全部主机测试必须通过。
- 不改 buddy_ui.c（UI 在任务4）。

### 任务2：三个离线预设迁移 + 新增（shared/presets）

- 现有 last_one / do_now / decide_now 迁移为 v2（补 pressure/quips，玩法结构不变）。
- 新增 3 个预设：swipe_duel、rhythm_tap、shake_off（按上方模板定义，含 quips、参数化形象沿用现有枚举白名单）。
- `simulate_buddies.py` 对 6 个预设全部跑通双结局；`validate_buddies.py` 全绿。
- 固件内嵌预设表（`device/t5/src/generated/` 或 presets 打包脚本 `gen_*`）重新生成。

### 任务3：服务器模板库 ×4

- `server/app/providers/stub.py`：按 buddy 种子确定性选择 4 模板之一并填参数（次数/速度/文案/quips）。
- `server/app/providers/openai_llm.py`：LLM prompt 改为"选择模板+填参数"，输出受模板 schema 约束。
- `server/app/generation/validate.py` 用 v2 校验（与 shared 对齐）。
- pytest 全绿，新增：4 模板各生成-校验-模拟双结局；v1 旧包兼容。

### 任务4：固件 UI（buddy_ui.c）

- 游戏区分发方向滑动事件（复用首页方向判定逻辑）。
- 压力条 UI（圆屏顶部弧形或顶部条，随压力变色绿→红），倒计时数字改为可选兜底显示。
- 结局屏：评级（S/A/B/C，公式常量集中在 buddy_engine.h）+ 从规则包 quips 随机/轮换一条 + 既有重开/返回。
- 游戏中单击 KEY（由任务5提供事件）→ 直接退出记 carried_away 并走结局屏。

### 任务5：KEY 键接入（IO12）

- GPIO 输入轮询或中断（遵循 Tuya SDK 现有按键/GPIO 用法），消抖 30ms。
- 状态机：单击（<500ms 释放）=返回事件；按住>=500ms=PTT 开始钩子，释放=PTT 结束钩子（钩子先空实现+日志，接录音链路留给联调）。
- 事件注入 buddy_ui：非游戏界面=返回上一级；游戏中=任务4的退出判负。

### 任务6：IMU SHAKE（QMI8658）

- I2C（IO20/IO21，0x6B）初始化（遵循 Tuya SDK tkl_i2c 用法，注意与触摸共总线）。
- 50Hz 轮询加速度，SHAKE 检测（见核心设计），事件注入引擎。
- 编译期开关 `BUDDY_IMU_ENABLE`，默认可关，便于无传感器环境回归。

### 任务7：实机联调与调参

- 烧录真机验证：KEY 单击/按住、SHAKE 阈值、压力曲线节奏（目标单局 20—60s 自然分胜负）、6 预设双结局。
- 记录调参结果到 `docs/project/hardware-check-2026-11-06.md` 追加小节。

## 验收

- 主机 C 测试 + simulate/validate + server pytest 全绿。
- 6 个预设与服务器 4 模板均可在仿真中达成双结局。
- 真机：方向滑/连点/摇晃可操作，KEY 单击返回与游戏退出记负生效，单局时长 20—60s。
