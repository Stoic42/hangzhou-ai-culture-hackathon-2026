# Attention

本文件是 CodeStable 技能启动必读的项目注意事项入口。所有 CodeStable 子技能开始工作前必须读取它。

## 报告语言

CodeStable 所有落盘产出的正文用**中文**：plan / design、plan review / design-review、code review、QA、验收、issue（report / analysis / fix-note）、refactor、roadmap、goal、沉淀（compound）等所有人读报告都用中文表达。机器状态（YAML / JSON / `state.yaml` / frontmatter 字段）保持机读格式不翻译。如需改默认语言，改这一节。

## 项目碎片知识

<!-- cs-note managed: 用 cs-note 维护，新条目按下面分节追加 -->

### 编译与构建

### 运行与本地起服务

### 测试

### 命令与脚本陷阱

- Windows本机`python`为3.9，不能运行当前CodeStable校验器；使用`py -3.12 .codestable/tools/validate-yaml.py`。

### 路径与目录约定

- 当前唯一实施方向是《当代妖怪收容所》；`archive/initial-directions/`中的《拓》《蓝》《剪》暂无实施计划，不作为需求或代码输入。
- 当前内部roadmap标识保留`bad-habit-buddy`；新代码按roadmap分为`device/`、`server/`、`shared/`。

### 环境变量与凭证

### 其他
