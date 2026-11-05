---
doc_type: feature-design
feature: 2026-11-06-server-generation-library
requirement: null
roadmap: bad-habit-buddy
roadmap_item: voice-candidate-creation, confirmed-buddy-generation, public-buddy-library
status: approved
summary: 实现契约4.1语音候选、4.2异步生成与自动发布、4.3公共搭子库的服务器侧，附口令保护的管理后台
tags: [fastapi, sqlite, server, generation, public-library]
---

# server-generation-library 设计

## 0. 术语约定

- **候选 / 生成任务 / 搭子 / manifest**：严格使用 `.codestable/requirements/CONTEXT.md` 与 roadmap 第 4 节定义。
- **content 四字段**：`name / personality / gameplay_summary / theme_tags`，候选与发布之间逐字不变。
- **Provider**：ASR（语音转写）与生成（候选/规则包）两个可插拔接口；默认 stub 为确定性假数据。

## 1. 背景与范围

落实 roadmap 第 4.1/4.2/4.3 节网络契约的服务器侧，使 T5 设备可"语音创建候选 → 确认生成 → 公共库分发"，并给运维一个口令保护的内部后台（统计、查看、撤回、失败重试）。

### 明确不做

- 不实现设备侧缓存与下载（device-library-cache）、真机联机验证（three-device-demo-hardening）。
- 不实现真实 ASR/LLM 接入（remote Provider 为占位，抛 503）。
- 不做账号、私人库、搭子编辑、公开撤回 API。
- 不保存原始音频；识别文本随候选过期删除。

### 关键决策

1. **FastAPI + SQLite**：单机演示规模（三设备 + 后台），无需外部服务即可完整运行；WAL + 每线程连接支撑并发请求；SQLite 文件即全部状态，部署与备份零成本。
2. **stub + 可插拔 Provider**：比赛现场不依赖外部 AI 账号即可演示全链路；stub 输出确定性（按输入散列取主题），支持前缀/关键词故障注入；真实服务经 `SERVER_PROVIDER=remote` 切换，实现 `providers/base.py` 协议即可。
3. **校验器复用 + 设备收紧**：发布前校验直接加载 `shared/tools/validate_buddies.py`（与设备共用同一白名单语义），再追加设备硬约束（节点 ≤16、迁移 ≤8/节点、动作 ≤6/列表、变量 ≤4、资源 ≤4、标签 ≤4、condition.right 必须为整数），保证"过服务器校验即可在 T5 运行"。
4. **content_hash 定义**：sha256 于 content 四字段的规范化 JSON（UTF-8、`sort_keys=True`、`separators=(",", ":")`），实现在 `server/app/util.py: content_hash_of`，设备侧必须对齐。
5. **线程本地连接**：uvicorn 同步路由跑在线程池，共享单连接会跨线程事务交错；`app.state.conn` 为线程本地代理，每线程独立 SQLite 连接，路由代码零改动。
6. **幂等与同事务发布**：`candidate_id` 唯一约束保证同候选只建一个任务（并发撞约束时返回已有任务）；发布与任务 `succeeded` 状态顺序提交于同一连接，任务成功时 buddy 必然已可读；后台重试用条件 UPDATE（仅 failed→pending）防双开。
7. **隐私约束**：原始音频只在内存中传给 ASR 后删除；识别文本仅存 `candidates.private_text` 且随过期删除；候选页面与所有响应均不含识别原文；公共库不含创造者原话、识别文本、录音、候选 ID。
8. **后台设计**：四页面（统计/候选/任务/搭子），口令只来自 `SERVER_ADMIN_TOKEN`（空则提示未配置），cookie + `?token=` 双通道，`secrets.compare_digest` 防时序；撤回仅置 `withdrawn=1` 标记，公开 API 对已撤回搭子返回 410，不影响设备缓存。

## 2. 模块划分

```text
server/
├── app/
│   ├── main.py        应用工厂：配置、建库、Provider、限流、路由装配
│   ├── config.py      环境变量 Settings（凭证只走环境变量）
│   ├── db.py          SQLite 层：candidates / generations / buddies / counters
│   ├── util.py        ID 生成、content_hash_of、滑动窗口限流器
│   ├── errors.py      统一 {"error": {code, message, request_id}} 响应
│   ├── resources.py   builtin://feedback 内置资源登记
│   ├── generation/
│   │   ├── candidates.py  契约4.1：WAV 校验→ASR→候选→入库（音频即弃）
│   │   ├── tasks.py       契约4.2：提交（幂等）/查询生成任务
│   │   ├── tasks_runner.py 后台线程：生成→校验→发布→回写状态（异常必收敛）
│   │   └── validate.py    shared 校验器 + 设备硬约束
│   ├── library/
│   │   ├── publish.py     manifest 组装 + 全量校验 + 入库（失败不入库）
│   │   ├── routes.py      契约4.3：列表（cursor 分页）/详情/manifest
│   │   └── withdraw.py    内部撤回（仅置标记）
│   ├── admin/routes.py    后台四页面 + 撤回/重试（口令认证）
│   └── providers/
│       ├── base.py    ASRProvider / GenerationProvider 协议与异常
│       ├── stub.py    确定性假数据 + 故障注入
│       └── remote.py  真实服务占位（未配置抛 503）
└── tests/             43 个 pytest（契约、后台、校验一致性、并发/限流）
```

## 3. 关键场景与验收契约

1. 上传合法 WAV → 201 返回候选四字段，不含识别文本；`__silence__`/`__unavailable__`/超大超长音频各自命中 422/503/400。
2. 提交生成 → 202 pending；轮询 → succeeded + buddy_id；同一 candidate 重复提交返回同一任务与 buddy。
3. 候选过期/不存在 → 任务 failed（candidate_expired）；name 含"失败" → failed（generation_failed）；不入库。
4. 列表分页顺序稳定，撤回后列表清空、详情/manifest 返回 410 buddy_withdrawn。
5. manifest 通过 shared 与设备收紧双校验；content_hash 与设备定义一致。
6. 后台未带口令显示登录页；口令为空显示"未配置"页；登录后可撤回与重试。
7. 限流只作用于候选与生成接口；并发提交同一候选不产生重复任务。

DoD 命令：`py -3.12 -m pytest server/tests -v`（43 passed）；uvicorn 冒烟（真实启动跑通 1—6 场景）。

## 4. 与项目级架构文档的关系

本 feature 落实 ADR 001 中"服务器生成 + 公共库分发"的服务器半边，不改变契约；音频编码、包大小等参数在设备基线验证后回写 roadmap attention/compound。
