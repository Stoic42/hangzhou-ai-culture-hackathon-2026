---
doc_type: feature-design
feature: 2026-11-07-real-ai-providers
requirement: null
roadmap: bad-habit-buddy
roadmap_item: voice-candidate-creation, confirmed-buddy-generation
status: approved
summary: 将服务器 AI 能力从 stub 升级为真实 Provider：DeepSeek（OpenAI 兼容）remote LLM 与 sherpa-onnx 本地 SenseVoice ASR，附部署资源自动补全脚本
tags: [fastapi, providers, openai, deepseek, sherpa-onnx, asr, llm, deployment]
---

# real-ai-providers 设计

## 0. 术语约定

- **Provider**：ASR 与 LLM（候选 + 规则包生成）两个可插拔接口，经 `SERVER_ASR_PROVIDER` / `SERVER_LLM_PROVIDER` 分别切换（默认取向后兼容的 `SERVER_PROVIDER`，均为 `stub`）。
- **候选 / 规则包 / 发布校验**：沿用 `2026-11-06-server-generation-library` 的定义。

## 1. 背景与范围

上一 feature 交付了完整服务器（契约 4.1/4.2/4.3 + 后台），但 ASR 与 LLM 均为 stub 假数据（remote 为占位抛 503）。本 feature 接通真实 AI：

- `SERVER_LLM_PROVIDER=remote`：`providers/openai_llm.py`，任意 OpenAI 兼容服务（实测 DeepSeek `deepseek-chat`），同时服务候选生成与规则包生成。
- `SERVER_ASR_PROVIDER=local`：`providers/local_asr.py`，sherpa-onnx 本地 SenseVoice-small，免费、离线、音频不出内网。

### 明确不做

- 不接 remote ASR（仍为占位）。
- 不改动既有契约、路由、DB 与后台行为；Provider 协议不变。
- 不把任何凭证、模型文件写入仓库。

## 2. 关键决策

1. **OpenAI 兼容 + JSON 模式**：DeepSeek 等平台均提供 OpenAI 兼容端点，一套 `openai_llm.py` 适配多家；请求开 `response_format=json_object`，prompt 要求输出 JSON；解析/校验失败把错误详情反馈给模型重试（最多 2 次），校验仍失败抛 `GenerationUnavailable`（503），绝不带病入库。
2. **白名单程序化生成**：规则包事件/动作白名单不再手写副本，而从 `shared/tools/validate_buddies.py` 的校验器常量程序化生成 prompt 白名单，杜绝两份白名单漂移（质量审查发现并修复）。
3. **sherpa-onnx 本地 SenseVoice**：免费、离线、CPU 可跑（int8 约 230MB），契合"音频不出内网"隐私约束；识别器首次请求惰性加载（双重检查锁），`num_threads=2` 适配 2C 机型；输出剥掉 `<|zh|>` 等元信息标签；非 16kHz 输入线性重采样兜底。
4. **可选依赖与请求期 503 降级**：sherpa-onnx 为可选依赖，缺装/模型目录未配齐/初始化失败均装配成功、请求期抛 `GenerationUnavailable`，服务照常启动，与 stub Provider 的故障注入语义一致。
5. **httpx 连接复用**：模块级共享 `httpx.Client`（限流信号量内串行使用 + 异常时强制关闭重建），避免每次请求重建连接（质量审查发现并修复）。
6. **资源自动补全脚本**：`server/tools/ensure_resources.py` 幂等引导——检查基础依赖（缺失自动 pip 安装）、local ASR 的 sherpa-onnx 与模型目录（缺失自动下载解压官方 release，stdlib urllib + tarfile，带进度）、remote LLM 的环境变量（只报缺失项），打印配置摘要，退出码 0=就绪 / 1=有缺失；不启动服务。
7. **配置拆分**：`SERVER_ASR_PROVIDER` / `SERVER_LLM_PROVIDER` 独立开关，保留 `SERVER_PROVIDER` 批量设置作向后兼容默认；`ASR_MODEL_DIR` 默认空串表示未配置（请求期 503）。

## 3. 隐私与凭证约束

- 凭证（`OPENAI_API_KEY`、`SERVER_ADMIN_TOKEN`）只走环境变量，不进仓库、代码、模板与日志；脚本与文档只引用变量名，不打印值。
- 原始音频只在内存中传给本地识别器后即弃；remote LLM 只收到识别文本（不含原始音频）；识别文本仍仅存 `candidates.private_text` 且随过期删除。

## 4. 验证

- 单测 82 passed + 1 skipped（1 个 local ASR 真机集成用例未配 `ASR_MODEL_DIR` 时自动跳过）；local ASR 用假 `sherpa_onnx` 模块形状注入测试。
- 真 key 联调（11-07）：真实中文语音 → 本地 SenseVoice 识别（首次加载约 2.6s、后续约 0.4s/次）→ DeepSeek `deepseek-chat` 生成候选 → 确认生成规则包 → 过发布校验入公共库，端到端闭环。
