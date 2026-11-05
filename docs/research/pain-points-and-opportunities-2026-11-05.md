# 痛点调研与新增候选：从看作品到动手创造

日期：2026-11-05。状态：探索记录，未定题、未开发、未开展本队用户实验。

## 本轮范围与判断

赛事允许动漫、游戏、原创IP及公共文化等切口，不必只选传统技艺。团队确认共同经验是组织黑客松；因此可以优先接触真实参与者、导师和展台观众，研究参与、创造与合作的过程。共同组织经验不等于所有成员都掌握嵌入式开发，也不等于作品必须做成活动管理系统。

原有《拓》《蓝》《剪》保留。拼豆、重度谷子收藏等消费爱好路线暂不优先，原因是当前团队缺少持续使用经验；不是断言这些领域没有需求。以下优先级为助手建议，尚未获团队选择。

## 已有证据与不能直接推出的结论

| 观察 | 来源与阅读范围 | 对选题的含义及限制 |
|---|---|---|
| 科学黑客松新手可能需要超出偶发答疑的支持；项目自主性、可达成目标和学习导向支持值得关注 | [Nolte等，CSCW 2020原文](https://hackathon-planning-kit.org/files/Nolte-CSCW-2020.pdf)，研究一个24小时活动中的3个学生团队 | 支持研究新手如何开始并完成作品；不能据此证明本队装置能替代导师，或所有活动都有同等需求 |
| 求助排队及导师分配已有专门工具 | [HELPq官方仓库](https://github.com/ehzhang/HELPq)，README | 普通导师工单不是新空白；先了解现成流程是否已够用 |
| 创客空间的预约、成员、培训权限和机器接入已有产品 | [Fabman官网](https://fabman.io/) | 不宜把完整空间管理后台当成本轮创新点；官网能力未实测 |
| 公共交互研究区分路过、注意、轻微尝试、直接操作等阶段 | [Audience Funnel作者说明，2011](https://magicalmirrors2006.wordpress.com/2011/08/19/audience-funnel/)，观察柏林公共显示屏前660名路人 | 可以据此设计“让观众开始操作”的实验；迁移到黑客松展台是设计推断，不是论文验证结果 |
| 低门槛图形化硬件编程、模拟器与刷写早已有完整工具链 | [Microsoft MakeCode for micro:bit官方说明](https://makecode.microbit.org/about) | 自然语言控制硬件不能只靠“比写代码简单”宣称创新，需要和现有积木编程、预设模板比较 |

以上为定性研究、特定场景观察及产品说明，未形成市场规模、需求普遍性或付费意愿结论。本轮没有声称访谈过现场用户。

## 候选A：几分钟做出一个会回应的小物件

**体验假设**：观众用纸盒或纸片做一个原创角色，说出希望它如何回应，再亲手测试和修改它的行为。作品主题可以是“每个人都能创造自己的互动角色”。具体角色、材料与故事仍待设计，不能只用“创客文化”四字代替体验内容。

示例：“按一下点头，连续按三次就躲起来，过五秒再探头。”这句描述必须被转换为设备实际可执行的规则，而非只生成角色图片、台词或播放固定动画。

- **最小实体**：一个已接好的按键、一个舵机、一个简单纸质外壳。具体控制板、驱动和电源需先验证；不要求所有现有板子一起使用。
- **AI任务**：把意图转成有限的事件、状态、计时及动作参数；把含糊或超出支持范围的要求改写成可执行选项；解释行为为何发生。
- **确定性执行**：固定程序校验规则后运行，限制动作范围并提供复位。第一版不接受任意外设、自由接线或任意生成固件。
- **树莓派5候选职责**：界面、模型API调用、规则校验和运行记录；T5或已有控制板承担按键读取与舵机动作。也可先以电脑完成上层功能，不依赖树莓派部署才开始验证。
- **拔高**：实测输入没有触发动作时，系统根据事件记录定位是条件未满足还是动作未执行；新增一种传感器前单独验收。摄像头识别任意物体不列入第一版。

**先做的验证**：邀请3名真实零基础参与者，观察他们能否在目标时间5分钟内完成一次设定、触发和修改，并说清楚一条因果规则；该人数和时长是试验目标，不是现有结果。对照预设模板：如果模板同样容易且足以表达需求，AI不是本体验的核心。若大家只想看现成机器人，纸盒创作也可能不成立。

**当前判断**：最值得做一次小实验的新方向。它把原创角色、动手制作和实际行为联系起来；主要风险是退化为普通语音遥控玩具，或AI生成规则没有比已有工具更好用。

## 候选B：能带观众实际玩一次的作品演示台

**体验假设**：观众面对展品，不知道第一步能做什么。演示台根据作品真实状态给出一个可完成的操作，确认操作结果，再解释发生了什么。固定脚本、屏幕提示或作者说明可能已经够用，需要比较。

- **最小实体**：一个真实按键—执行器作品，提供`idle / await_input / running / error`等有限状态；不能只连一个无关聊天机器人。
- **AI任务**：把同一实际状态解释给不同观众、回答当前步骤问题；关键操作和复位走固定程序。
- **硬件关系**：读取真展品的输入及完成信号，按允许的动作运行一次；动作失败时不能按成功继续讲解。
- **文化内容**：取决于连接的作品及其互动设计。通用展台助手的文化内核较弱，不能因为服务文博会就自动视为文化作品。
- **验证**：比较固定提示与状态感知引导下，观众开始动手、完成一次体验以及作者需要介入的情况。反复讲解负担是待验证假设，本轮来源未证明其普遍性。

**当前判断**：有机会落地为活动工具，作为本场独立参赛作品需要补足内容表达。候选A的引导流程可以借鉴此思路，但不同时开发一个通用展台平台。

## 候选C：从想做什么，到领到一套可用零件

**体验假设**：新手知道想做什么，却不知道现有元件在哪、是否兼容及是否可借。先做3个有标签的盒子和有限库存清单；根据任务选出预先验证兼容的一套材料，点亮对应盒子，取还由扫码或人工确认。

- **AI任务**：在已核对清单及兼容组合内提出方案，材料不足时给替代选项；不能凭空推断模块接口和电压。
- **硬件关系**：实际库存与位置反馈、盒子指示；第一版不做从摄像头自动辨识所有零件。
- **热敏打印机的可能作用**：输出小型领料/归还清单，纸幅与信息量匹配；它在这里不需要替代工艺用纸。
- **验证**：与清晰纸质清单、人工领料及已有库存工具比较。若只节省一次点击，增设联网硬件价值不足。

**当前判断**：共享使用和修理文化可作为背景，但管理属性重、文化表达弱，暂不优先于候选A或能产生真实成品的《拓》。不能仅凭“我们办活动”就把它升级为最佳选题。

## 原有领域调研怎样影响取舍

| 领域 | 搜索发现 | 当前处理 |
|---|---|---|
| 拼豆 | [玩家讨论](https://www.reddit.com/r/PerlerBeads/comments/1vq3ldr/random_question_about_patterns/)涉及计数，[工具作者及评论](https://www.reddit.com/r/beadsprites/comments/1wl2525/my_free_bead_pattern_tool_can_now_use_only_the/)涉及制作进度；B站[自动拼豆机视频](https://www.bilibili.com/video/BV1xZFyzHE8i)只核对到标题、作者、日期等元数据 | 团队使用经验不匹配，降优先；不转述视频标题中的“全网第一”为事实，也未验证机器性能 |
| 谷子/手办展示 | 拍摄、布置和保存是不同任务；反光有时是想要的效果 | 没有可靠依据把“去反光”设成团队首选；小红书登录受限，不能声称已完成该站用户调研 |
| Cos拍照 | [玩家讨论](https://www.reddit.com/r/CosplayHelp/comments/1v1c70p/posing_in_character_or_no/)提到现场摆姿不自然；[PoseAI](https://getposeai.com/)等已宣传AI姿势指导 | 不把手机已有能力搬进盒子就算硬件创新；当前不优先 |
| 漫展社交 | [独自参展讨论](https://www.reddit.com/r/animecons/comments/1x1t1rd/what_to_do_on_convention_alone/)中，有人想结识朋友，也有人喜欢独自逛展 | 不把独行自动诊断为痛点；本轮未确认本队对这一场景的持续投入 |
| 实体桌游/解谜 | [Teburu](https://www.teburu.com/ecosystem/smart-board/)已有智能桌游硬件，[Escape Room AI](https://www.elyanlabs.ai/escape-room-ai.html)也有实体密室AI方案说明 | 可保留原创合作体验；不能宣称AI实体游戏首创，也未确认成员爱好 |
| 方言 | [2025温州话识别论文](https://aclanthology.org/2025.loresmt-1.5/)显示有专门数据与模型研究 | 不从家乡推定成员方言能力，不为语音板硬拼方言题目 |
| 工艺学习 | [Reshaping Craft Learning](https://studioforcreativeinquiry.org/wp-content/uploads/2025/07/Reshaping-craft-learning.pdf)讨论陶艺学习的身体动作与反馈 | AI解释不等于掌握手感；《拓》《蓝》《剪》仍以真实材料试验判断 |

## 下一步选择方式

优先比较两个能实际试验的方向：候选A的一次零基础造物体验，以及《拓》的一次手工清晰成样。记录真实完成过程后再投入机械或交互开发。不预报评委得分，不因新想法出现而宣布原方案失效。

## 检索台账

本轮采用smart-search检索流程，记录实际调用、无效结果及访问限制。

| 渠道 | 查询或任务 | 实际调用 | 结果/限制 |
|---|---|---:|---|
| OpenCLI / 豆包 | ACG、手工与方言等六领域痛点、既有方案及原始线索（任务摘要） | ask 1次 | 返回内容无有效调研结果，已弃用，不重试 |
| OpenCLI / 小红书 | `谷子 拍照 反光` | search 1次 | AUTH_REQUIRED，停止访问，未绕过登录 |
| OpenCLI / B站 | `拼豆 识别 错豆`；读取`BV1xZFyzHE8i`元数据 | search 1次 + read 1次 | 搜索提供先例线索，读取不等于看完视频或测试硬件；达到本站本题调用上限，不继续扩搜 |
| 网页搜索 | 以下36条查询 | 36条查询，分9批 | 另读取论文、官网与公开讨论；少数链接403或缓存失败，未访问全文的资料不作为核心结论依据 |

网页查询词（保留原始查询，包含部分结果较少或未用于结论的检索）：

```text
site.reddit.com/r/PerlerBeads pattern losing count wrong colors beads
site.reddit.com/r/AnimeFigures display lighting fading dust acrylic stand
site.reddit.com/r/cosplay convention photos posing alone camera
site.reddit.com anime convention trading freebies social anxiety
site.reddit.com/r/AnimeFigures "dust" "lighting"
谷子 吧唧 拍照 反光 收纳 痛点 玩家
site.reddit.com/r/cosplay "posing" "awkward"
site.reddit.com anime convention "trading" "anxiety"
site.reddit.com/r/AnimeCons "alone" "friends"
site.reddit.com/r/itabag "layout" "pins"
site.reddit.com/r/AnimeFigures "photograph" "reflection"
site.reddit.com/r/cosplayprops "electronics" "LED" "help"
"谷子" "反光" 拍照
"perler" "camera" "detect" beads pattern
"dialect" "speech recognition" "Wenzhou" dataset
"craft" "novice" "tacit knowledge" AI user study
"拼豆" "相机" "识别"
"perler" "opencv"
AI posing assistant live camera pose guidance app
site.orbitvu.com automatic product photography turntable reflective jewelry
site.reddit.com/r/DMAcademy "sound effects" "manage"
site.reddit.com/r/boardgames "teaching" "rules" "new players"
site.reddit.com/r/arduino "breadboard" "debugging" "beginner"
hackathon team formation challenges participants study asking help
site.teburu.net board game rules bookkeeping sensors
"AI" "physical" "escape room" "game master"
"site:reddit.com/r/DMAcademy" "soundboard" "distracting"
"Wenzhou Dialect Speech to Mandarin Text Conversion" site:aclanthology.org
hackathon hardware shared equipment borrowing components problems study
maker faire exhibitors repeated explanation visitors interactive prototype study
hackathon mentor help seeking novice challenges interview study
makerspace tool checkout inventory missing tools study
site.fabman.io bridge makerspace access tools
hackathon mentor help queue github helpq
"audience funnel" interactive displays study
"How to Support Newcomers in Scientific Hackathons" pdf nolte
```

关联：[方案比较](../proposals/comparison.md) · [硬件资源](../event/hardware.md) · [讨论记录](../project/decisions.md)。
