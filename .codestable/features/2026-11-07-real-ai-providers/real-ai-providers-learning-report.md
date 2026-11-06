---
doc_type: learner-report
unit: .codestable/features/2026-11-07-real-ai-providers
branch: feat/real-ai-providers
base_ref: main
covered_head: 441b1b84cfa35936cb0c3ae36a1639ca3c99df9c
covered_diff: main...441b1b84cfa35936cb0c3ae36a1639ca3c99df9c
status: ready-to-merge
---

# real-ai-providers 学习报告

> 这份报告记录当前 execution worktree 在合并前必须保留的上下文和验证证据。

## 决策简报

### 目标
- 准备将 `feat/real-ai-providers` 合并回 `main`。

### 已决定
- 本 worktree 已进入 finish gate，学习报告覆盖当前 HEAD。

### 已排除
- 不自动 merge、rebase、删除 branch 或删除 worktree。

## 工作上下文

### 风险
- 合并前如果出现新 commit，必须重新生成学习报告。

### 相关文件
- .codestable/features/2026-11-07-real-ai-providers/2026-11-07-real-ai-providers-checklist.yaml
- .codestable/features/2026-11-07-real-ai-providers/2026-11-07-real-ai-providers-design.md
- .codestable/features/2026-11-07-real-ai-providers/real-ai-providers-review.md
- .codestable/roadmap/bad-habit-buddy/bad-habit-buddy-items.yaml
- .gitignore
- server/README.md
- server/app/admin/routes.py
- server/app/config.py
- server/app/generation/validate.py
- server/app/main.py
- server/app/providers/__init__.py
- server/app/providers/local_asr.py
- server/app/providers/openai_llm.py
- server/app/providers/remote.py
- server/requirements.txt
- server/tests/test_provider_local_asr.py
- server/tests/test_provider_openai.py
- server/tools/__init__.py
- server/tools/ensure_resources.py

### 剩余事项
- None

## 证据附录

### 验证证据
- py -3.12 -m pytest server/tests -q -> 82 passed + 1 skipped
- 真key联调: DeepSeek候选+规则包过发布校验入库; SenseVoice真实中文识别0.4s; 全栈链路跑通

## 1. 为什么做
- 记录 worktree finish 前的合并上下文，避免分支完成后被遗忘。

## 2. 改了什么
- .codestable/features/2026-11-07-real-ai-providers/2026-11-07-real-ai-providers-checklist.yaml
- .codestable/features/2026-11-07-real-ai-providers/2026-11-07-real-ai-providers-design.md
- .codestable/features/2026-11-07-real-ai-providers/real-ai-providers-review.md
- .codestable/roadmap/bad-habit-buddy/bad-habit-buddy-items.yaml
- .gitignore
- server/README.md
- server/app/admin/routes.py
- server/app/config.py
- server/app/generation/validate.py
- server/app/main.py
- server/app/providers/__init__.py
- server/app/providers/local_asr.py
- server/app/providers/openai_llm.py
- server/app/providers/remote.py
- server/requirements.txt
- server/tests/test_provider_local_asr.py
- server/tests/test_provider_openai.py
- server/tools/__init__.py
- server/tools/ensure_resources.py

## 3. 没改什么
- 未自动合并到 base branch。
- 未自动清理 worktree。

## 4. 关键决策
- `covered_head` 固定为 `441b1b84cfa35936cb0c3ae36a1639ca3c99df9c`；HEAD 变化后本报告失效。

## 5. Task agent review 发现与修复
- 见同 unit 的 implementation review 记录；finish gate 只验证 evidence 是否存在。

## 6. 验证证据
- py -3.12 -m pytest server/tests -q -> 82 passed + 1 skipped
- 真key联调: DeepSeek候选+规则包过发布校验入库; SenseVoice真实中文识别0.4s; 全栈链路跑通

## 7. 合并前注意事项
- 合并前确认 `feat/real-ai-providers` 当前 HEAD 仍为 `441b1b84cfa35936cb0c3ae36a1639ca3c99df9c`。

## 8. 后续 follow-up
- None
