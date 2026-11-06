# 服务器：生成服务与公共搭子库

本目录实现《当代妖怪收容所》的服务器侧，覆盖 roadmap 的三个子 feature 并附带一个内部管理后台：

- **voice-candidate-creation**（契约 4.1）：设备上传语音，返回候选搭子的名称、性格、玩法简介与主题标签。
- **confirmed-buddy-generation**（契约 4.2）：确认候选后异步生成具体规则包，校验通过后自动发布进公共库；已确认内容逐字不变。
- **public-buddy-library**（契约 4.3）：无登录公共搭子库，提供稳定分页列表、详情与 manifest 下载；发布不可变，支持内部撤回。

技术栈：FastAPI + SQLite（WAL），AI 能力通过可插拔 Provider 接入。默认 `stub` Provider 为确定性假数据，本地可跑通全链路；LLM 经 `SERVER_LLM_PROVIDER=remote` 切换为真实 OpenAI 兼容接口（`providers/openai_llm.py`，输出经 `generation/validate.py` 全量校验）。remote ASR 与 local ASR 仍为占位，待后续任务接入。

## 快速开始

在仓库根目录执行：

```bash
py -3.12 -m pip install -r server/requirements.txt
py -3.12 -m uvicorn server.app.main:app
```

默认监听 `http://127.0.0.1:8000`；管理后台在 `/admin`。

运行测试：

```bash
py -3.12 -m pytest server/tests -v
```

当前 64 个用例全部通过，另经 uvicorn 真实启动冒烟（上传 WAV → 候选 → 生成 → 公共库 → 后台撤回 → 410）。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SERVER_DB_PATH` | `server/data/server.db` | SQLite 文件路径 |
| `SERVER_PROVIDER` | `stub` | 批量 Provider 开关（向后兼容）：`stub` 或 `remote`；被下面两个单独开关覆盖 |
| `SERVER_ASR_PROVIDER` | 取 `SERVER_PROVIDER` | ASR 开关：`stub`（默认）\| `local`（占位，选择即报不可用）\| `remote`（仍为占位） |
| `SERVER_LLM_PROVIDER` | 取 `SERVER_PROVIDER` | LLM（候选 + 规则包生成）开关：`stub`（默认）\| `remote`（OpenAI 兼容真实接口） |
| `SERVER_RATE_LIMIT_PER_MIN` | `10` | 每 IP 每分钟限流阈值，只作用于候选与生成接口，不影响公共库浏览/下载 |
| `SERVER_ADMIN_TOKEN` | 空 | 管理后台口令；为空时 `/admin` 显示“未配置”提示页并拒绝操作 |
| `SERVER_BASE_URL` | `http://127.0.0.1:8000` | 对外基础 URL，用于详情响应中的 `manifest_url` |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容端点地址，可指向任意兼容服务 |
| `OPENAI_API_KEY` | 空 | OpenAI 兼容接口密钥，remote LLM 必需，缺失即 `503 generation_unavailable` |
| `OPENAI_MODEL` | `gpt-4o-mini` | 候选与规则包生成使用的模型名 |
| `OPENAI_TIMEOUT_SEC` | `60` | LLM 请求超时（秒）；网络/超时/5xx 均映射为 `generation_unavailable` |
| `ASR_REMOTE_URL` | 空 | remote ASR 服务地址（仍为占位） |

**凭证只走环境变量，不进仓库、不入代码、模板与日志。** remote LLM 的 prompt 要求输出 JSON 并经 `server/app/generation/validate.py` 全量校验，解析/校验失败会把错误反馈给模型重试（最多 2 次重试）；remote ASR 与 local ASR 尚未接入。

## API 摘要

权威契约见 `../.codestable/roadmap/bad-habit-buddy/bad-habit-buddy-roadmap.md` 第 4 节；以下为速览。所有接口以 `/api/v1` 为前缀，错误统一为 `{"error": {"code", "message", "request_id"}}`。

### 契约 4.1 语音创建候选

- `POST /api/v1/buddy-candidates`（multipart：`request_id`、`locale`、`audio`）→ `201`：`{candidate_id, content, expires_in_sec}`（候选默认 24 小时有效）。
- 音频当前只接受 **WAV**，≤30 秒、≤2MB。

### 契约 4.2 确认候选并异步生成

- `POST /api/v1/buddy-generations` `{request_id, candidate_id}` → `202` `{generation_id, status}`。
- `GET /api/v1/buddy-generations/{generation_id}` → `{generation_id, status, buddy_id, error_code}`。
- 同一 `candidate_id` 重复提交返回同一任务（已成功返回同一 `buddy_id`）；任务 `succeeded` 时 buddy 已在公共库可读；失败不入库，候选有效期内可重新提交。

### 契约 4.3 公共搭子库

- `GET /api/v1/buddies?cursor=&limit=` → `{items, next_cursor}`（`published_at` 降序 + `buddy_id` 降序稳定分页，cursor 绑定该顺序；`limit` ≤ 50）。
- `GET /api/v1/buddies/{buddy_id}` → 列表项字段 + `manifest_url`。
- `GET /api/v1/buddies/{buddy_id}/manifest` → BuddyManifest。
- 列表与详情只含公开字段，不含创造者原话、识别文本、原始录音或候选 ID。

### 错误码

| HTTP | code | 触发 |
|---|---|---|
| 400 | `invalid_audio` | 音频为空、非 WAV、超长或超大 |
| 400 | `invalid_cursor` | 分页游标无法解析 |
| 404 | `buddy_not_found` / `generation_not_found` | ID 不存在 |
| 410 | `buddy_withdrawn` | 搭子已被内部撤回 |
| 422 | `speech_unrecognized` | 未获得可用语义 |
| 422 | `content_not_supported` | 输入无法转成可玩主题 |
| 429 | `rate_limited` | 候选/生成接口触发限流 |
| 503 | `generation_unavailable` | ASR/LLM 服务不可用 |

## content_hash 定义

`content_hash` 是候选 content 四字段（`name` / `personality` / `gameplay_summary` / `theme_tags`）的规范化 JSON 的 SHA-256：

- UTF-8 编码；
- `sort_keys=True`；
- `separators=(",", ":")`（无多余空格）。

实现在 `server/app/util.py` 的 `content_hash_of`。**设备侧必须对齐此定义**，否则 manifest 校验与内容 diff 会不一致。

## 管理后台（/admin）

口令认证（cookie 或 `?token=`，口令只来自 `SERVER_ADMIN_TOKEN`）。四个页面：

- `/admin`：运行统计（计数器、限流阈值、Provider）。
- `/admin/candidates`：候选列表（只显示名称与标签，绝不显示识别原文）。
- `/admin/generations`：生成任务列表；failed 任务可重试（仅在仍为 failed 时重置为 pending，避免双开执行）。
- `/admin/buddies`：已发布搭子列表；支持**撤回**——撤回仅置标记，不提供公开或设备端撤回 API，不删除设备已有缓存。撤回是内部运维操作。

## 故障注入（stub Provider）

开发/联调时无需真实 AI 即可注入错误：

- 音频字节以 `__unavailable__` 开头 → `503 generation_unavailable`
- 音频字节以 `__silence__` 开头 → `422 speech_unrecognized`
- 识别文本含“不支持” → `422 content_not_supported`
- 候选 `name` 含“失败” → 任务 `failed / generation_failed`

也可用 monkeypatch 替换 `app.state.asr` / `app.state.generation` 注入任意故障（测试即如此）。

## 设备对接说明

- 音频编码当前固定为 WAV（≤30s、≤2MB），与设备基线验证结果对齐后再最终固定；若设备侧改用其他编码，需同步放宽 `_wav_duration_sec` 的解析逻辑。
- manifest 中的资源当前一律为 `builtin://feedback`（设备本地校验散列与大小，不下载）；服务器不下发远程资源 URL。
- 发布前校验复用 `shared/tools/validate_buddies.py` 并追加设备硬约束（节点 ≤16、迁移 ≤8/节点、动作 ≤6/列表、变量 ≤4、资源 ≤4、标签 ≤4、condition.right 必须为整数），保证“过服务器校验即可在 T5 真机运行”。
- 设备提交生成后应轮询任务状态；候选过期（`candidate_expired`）时重新录音创建，不尝试恢复私有识别文本。

## 隐私约束

- 原始音频只在内存中传给 ASR，识别后即弃，不落盘、不入日志、不作训练数据。
- 识别文本仅存 `candidates.private_text`，随候选过期删除，不出现在任何响应或后台页面。
- 公共库字段经测试审计，不含识别文本、原始录音、候选 ID 或创造者原话。
