---
doc_type: feature-review
feature: 2026-11-07-real-ai-providers
status: passed
reviewed: 2026-11-07
reviewer: subagent
round: 2
---

# real-ai-providers 实现审查记录

## 范围

- 审查 `providers/openai_llm.py`（remote LLM）、`providers/local_asr.py`（本地 ASR）、`app/config.py` 配置拆分与装配改动，对照已批准 design 与 roadmap 第 4 节契约。
- 两轮独立审查：任务1（LLM 适配器）规格与质量审查；任务2（本地 ASR）规格与质量审查。
- 全部发现经修复后复审通过；最终 82 个 pytest 通过（1 个真机集成用例跳过）。

## 任务1：remote LLM 适配器

- **规格审查**：通过。OpenAI 兼容端点 + JSON 模式、校验失败错误反馈重试（最多 2 次）、网络/超时/5xx 统一映射 503 `generation_unavailable`、缺 `OPENAI_API_KEY` 请求期 503，均符合设计；候选与规则包生成共用同一适配器，契约行为不变。
- **质量审查，2 项重要发现**：
  1. **白名单漂移**：prompt 内事件/动作白名单为手写副本，与 `shared/tools/validate_buddies.py` 常量存在漂移风险 → 已修复为从校验器常量程序化生成，测试断言逐项一致。
  2. **httpx 连接未复用**：每次请求新建 `httpx.Client` → 已修复为模块级共享客户端，配合限流信号量内串行使用保证线程安全，异常时强制关闭重建，双重检查。
- **次要发现**（均已修复复审通过）：重试提示语可能泄露内部字段名、超时参数边界说明不足等。

## 任务2：本地 ASR 适配器

- **规格审查**：通过。sherpa-onnx 可选依赖、模型目录未配齐/初始化失败请求期 503 降级、识别器惰性加载（双重检查锁）、元信息标签剥离、非 16kHz 重采样兜底，均符合设计与隐私约束（音频不出内网、不落盘）。
- **质量审查**：通过。次要发现均已修复：字节序真实检查（小端 `s16le` 断言）、可选依赖缺装路径补注释、假 `sherpa_onnx` 模块的测试形状说明。

## 真 key 联调记录（2026-11-07）

- DeepSeek（`deepseek-chat`，OpenAI 兼容端点）：候选生成与规则包生成均验证通过——真实语音候选确认后生成规则包，过 `generation/validate.py` 发布校验并自动发布入公共库。
- sherpa-onnx SenseVoice 本地识别：真实中文语音识别验证通过；识别器首次请求加载约 2.6s，后续每次识别约 0.4s。
- 端到端闭环：真实语音 → 本地 ASR → DeepSeek 候选 → 规则包 → 校验 → 公共库。

## 遗留

- remote ASR 仍为占位，待后续 feature 接入。
- 设备侧录音上传与真机联调待做（见 roadmap 相关条目 notes）。
