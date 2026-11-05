# 《当代妖怪收容所》

**一万个回答·AI文化造物黑客松 2026｜杭州白马湖｜2026年11月5日至8日**

《当代妖怪收容所》把用户的当代坏习惯生成一只具有独特性格和游戏规则的妖怪搭子。用户直接用涂鸦T5-E1说话创建搭子，通过触摸完成一场60—90秒的破解游戏；其他设备可以从公共搭子库获取已经发布的内容。

## 当前状态

- **当前唯一开发方向**：《当代妖怪收容所》。初期《拓》《蓝》《剪》暂无实施计划，已完整归档。
- 团队有三台T5-E1-Touch-AMOLED-1.75-G，各设备独立运行，不做实时联机。
- 架构决策与roadmap已建立并通过独立规划审查；roadmap已激活，首个`offline-preset-buddy`设计已批准并进入实现。
- **当前尚无搭子设备端或服务器实现代码**，下一步是T5离线预设与规则包执行器。

## 核心体验

1. 按住T5说话，描述一个坏习惯。
2. 服务器识别语音并生成候选搭子的名称、性格和玩法简介。
3. 用户确认后，服务器生成可执行规则包并发布到全局公共搭子库。
4. 本机下载后离线游玩；其他联网设备也可获取该搭子。
5. 预设搭子和已下载搭子无需网络即可切换、重玩。

AI不直接下发代码，而是组合经过验证的行为图规则；T5负责参数化形象、触摸交互、本地音频与单局状态。

## 从这里开始

| 内容 | 入口 |
|---|---|
| 当前开发计划与实施顺序 | [开发计划](docs/project/roadmap.md) |
| 完整架构与接口契约 | [CodeStable roadmap](.codestable/roadmap/bad-habit-buddy/bad-habit-buddy-roadmap.md) |
| 已拍板的架构取舍 | [ADR 001](.codestable/requirements/adrs/001-independent-buddy-architecture.md) |
| 领域术语 | [CONTEXT](.codestable/requirements/CONTEXT.md) |
| 当前结论与待验证项 | [讨论记录](docs/project/decisions.md) |
| 赛事要求与日程 | [赛事摘要](docs/event/guide.md) · [赛程](docs/event/schedule.md) |
| T5规格与现场资源 | [硬件资源](docs/event/hardware.md) |
| 提交与路演材料 | [提交材料](docs/project/submission.md) |
| 初期《拓》《蓝》《剪》档案 | [历史档案](archive/initial-directions/README.md) |

## 目录组织

```text
.codestable/requirements/  # 当前领域术语与架构ADR
.codestable/roadmap/       # 当前roadmap、子feature状态与审查
docs/event/                # 赛事规则、日程和硬件资料
docs/project/              # 当前决策、开发入口与提交材料
archive/initial-directions/ # 无实施计划的旧方案、调研和原型
```

规划中的新代码模块为`device/`、`server/`和`shared/`；它们将在对应子feature启动后创建，不把规划目录当作已有实现。

## 信息来源与协作

赛事和硬件资料以组委会及厂商最新信息为准。文档区分已确认规格、用户决策和待实机验证能力。公开协作遵循[协作约定](CONTRIBUTING.md)，密钥、场馆凭据和原始语音不得进入公开仓库。
