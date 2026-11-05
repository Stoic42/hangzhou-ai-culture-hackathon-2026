---
doc_type: feature-design-review
feature: 2026-11-05-offline-preset-buddy
status: passed
reviewed: 2026-11-05
round: 3
---

# offline-preset-buddy feature design 审查报告

## 1. Scope And Inputs

- Design: `.codestable/features/2026-11-05-offline-preset-buddy/offline-preset-buddy-design.md`
- Checklist: 同目录`offline-preset-buddy-checklist.yaml`
- Roadmap: `bad-habit-buddy`主文档第3/4节（含4.6界面契约）与items.yaml
- Related docs: CONTEXT.md、ADR 001、T5官方资料调研结果
- Code facts checked: 当前无搭子代码；COM4/COM8为本次机器识别到的CH342双串口。

### Independent Review

- Status: completed
- Detection: native-agent
- Provider / agent: 三轮独立general-purpose agent
- Raw output: 第一轮发现资源、枚举、计时与命令问题；第二轮确认修复；第三轮审查三页面导航并指出详情内容白名单。
- Merge policy: 已逐条核验并同步design/checklist/roadmap；详情页内容白名单已补齐。
- Gate effect: 无未解决blocking/important。

## 2. Design Summary

- Goal: 三只玩法不同预设搭子在T5离线运行，具有主界面、详情、游戏和生成页离线状态，支持双结局与重开重置。
- Key contracts: BuddyManifest、GameSession、整区手势、白名单状态机、builtin资源、三顶级页面导航。
- Steps: 6步，真机spike优先，随后共享校验、运行时与界面、状态机、表演和收口。
- Checks: 9条，覆盖名词、编排、导航、详情内容、错误、挂载、范围和真机场景。
- Baseline / validation: 主机校验无第三方依赖；T5使用TuyaOpen构建/烧录，实际端口写入证据。

## 3. Findings

### blocking

- none unresolved。内置`builtin://`资源、完整动画枚举和页面边界已明确。

### important

- none unresolved。计时优先、默认超时结局、端口可移植性、双结局/连续重开口径及详情内容白名单均已修正。

### nit

- none

### suggestion

- none

### learning

- 内置资源和远程资源共享散列/大小契约，但获取方式分别定义。
- 双结局路径验证与连续重开稳定性是两类证据。
- 离线feature可以实现页面骨架，但在线下载与生成行为必须留给后续feature验收。

### praise

- 真机spike在服务器开发之前，符合最弱依赖优先。
- 主界面手势、详情、固定游戏返回和生成状态均有明确归属，不与游戏手势冲突。

## 4. User Review Focus

- 用户需要确认：三顶级页面、主界面滑动/点按/长按、详情白名单、固定返回、生成成功自动进入游戏；当前feature只实现离线路径。
- implement需要遵守：先真机工具链，再规则校验、界面与状态机；不改归档。
- QA/acceptance需要复核：每只双结局各1次、另做至少3局连续重开、断网、音频和导航证据。

## 5. Evidence Confidence Ledger

| Check | Verdict | Evidence Class | Basis | Follow-up |
|---|---|---|---|---|
| Acceptance Coverage Matrix | pass | E | 核心场景映射到S1—S6与证据 | 真机执行 |
| DoD Contract | pass | E | 五类gate与三条命令齐全 | 实现后重跑 |
| Steps and checks traceability | pass | E | 6步、9条checks回溯design | none |
| Roadmap contract compliance | pass | E/C | 资源、枚举、计时和界面符合4.4/4.6 | 不在feature内私改 |
| Validation and artifacts | pass | E | 主机命令、TuyaOpen命令与真机材料明确 | SDK安装后验证 |

Summary: E=5, C=1（部分检查同时含C）, H-only core checks=none。

## 6. Residual Risk

- 本机尚未安装完整TuyaOpen工具链，官方SDK构建和真机外设仍未实际验证。
- 微雪Wiki对触摸芯片存在CST9217/FT3168两种表述，以官方Demo和原理图为准。
- YAML校验通过但使用内置简化解析器，PyYAML警告已记录。

## 7. Verdict

- Status: passed
- Next: 交给用户整体review；确认后将design改为approved并开始实现。
