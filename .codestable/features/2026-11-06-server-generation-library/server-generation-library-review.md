---
doc_type: feature-review
feature: 2026-11-06-server-generation-library
status: passed
reviewed: 2026-11-06
reviewer: subagent
round: 2
---

# server-generation-library 实现审查记录

## 范围

- 审查 `server/` 全部新增实现（契约 4.1/4.2/4.3、管理后台、providers、校验复用），对照已批准 design 与 roadmap 第 4 节契约。
- 两轮独立审查：任务1（生成服务与后台）规格与质量审查；任务2（公共库与测试套件）规格与测试质量审查。
- 全部发现经修复后复审通过；最终 43 个 pytest 全绿 + uvicorn 真实启动冒烟通过端到端闭环。

## 第一轮：任务1（契约 4.1/4.2 + 管理后台）

### 规格审查：通过

对照契约逐项核对：WAV 约束、错误码映射、候选隐私（音频即弃、识别文本私有且随过期删除）、幂等提交、任务状态机、后台口令认证与撤回均为内部操作——符合规格，无 blocking。

### 质量审查：发现 3 关键 + 2 重要，全部修复

**关键（已修复）：**

1. **共享连接跨线程事务交错**：早期路由共用单条 SQLite 连接，uvicorn 同步路由在线程池并发下会相互提交对方的事务。修复：`app.state.conn` 改为线程本地代理（`main.py: _ThreadLocalConn`），每线程独立连接，路由代码零改动。
2. **生成任务悬挂**：后台线程的未预期异常会使任务永远停在 pending。修复：`tasks_runner.run_generation` 全路径 try/except 兜底，任何异常把任务收敛为 failed，连状态回写失败也留下日志。
3. **过期候选仍可生成**：提交时只查存在性，任务执行期候选可能已过期却仍产出 buddy。修复：执行前二次校验 `expires_at`，过期立即 failed/candidate_expired。

**重要（已修复）：**

4. **幂等竞态**：并发提交同一 candidate_id 可能建出两条任务。修复：依赖 `candidate_id UNIQUE` 约束，撞 IntegrityError 时重读并返回已有任务。
5. **重试双开**：后台"重试"按钮在并发点击下可能为同一任务启动两个执行线程。修复：`reset_generation_for_retry` 用条件 UPDATE（仅 failed→pending 生效），rowcount=0 即放弃启动。

复审：通过。

## 第二轮：任务2（公共库 + 测试套件）

### 规格审查：通过（2 个弱点已强化）

- **限流只作用生成接口**：补测试验证限流交错下公共库浏览/下载不受 429 影响。
- **真并发提交**：补真实多线程并发提交同一候选的用例，验证唯一约束 + 幂等返回不产生重复任务。

### 测试质量审查：通过

- 43 个 pytest 全绿：契约错误码、分页稳定性、撤回 410、后台认证、校验一致性、并发与限流。
- 审查指出覆盖缺口后补齐：`content_not_supported`（识别文本含"不支持"）与过期候选生成（candidate_expired）用例；并收敛测试夹具避免跨用例连接复用。

## 残留（理论性次要，不阻塞）

1. IntegrityError 后重读已有任务存在微秒级窗口，极端并发下可能读到尚未提交的行；概率极低且重试语义不受损。
2. 线程本地连接无显式关闭路径，依赖进程退出回收；对演示规模无实际影响。

## Verdict

- Status: passed（复审通过，剩余残留为理论性次要）。
- 证据：`py -3.12 -m pytest server/tests -v` → 43 passed；uvicorn 冒烟（上传 WAV→201 候选→202 pending→succeeded+buddy_id→列表出现→manifest 过双校验→后台登录→撤回→410 且列表清空）。
