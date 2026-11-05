# 一万个回答 · AI文化造物黑客松 2026

杭州白马湖，2026年11月5日至8日。团队公开协作资料库：赛事信息、硬件资源、候选方案、技术调研与原型文件。

**当前状态：尚未确定最终作品。** 保留《拓》《蓝》《剪》，同时从团队共同的活动组织经验出发，探索创客参与和原创互动作品。方案中的目标、候选能力和已运行代码分别标注；生成了模型文件不等于完成了实体工艺验证。

## 从这里开始

| 内容 | 文档 |
|---|---|
| 赛事主题、作品要求、评分 | [赛事摘要](docs/event/guide.md) |
| 日程与官方资料中的待确认项 | [赛程](docs/event/schedule.md) |
| 现场设备、团队现有板子 | [硬件资源](docs/event/hardware.md) · [现场物料CSV](docs/event/hardware.csv) |
| 《拓》教学试拓装置 | [独立方案](docs/proposals/tuo.md) · [MVP与拔高分档](docs/proposals/tuo-stages.md) |
| 《蓝》花版设计／小样控染 | [独立方案](docs/proposals/lan.md) |
| 《剪》效果图转可制作剪纸 | [独立方案](docs/proposals/jian.md) |
| 三方案如何比较 | [比较与验证门槛](docs/proposals/comparison.md) |
| AI效果图如何转换为制作图纸 | [技术路线](docs/research/image-to-craft.md) |
| 从兴趣领域转向真实参与场景 | [痛点调研与新增候选](docs/research/pain-points-and-opportunities-2026-11-05.md) |
| 产品、论文和文化资料 | [参考链接](docs/research/references.md) |
| 已确定什么、还没确定什么 | [讨论记录](docs/project/decisions.md) |
| 剩余开发步骤与提交清单 | [开发计划](docs/project/roadmap.md) · [提交材料](docs/project/submission.md) |
| 已有拓板生成代码 | [拓板原型](prototypes/tuo/README.md) |

## 三个候选方向

- **拓**：先验证真实纸、墨、复制板能否稳定形成清晰试样，再考虑机械辅助上墨及图像反馈。
- **蓝**：分别研究“效果图转镂空花版”和“控制真实布料的小样染色”。两条路线尚未合并或选定。
- **剪**：把AI图案改成符合尺寸、连接与工具约束的制作方案。基础模拟和自动桥接已有先例，硬件价值仍需验证。

## 现有原型

`prototypes/tuo/make_stele.py` 可生成教学用阳刻板的预览与STL。优先使用50×50 mm单字试片，先做打印和手工试拓。

```bash
python -m pip install -r prototypes/tuo/requirements.txt
python prototypes/tuo/make_stele.py --sample-only
```

需要可用的中文字体；非Windows环境请显式提供 `--font /path/to/font.ttf`。字体文件不随仓库分发。

## 信息来源与维护

赛事摘要和物料来自2026-11-05读取的[赛事指南](https://ai-gongfang.feishu.cn/wiki/XBWpwiOC0i9SXbk1QRbcNePenTg)与[硬件一览表](https://ai-gongfang.feishu.cn/wiki/HfKTwaNeUiwKRgk28y8cguKqnFg)，以组委会最新通知为准。链接可能需要飞书访问权限，本仓库提供的是团队整理摘要。

仓库用于公开协作，团队当前讨论成员使用称呼：Desal、君君、Eagle、小羊。具体分工和最终方案待团队确认。

提交内容请遵循[协作约定](CONTRIBUTING.md)。
