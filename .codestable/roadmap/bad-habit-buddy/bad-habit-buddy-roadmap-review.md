---
doc_type: roadmap-review
roadmap: bad-habit-buddy
status: passed
reviewed: 2026-11-05
round: 3
---

# bad-habit-buddy roadmap 审查报告

## 1. Scope And Inputs

- Roadmap: `.codestable/roadmap/bad-habit-buddy/bad-habit-buddy-roadmap.md`
- Items: `.codestable/roadmap/bad-habit-buddy/bad-habit-buddy-items.yaml`
- Related docs: ADR 001、根目录`CONTEXT.md`、`docs/project/decisions.md`、`docs/event/hardware.md`、`docs/event/schedule.md`、旧`docs/project/roadmap.md`
- Code facts checked: 仓库无T5/服务器工程、CI或现成测试入口；仅存在无关《拓》Python原型。

### Independent Review

- Status: completed
- Detection: native-agent
- Provider / agent: 三轮独立general-purpose agent审查
- Raw output: 第一轮提出排期、schema、发布与量化问题；第二轮无blocking并指出撤回/限流/隐私边界；第三轮指出最小发布通路层级问题。
- Merge policy: 已逐条对照roadmap/items本地核验并修订；未采纳“用视频替代三机实机”的建议。
- Gate effect: 第三轮剩余important已通过“第3条提供最小按ID发布通路，第4条提供完整列表/分页/撤回”消除。

## 2. Roadmap Summary

- Goal completion signal: 单机离线预设、本机语音创建、确认后生成新规则、公共库分发、三设备独立演示均有可观察证据。
- Module split: shared契约、device终端、generation服务、library公共库，职责独立。
- Interface contracts: 包含语音上传、异步生成、公共列表/下载、规则包JSON、条件语法、错误码与本地缓存原子性。
- Items: 6条；最小闭环为`offline-preset-buddy`；第1条验证表达力，第6条承担收口。
- Dependency shape: 无环DAG；第3条包含最小发布通路，第4条扩展完整公共库，不存在验收前置倒置。

## 3. Findings

### blocking

- none

### important

- none unresolved。
- 已处理：赛程倒排、服务器基线归属、条件/枚举/结局语法、自动发布时刻、量化验收、匿名限流、内部撤回边界、识别文本生命周期、最小发布通路层级。

### nit

- none unresolved。
- `items.yaml`校验使用内置简化解析器并给出PyYAML未安装警告；结构已由独立review逐项核对，后续安装PyYAML后可再跑严格解析。

### suggestion

- none

### learning

- 白名单行为图＋静态校验可同时保留生成自由度与设备可执行性。
- 最小发布通路与完整公共库API应分层验收，避免依赖方向与完成信号相互倒置。

### praise

- 离线预设优先于服务器扩展，直接降低现场网络风险。
- 范围明确排除实时联机、任意代码下发与长期养成，与ADR一致。
- 降级只缩减主张，不用视频或预生成内容冒充未发生的现场能力。

## 4. User Review Focus

- 用户需要重点拍板：6条拆解与倒排顺序是否符合团队投入；是否接受第1条用三只玩法不同预设验证表达力。
- 后续feature-design需要重点复核：T5 SDK可行性、规则包资源上限、外部ASR/生成/音频合成选型与凭证。
- 不能靠roadmap review完全确认：实机录音质量、生成时延、同IP限流阈值、Flash缓存容量。

## 5. Evidence Confidence Ledger

| Check | Verdict | Evidence Class | Basis | Follow-up |
|---|---|---|---|---|
| Granularity Gate | pass | E | 主文档第2节，跨四个模块与6条独立交付 | none |
| Goal Coverage Matrix | pass | E | 第5节矩阵覆盖7个核心目标及证据 | 各feature落实命令 |
| DAG and minimal loop | pass | E | items六条无未知依赖/环；仅第1条minimal_loop=true | none |
| Interface contract usability | pass | E/C | 第4节字段、示例、错误码、白名单与ADR一致 | 真机spike验证编码/容量 |
| Verification and schedule | pass | E/C | 量化次数、故障注入与11月5—8日倒排可见 | 按实际提交通知调整 |

Summary: E=5, C=2（部分检查同时含C）, H-only core checks=none。

## 6. Residual Risk

- T5实机SDK、音频编码、触摸、存储与播放尚未验证；第1条必须先做spike，失败时暂停后续扩展。
- ASR、生成模型和音频合成服务尚未选型，时延/限流/成本未知；第2条需以真实凭证联调。
- 现场Wi‑Fi与同IP三设备限流仍待实测；公共库浏览/下载不受生成限流。
- YAML校验器当前使用内置简化解析；存在PyYAML警告，但不影响人工与独立agent对结构的核验。

## 7. Verdict

- Status: passed
- Next: 交给用户整体review；用户确认后将roadmap从`draft`改为`active`。
