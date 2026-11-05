---
doc_type: roadmap
slug: bad-habit-buddy
status: active
created: 2026-11-05
last_reviewed: 2026-11-05
tags: [ai, hardware, game, tuya-t5, public-library]
related_requirements: []
related_architecture: []
---

# 当代妖怪收容所：独立设备、语音生成与公共搭子库

## 1. 背景

《当代妖怪收容所》把用户描述的坏习惯生成一只具有独特性格与游戏规则的搭子。用户仅凭涂鸦T5-E1-Touch-AMOLED-1.75-G即可语音创建、确认并游玩；其他设备可从全局公共搭子库获取已发布搭子。已有搭子下载后离线可用，各设备始终独立游戏。

本规划落实已接受的[ADR 001](../../requirements/adrs/001-independent-buddy-architecture.md)，目标不是聊天机器人或实时联机系统，而是可反复演示的“生成角色即生成一局新游戏”。

## 2. 范围与明确不做

### 本 roadmap 覆盖

- 三个玩法规则明显不同的预设搭子及统一规则包执行器，用于验证表达力与离线体验。
- T5本机语音创建、候选搭子确认与具体逻辑生成。
- 参数化形象、触摸游戏、本地音频、单局记忆与双结局。
- 无登录全局公共搭子库、不可变发布、设备列表获取与完整缓存。
- 三台独立设备的生成、获取、离线游玩演示及错误收口。

### 明确不做

- 不做实时联机、对战、好友关系、设备配对或同步剧情。
- 不做本地生成式AI、本地通用语音识别或游戏中语音语义操作。
- 不下发或执行AI现场编写的任意代码。
- 不做账号、私人搭子库、搭子覆盖编辑、相似度检测或自动重写。
- 不做长期成长、跨局记忆、连续关卡、AI独立图片形象或必需外设。
- 不改造现有《拓》《蓝》《剪》原型，不以本 roadmap 处理其代码。

### Granularity Gate

| 判断项 | 结论 |
|---|---|
| 为什么不是 single feature | 跨T5运行时、生成服务、公共库与三设备验证，存在共享协议和明确依赖DAG，可分别验收。 |
| 为什么不是 brainstorm | 用户目标、核心行为、网络边界、游戏规模与不做项均已确认，ADR 001已接受。 |
| roadmap 边界 | 仅覆盖《当代妖怪收容所》的首版端到端原型及现场收口。 |
| 最小闭环 | `offline-preset-buddy`完成后，一台T5在断网状态下可玩一只预设搭子并得到两种结局。 |

## 3. 模块拆分（概设）

```text
当代妖怪收容所
├── shared/：统一搭子内容、规则包、资源清单与缓存元数据契约
├── device/：T5语音入口、本地执行器、参数化表演、游戏与离线缓存
└── server/
    ├── generation/：语音识别、候选生成、具体逻辑生成与规则校验
    └── library/：不可变发布、全局列表、详情与资源下载
```

### shared · 共享契约

- **职责**：定义设备与服务器共同遵守的规则包和资源格式，不包含具体游戏实现。
- **承载的子 feature**：`offline-preset-buddy`、`confirmed-buddy-generation`、`public-buddy-library`、`device-library-cache`。
- **触碰的现有代码 / 模块**：全新；仓库当前没有搭子代码。

### device · T5独立搭子终端

- **职责**：完成录音交互、候选确认、本地游戏、参数化表演、缓存与离线切换；不执行生成式AI。
- **承载的子 feature**：`offline-preset-buddy`、`voice-candidate-creation`、`device-library-cache`、`three-device-demo-hardening`。
- **触碰的现有代码 / 模块**：全新设备工程；硬件规格见`docs/event/hardware.md`。

### generation · 生成服务

- **职责**：将语音转成候选搭子，并在确认后生成符合共享契约的具体逻辑；不改变已确认内容。
- **承载的子 feature**：`voice-candidate-creation`、`confirmed-buddy-generation`。
- **触碰的现有代码 / 模块**：全新服务器模块；ASR、生成模型与音频合成账号需配置。

### library · 公共搭子库

- **职责**：保存和分发不可变搭子及资源，不管理用户身份，不保存或公开原始录音。
- **承载的子 feature**：`public-buddy-library`、`device-library-cache`、`three-device-demo-hardening`。
- **触碰的现有代码 / 模块**：全新服务器模块。

## 4. 模块间接口契约 / 共享协议（架构层详设）

所有网络接口以`/api/v1`为前缀，使用HTTPS；除音频上传外均使用JSON。客户端必须携带`request_id`用于日志关联。时间使用ISO 8601 UTC，散列使用小写十六进制SHA-256。

### 4.1 语音创建候选搭子

**方向**：device → generation  
**形式**：HTTP API

```text
POST /api/v1/buddy-candidates
Content-Type: multipart/form-data
字段：request_id: string, locale: "zh-CN", audio: 音频文件
音频上限：单段不超过30秒；具体编码由设备基线验证后固定为服务端支持的一种。

201 Response:
{
  "candidate_id": "cnd_...",
  "content": {
    "name": "最后一条",
    "personality": "害怕今天结束，总想再留用户一会儿",
    "gameplay_summary": "它会不断追加小任务；玩家需要忍住不再回应",
    "theme_tags": ["熬夜"]
  },
  "expires_in_sec": 86400
}
```

约束与错误：

- 响应只含候选内容，不返回原始录音；识别文本只作为服务端私有生成上下文，并随候选过期删除，不进入公共库。
- 原始录音在识别请求结束后即删除，不作为日志、调试样本或训练数据保存。
- 候选不是公共搭子，不能通过公共库查询。
- `400 invalid_audio`：编码、大小或时长不符合约束。
- `422 speech_unrecognized`：未获得可用语义。
- `422 content_not_supported`：输入无法转成安全、可玩的搭子主题。
- `429 rate_limited`：频率与并发限制只作用于候选和具体逻辑生成，不影响公共库浏览/下载；具体阈值由同IP三设备实测确定。
- `503 generation_unavailable`：识别或候选生成服务不可用。
- 候选过期后设备允许重新录音创建，不尝试恢复私有识别文本。

### 4.2 确认候选并生成具体逻辑

**方向**：device → generation  
**形式**：异步HTTP任务，避免设备长时间占用单个请求。

```text
POST /api/v1/buddy-generations
Request: { "request_id": "req_...", "candidate_id": "cnd_..." }
202 Response: { "generation_id": "gen_...", "status": "pending" }

GET /api/v1/buddy-generations/{generation_id}
Response:
{
  "generation_id": "gen_...",
  "status": "pending | succeeded | failed",
  "buddy_id": "bdy_... | null",
  "error_code": "candidate_expired | invalid_candidate | generation_failed | rule_validation_failed | null"
}
```

约束：

- 同一`candidate_id`重复提交返回同一进行中的任务；已成功任务返回同一`buddy_id`。
- 未知任务返回`404 generation_not_found`；已创建任务的状态查询返回200并由`status/error_code`表示失败。
- 成功后发布的`content`必须与候选的四个字段完全一致。
- 只有`schema_version`、规则可达性、资源清单、时长和双结局校验全部通过才可发布。
- 生成校验通过即自动发布，不需要第二次发布操作；任务进入`succeeded`时，返回的`buddy_id`必须已能从公共库读取。
- 失败不进入公共库；候选在有效期内可重新提交生成。

### 4.3 公共搭子库与不可变下载

**方向**：device → library  
**形式**：无登录HTTP API

```text
GET /api/v1/buddies?cursor={opaque_string}&limit=20
200 Response:
{
  "items": [{
    "buddy_id": "bdy_...",
    "schema_version": 1,
    "content": { "name": "...", "personality": "...", "gameplay_summary": "...", "theme_tags": ["..."] },
    "content_hash": "sha256...",
    "package_size": 12345,
    "published_at": "2026-11-05T10:00:00Z"
  }],
  "next_cursor": "opaque | null"
}

GET /api/v1/buddies/{buddy_id}
200 Response: { 列表项字段, "manifest_url": "https://..." }

GET /api/v1/buddies/{buddy_id}/manifest
200 Response: BuddyManifest
```

约束与错误：

- 列表按`published_at`降序、同刻按`buddy_id`降序稳定排序，cursor必须绑定该顺序。
- 列表不包含创造者原话、原始录音、识别文本、候选ID或规则源码说明。
- `buddy_id`发布后不可变；同ID的`content_hash`和manifest不得改变。
- `400 invalid_cursor`、`404 buddy_not_found`、`410 buddy_withdrawn`；撤回仅是`public-buddy-library`实现的内部运维操作，不提供公开或设备端撤回API，不删除设备已有缓存。

### 4.4 BuddyManifest与规则包

**方向**：generation → shared → library / device  
**形式**：版本化JSON与资源文件

```json
{
  "schema_version": 1,
  "buddy_id": "bdy_...",
  "content_hash": "sha256...",
  "content": {
    "name": "最后一条",
    "personality": "害怕今天结束，总想再留用户一会儿",
    "gameplay_summary": "它会不断追加小任务；玩家需要忍住不再回应",
    "theme_tags": ["熬夜"]
  },
  "avatar": {
    "face": "round",
    "eyes": "sleepy",
    "mouth": "small",
    "palette": ["#18243A", "#FFD166"],
    "motion_style": "drowsy"
  },
  "game": {
    "duration_sec": 75,
    "initial_node": "invite",
    "variables": [{ "name": "refusals", "type": "int", "initial": 0 }],
    "nodes": [{
      "id": "invite",
      "title": "最后一条",
      "instruction": "长按拒绝；点按接受",
      "on_enter": [{ "op": "avatar.expression", "value": "pleading" }],
      "transitions": [{
        "event": "touch.long_press",
        "to": "refused",
        "actions": [{ "op": "var.increment", "name": "refusals", "value": 1 }]
      }]
    }]
  },
  "resources": [{
    "resource_id": "voice_invite",
    "kind": "audio",
    "url": "builtin://voice_invite",
    "sha256": "sha256...",
    "size": 1234
  }]
}
```

执行器白名单与封闭值域：

- 事件：`game.start`、`touch.tap`、`touch.long_press`、`touch.swipe`、`timer.elapsed`。
- 动作：`avatar.expression`、`avatar.motion`、`audio.play`、`timer.start`、`var.set`、`var.increment`、`game.end`。
- `avatar.face`：`round | square | bean`；`eyes`：`sleepy | wide | side | dot`；`mouth`：`small | grin | flat | open`；`motion_style`：`drowsy | jittery | still | bouncy`。未知值拒绝，不静默替换。
- `palette`包含2—4个`#RRGGBB`颜色；`avatar.expression`值为`neutral | pleading | happy | smug | anxious | sleepy | angry`，`avatar.motion`值为`still | breathe | shake | bounce | nod`；未知值拒绝，不静默替换。
- `game.end`使用`{"op":"game.end","outcome":"escaped"}`表示“破解成功”，`outcome:"carried_away"`表示“被搭子带跑”。

条件表达式使用唯一JSON形式：

```json
{
  "event": "touch.long_press",
  "condition": { "left": { "var": "refusals" }, "op": "gte", "right": 3 },
  "to": "escaped_node",
  "actions": [{ "op": "game.end", "outcome": "escaped" }]
}
```

剩余时间条件使用`{"left":{"remaining_sec":true},"op":"lte","right":10}`；它只用于规则分支，不替代全局时间耗尽时的强制`carried_away`结局。

- `left`只允许`{"var":"已声明变量"}`或`{"remaining_sec":true}`；`right`只允许与左侧类型一致的常量。
- `op`只允许`eq | neq | gt | gte | lt | lte`；无`condition`表示无条件触发。
- 全局倒计时到达0且尚未成功时，执行器立即进入默认`carried_away`结局画面；同一事件循环中计时事件先于新触摸事件处理，规则不得覆盖该结局。

约束：

- 每个节点必须含`title`与`instruction`短文本，供设备显示当前角色台词和操作提示；v1触摸事件作用于整个游戏区域，不定义坐标或独立按钮命中区。
- 不包含可执行源码、动态脚本、任意URL跳转或未声明系统调用。
- `duration_sec`必须为60—90；所有节点、变量、条件和迁移必须静态可检查。
- 每个游戏必须至少存在一条到达`escaped`和一条到达`carried_away`的路径。
- 资源`url`只允许`https://`或`builtin://`；内置资源必须同时登记`sha256/size`并存在于固件资源表，设备校验本地散列而非下载。
- 所有远程资源须在开始游戏前下载并校验，内置资源须在开局前完成本地存在性与散列校验；缺资源不得进入一局。
- 设备拒绝未知`schema_version`、未知事件/动作/枚举、散列不符或超限包。

### 4.5 设备本地缓存

**方向**：library → device  
**形式**：设备本地索引＋完整规则包与资源

```text
LocalBuddyRecord {
  buddy_id: string,
  schema_version: int,
  content_hash: string,
  local_path: string,
  package_size: int,
  downloaded_at: ISO8601
}
```

约束：

- 只有manifest及全部资源通过校验后，记录才标记为可玩；下载过程使用临时位置并原子替换。
- 本地列表可包含预设和已下载搭子；二者使用同一执行器。
- 离线打开已有搭子不得发起必需网络请求。
- 错误：`network_unavailable`、`unsupported_schema`、`hash_mismatch`、`resource_missing`、`storage_full`；失败不得破坏既有可玩缓存。

### 4.6 设备界面与导航契约

**方向**：device内部跨feature共享  
**形式**：三个顶级页面＋一个详情二级页面

```text
主界面 ⇄ 搭子游戏页
主界面 ⇄ 生成页
主界面 ⇄ 搭子详情页
```

- **主界面**：一屏选中一只搭子，滑动切换；本地搭子在前，成功获取公共库时在线搭子在后。本地搭子点按直接游戏；在线搭子点按下载并校验后自动游戏；任一搭子长按打开详情。开机自动刷新一次公共库，允许手动刷新，从游戏/详情返回不刷新。
- **主界面降级**：获取失败时保留本地列表并提示“当前仅显示本地搭子”；下载失败保留原卡片与重试入口，不改变当前选择。
- **搭子详情页**：只显示搭子内容、主题标签和本地/在线状态；关闭后回到原选中卡片，不显示创造者原话或具体逻辑。
- **搭子游戏页**：打开即开始；左上角固定返回按钮，其余区域为游戏区。返回立即放弃本局并回主界面，不保留中途状态。
- **生成页**：按住说话→候选确认→生成→下载校验→自动进入新搭子游戏；支持重说、重试和返回，失败不影响本地搭子。
- 首条`offline-preset-buddy`只验收本地预设、详情、游戏与生成页离线不可用状态；在线下载和生成行为由后续feature验收。

## 5. 子 feature 清单

1. **offline-preset-buddy** — 建立T5工程基线、规则包v1执行器与三只玩法不同的预设搭子，断网可玩出两种结局。
   - 所属模块：shared、device
   - 依赖：无；完成信号：先完成T5 SDK与触摸/显示/音频可行性spike，再让三只预设通过规则校验；每只断网连续完成3局，双结局各至少出现1次，重开后单局变量复位。
   - 状态：planned；对应 feature：未启动；证据：真机视频、构建/测试命令、规则校验结果。
2. **voice-candidate-creation** — 建立生成服务测试基线，并让用户按住T5说话获得候选搭子的名称、性格、玩法简介与主题标签。
   - 所属模块：device、generation
   - 依赖：`offline-preset-buddy`提供真机工程与触摸/音频基线。
   - 状态：planned；对应 feature：未启动；完成信号：3句不同坏习惯输入分别返回可确认候选，无效语音、服务503与生成接口429各注入1次且本地搭子入口仍可用；公共库浏览/下载不计入生成限流。
   - 证据：真实语音API响应、设备录屏、服务器测试与错误态。
3. **confirmed-buddy-generation** — 确认候选后异步生成并校验可执行规则包，通过最小发布通路写入公共库，保持已确认内容逐字不变。
   - 所属模块：shared、generation、library最小发布通路、device验证入口
   - 依赖：`voice-candidate-creation`提供候选；`offline-preset-buddy`提供规则包v1与执行器。
   - 状态：planned；对应 feature：未启动；完成信号：至少2只自定义搭子通过内容diff与双结局校验并分别在真机完整运行1局；最小发布通路保证任务成功时已可按ID读取，失败候选不入库。完整列表、分页与撤回不在本条。
   - 证据：生成任务响应、内容diff、双路径校验报告、真机视频。
4. **public-buddy-library** — 将生成成功的搭子不可变发布到无登录公共库并提供稳定分页、详情和资源下载。
   - 所属模块：library、shared
   - 依赖：`confirmed-buddy-generation`提供通过校验且自动发布的搭子。
   - 状态：planned；对应 feature：未启动；完成信号：API测试覆盖分页顺序、公开字段、同ID不可变、撤回与404/410响应。
   - 证据：API集成测试、公开字段检查、不可变与撤回测试。
5. **device-library-cache** — T5浏览公共库、原子下载完整搭子并离线切换已有缓存。
   - 所属模块：device、library
   - 依赖：`public-buddy-library`提供下载契约；`offline-preset-buddy`提供本地执行与存储基线。
   - 状态：planned；对应 feature：未启动；完成信号：下载至少2只搭子并分别断网完整玩1局；坏包、下载中断、存储不足各注入1次，既有缓存仍可玩。
   - 证据：下载后断网视频、损坏包/存储不足/断网恢复测试。
6. **three-device-demo-hardening** — 用三台独立T5完成生成、公共库获取和离线预设演示，并收口主要错误与回归。
   - 所属模块：device、generation、library
   - 依赖：`device-library-cache`提供完整端到端路径。
   - 状态：planned；对应 feature：未启动；完成信号：A生成、B获取后断网游玩、C离线预设各完成1次；断网、坏包、存储写满、服务503故障注入各1次且不破坏既有缓存。
   - 证据：三机演示视频、分项验收记录、故障注入结果。

**最小闭环**：第1条`offline-preset-buddy`完成后，一台T5断网选择预设搭子，完成60—90秒触摸游戏并呈现双结局。

### Goal Coverage Matrix

| Goal / completion signal | Covered by item(s) | Verification entry | Evidence type | Core? |
|---|---|---|---|---|
| 单台T5离线完整游玩已有搭子 | offline-preset-buddy、device-library-cache | 真机断网游戏与重开 | 真机视频、测试 | yes |
| 单台T5语音创建候选并确认 | voice-candidate-creation | 按住说话的真实创建路径 | API响应、设备录屏 | yes |
| 确认内容不变并生成可玩新规则 | confirmed-buddy-generation | 内容diff、规则校验、真机运行 | 测试、校验报告、视频 | yes |
| 全局公共库无登录分发不可变搭子 | public-buddy-library | 列表/详情/下载与不可变测试 | API集成测试 | yes |
| 三设备独立运行且无实时联机 | three-device-demo-hardening | A生成、B下载、C离线预设 | 三机视频、验收记录 | yes |
| 不公开原话且不长期保存录音 | voice-candidate-creation、public-buddy-library | 数据记录与API字段审计 | 集成测试、diff review | yes |
| 网络、坏包和无效输入不破坏已有体验 | device-library-cache、three-device-demo-hardening | 故障注入与恢复路径 | 测试、真机记录 | yes |

## 6. 排期思路

技术依赖决定顺序：先在T5证明预设游戏与规则执行器，避免服务器生成出设备无法运行的内容；随后验证语音候选，再接具体生成、公共库与缓存；最后用三机演示统一收口。除该依赖顺序外，本 roadmap 不额外替团队安排产品优先级。

### 赛程对齐

| 目标日期 | 条目 | 退出与降级边界 |
|---|---|---|
| 11月5日 | `offline-preset-buddy` | 当天先完成SDK/触摸/音频spike；若真机基础链路不可用，暂停服务器扩展并优先修设备地基。 |
| 11月6日 | `voice-candidate-creation`、`confirmed-buddy-generation` | 至少留下2只真实生成并在T5运行的搭子；未通过校验的候选不得发布。 |
| 11月7日提交前 | `public-buddy-library`、`device-library-cache` | 优先保证真实生成与单机离线游玩；若公共库链路未稳定，不得以视频冒充多设备成果，应明确缩减现场主张。 |
| 11月7日冻结前至11月8日 | `three-device-demo-hardening` | 只做三机验证、故障收口与材料整理，不新增联机或新游戏机制。 |

若`confirmed-buddy-generation`在11月6日未完成，依赖它的第4—6条必须顺延，不用预生成结果冒充现场生成；11月7日优先交付真实可玩的单机与离线预设，并明确缩减公共库和三机演示主张。

以上是倒排目标而非已完成承诺；实际提交时刻以组委会通知为准。

当前仓库没有T5或服务器工程、CI及现成测试命令，旧《拓》Python命令不是本项目的验证基线。第1条必须建立设备构建与规则校验入口，第2条建立服务器测试入口；后续feature不得跳过这些基线。

### Top 3风险与缓解

1. **生成规则语法合法但不可玩**：规则包v1先落地；生成时检查节点、资源、时长和双结局可达性，并安排真机运行生成搭子。
2. **展馆噪声、网络或匿名接口限流使创建失败**：第1条先交付离线预设；第2条实测麦克风与错误态；匿名生成接口设置频率/并发限制并返回`429`，失败时保留已有本地搭子入口。
3. **包资源或缓存不一致导致跨设备失败**：manifest带版本、大小和SHA-256，原子下载，第6条用三台真机验证并注入坏包/断网。

### 非显然依赖与关键假设

- 依赖T5官方开发环境、可用Wi‑Fi、ASR/生成模型/音频合成服务及凭证；凭证不得写入公开仓库。
- 假设T5能以选定音频编码完成30秒以内录音上传，并在本地执行规则包与播放资源；第1、2条先验证。
- 假设三台设备存储可支撑限定大小的缓存；不默认有Micro SD卡，容量与淘汰策略由对应feature设计。
- 外部服务的生成时延和限流尚未实测；异步生成接口用于隔离该不确定性。

### 交付物与知识回写

- 每条完成后须留下对应设备/服务器/共享代码、可运行验证入口、测试或真机记录，并更新items.yaml状态。
- 经验证的音频编码、包大小限制、设备存储约束和生成时延应在对应acceptance后进入`attention`或`compound`；本规划不提前编造参数。

## 7. 观察项

- 当前术语位于`.codestable/requirements/CONTEXT.md`；初期《拓》《蓝》《剪》方案、调研、原型和旧计划已统一移入`archive/initial-directions/`。
- README与`docs/project/`已指向当前《当代妖怪收容所》；历史档案不作为后续feature输入。
- 正式开发前需实机核对T5 SDK、音频编码、触摸手势与存储能力，不能把产品页规格当作端到端验证结果。
