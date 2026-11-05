# 《拓》阳刻板生成原型

该目录保存已有的 `make_stele.py`，用于生成教学试拓板。代码从团队现有拓印工作目录整理，原工作文件未被改动。

## 功能范围

- 用中文字体生成竖排字形mask，进行加工目标下的笔画补粗。
- 保留内孔，将轮廓转换为带实物单位的浮雕。
- 通过布尔并集合并底板和浮雕，检查单一封闭实体。
- 输出PNG预览、STL和带诊断值的JSON清单。

默认优先使用50×50 mm“青”字试片。完整作业还包含“青取之於藍／而青於藍”两列，共九字，以及自拟展台文案。

## 环境与运行

```bash
python -m pip install -r prototypes/tuo/requirements.txt
python prototypes/tuo/make_stele.py --sample-only
python prototypes/tuo/make_stele.py --sample-only --preview
```

脚本首先尝试Windows系统中文字体。其他系统或需要指定字体时：

```bash
python prototypes/tuo/make_stele.py --sample-only --font /path/to/font.ttf
```

字体需由运行者提供；仓库不分发字体文件。不同字体、包版本与参数可能生成不同轮廓，切片前应检查当前输出。

## 文件

- [单字预览](preview/stele_sample_qing.png)。
- [单字STL](stl/stele_sample_qing.stl)。
- [STL生成清单](stl/manifest.json)，记录尺寸、体积、内孔与闭合检查。
- 只运行预览时，清单写入 `preview/preview_manifest.json`，不替代已生成STL清单。

## 验证边界

当前仓库样例通过脚本生成与网格检查，**没有据此确认实体打印或试拓成功**。笔画目标1.5 mm是参数，不保证所有细尖和间隙都满足加工要求；密集字可能合并，需要人工审预览和切片。

不要未经试片验证就排队打印多块整板。本目录不包含舵机、测力、OCR或端到端拓印固件。

关联：[拓方案](../../docs/proposals/tuo.md) · [硬件资源](../../docs/event/hardware.md)。
