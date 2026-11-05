# 《当代妖怪收容所》开发计划

当前唯一实施方向为《当代妖怪收容所》。详细接口、依赖和量化验收以CodeStable规划为准；本页是面向协作者的入口与赛程摘要。

## 权威规划

- [完整roadmap](../../.codestable/roadmap/bad-habit-buddy/bad-habit-buddy-roadmap.md)：模块拆分、接口契约、风险与排期。
- [子feature清单](../../.codestable/roadmap/bad-habit-buddy/bad-habit-buddy-items.yaml)：状态与依赖的机器可读记录。
- [独立规划审查](../../.codestable/roadmap/bad-habit-buddy/bad-habit-buddy-roadmap-review.md)：三轮审查结果与残余风险。
- [架构ADR](../../.codestable/requirements/adrs/001-independent-buddy-architecture.md)：独立设备、服务器生成、公共库和离线缓存的已拍板决策。

## 实施顺序

| 顺序 | 子feature | 可观察完成信号 |
|---|---|---|
| 1 | `offline-preset-buddy` | 三只玩法不同的预设搭子在T5断网运行，双结局与重开重置可验证 |
| 2 | `voice-candidate-creation` | T5本机录音后返回候选名称、性格和玩法简介，错误态可恢复 |
| 3 | `confirmed-buddy-generation` | 至少两只自定义搭子通过校验、真机运行并经最小通路发布 |
| 4 | `public-buddy-library` | 无登录公共列表、稳定分页、不可变下载与内部撤回通过API测试 |
| 5 | `device-library-cache` | 下载后断网可玩，坏包、中断和存储不足不破坏既有缓存 |
| 6 | `three-device-demo-hardening` | A生成、B下载后离线玩、C离线预设，完成故障注入与回归 |

## 赛程

- **11月5日**：优先完成T5 SDK与离线预设闭环，设备基础链路不通过则不扩展服务器。
- **11月6日**：完成语音候选与具体规则生成，留下真实生成并在T5运行的搭子。
- **11月7日**：提交前完成公共库与缓存；冻结前完成三机验证和故障收口，不新增联机功能。
- **11月8日**：按现场确认的演示时长展示真实成果。

这是倒排目标，不是已完成记录。若生成链延期，优先交付真实可玩的单机与离线预设，并明确缩减公共库及三机演示主张；不使用回放冒充现场能力。

## 验证与记录

每条子feature启动时使用 `cs-feat-design` 读取完整roadmap第4节接口契约，完成后留下构建/测试命令、API响应或真机视频，并由验收流程回写items.yaml。凭证不得进入公开仓库。

### 服务器侧进展（11-06）

服务器侧（契约 4.1 语音候选、4.2 异步生成、4.3 公共搭子库 + 口令保护的管理后台）已于 11-06 完成：`server/` 下 43 个 pytest 全绿，并经 uvicorn 真实启动冒烟（上传 WAV→候选→生成→公共库→后台撤回→410）。默认 stub Provider 为确定性假数据，可随时经 `SERVER_PROVIDER=remote` 环境变量切换真实 ASR/LLM。剩余依赖为设备侧基线（音频编码确认）与真机联调，详见 `server/README.md` 与 `.codestable/features/2026-11-06-server-generation-library/`。
