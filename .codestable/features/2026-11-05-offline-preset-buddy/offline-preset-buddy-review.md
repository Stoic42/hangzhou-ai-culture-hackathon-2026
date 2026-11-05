---
doc_type: feature-review
feature: 2026-11-05-offline-preset-buddy
status: passed
reviewed: 2026-11-05
reviewer: subagent
round: 1
---

# offline-preset-buddy 代码审查报告

## 范围

- 审查`device/`与`shared/`新增实现，生成文件抽样，archive不参与。
- 对照已批准design与roadmap规则包v1、离线界面和双结局契约。
- 独立native subagent完成整体与行级审查；OCR未安装，不阻塞本轮。
- 主机34项测试、规则仿真、字体覆盖与T5固件构建均通过；用户确认真机基础功能正常。

## Findings

### blocking

- none。

### important

- 已修复：解析失败时跳过资源校验，避免失败路径读取已释放cJSON字符串。
- 已修复：迁移到结局节点时统一执行目标节点`on_enter`，使成功/失败画面和模拟器语义一致。
- 标签缓冲累计已使用`strlen`结果，避免`snprintf`截断后的size_t下溢。
- 真机反馈的滑动误点、事件黑洞、字体缺字、详情悬挂指针与圆屏越界均已分别定位根因并修复。

### nit

- none。

### suggestion

- none。

### learning

- LVGL输入需要同时处理滚动命中、手势阈值与释放时附带CLICKED，不能只监听单一事件。
- 删除屏幕时必须同时处理仍被定时器引用的子对象指针。

### praise

- 规则包使用白名单和双端校验，内置音频有size与SHA-256核对。
- 真机日志可追踪输入、变量、节点和结局，支持实际调试。

## Test And QA Focus

- 后续完整验收仍应逐只记录双结局与至少3局连续重开，不能用“基础功能正常”替代量化记录。
- `input_thresholds_init`依赖indev注册时机；当前位移fallback已由真机基础体验支持，后续可再核对手势阈值实际生效。
- 预设`content_hash`当前是全零占位，不作为内容完整性证明；音频资源散列是真实校验。

## Verdict

- Status: passed（代码审查通过，不等同完整feature acceptance）。
- Next: 提交当前可用原型；完整量化真机验收记录可在后续QA/acceptance补齐。
