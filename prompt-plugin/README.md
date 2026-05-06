# Prompt Plugin

`prompt-plugin/` 是当前系统的 Prompt 资产层。

它负责两件事：

1. 用结构化 Markdown 保存不同场景下的提示词资产。
2. 把这些资产稳定地装配成最终的 system prompt。

它不负责两件事：

1. 不负责顶层意图判断。
2. 不负责在主链里再次本地选择 `module / subject / style / mode`。

当前真实主链是：

```text
用户输入 / 附件 / 历史
-> Router 单次模型规划
-> route + router_plan
-> model_plan_builder 校验并落地为 BranchStrategy
-> prompt-plugin 装配 Prompt 资产
-> renderer 产出 system prompt
-> responder 生成回答
```

这份文档要回答 4 个问题：

1. 这个板块到底怎么工作的。
2. 为什么要这样设计。
3. 这样设计的好处是什么。
4. 教育场景下，Prompt 应该怎么写才有效。

## 1. 先说结论

`prompt-plugin/` 不是“写一堆 prompt 文案”的目录，而是一个分层的教学策略资产系统。

它把一轮回答拆成 5 个层次：

1. `branch`
   决定走 `education / general_qa / casual_chat / clarify` 哪条大分支。
2. `module`
   决定当前这一轮要做什么教学动作，比如 `solve / check / explain / qa`。
3. `subject`
   决定当前学科的证据顺序、讲法和易错点，比如 `math / english / cs / physics`。
4. `style`
   决定这一轮讲多深、讲多快、讲多完整，比如 `hint_only / step_by_step / explain_careful / direct`。
5. `renderer`
   把以上资产和当前上下文拼成模型真正看到的 system prompt。

在当前架构里，Router 已经直接给出这轮要用哪个资产。`prompt-plugin/` 的职责不再是“选”，而是“把被选中的东西讲对、讲稳、讲一致”。

## 2. 为什么不再把选择逻辑塞进 Prompt 资产

旧思路的问题是：既想让 Router 判断意图，又想让 prompt runtime 再用一轮规则重判一次。

这种双重判断会带来 3 个问题：

1. 上下文容易断裂。
   Router 认为这是教育追问，runtime 又可能因为本地规则把它拐回通用答复。
2. 责任边界不清。
   回答效果差时，不知道是路由错了，还是 Prompt 写差了。
3. 维护成本高。
   一次改动要同时改模型 prompt、规则表、分支代码，最后还不一定一致。

现在的设计把职责收口了：

1. Router 负责“这一轮是什么意图，应该用什么 plan”。
2. `model_plan_builder` 负责“把 plan 变成可执行策略，并兜底非法 id”。
3. `prompt-plugin` 负责“把策略写成清晰、稳定、可维护的 system prompt”。

这样做的直接好处是：问题定位会简单很多。

- 选错 `module / subject / style`：先看 Router。
- 选对了但讲法不对：改 prompt 资产。
- system prompt 结构乱：改 renderer 或 contract。

## 3. 目录是怎么分层的

```text
prompt-plugin/
├── README.md
├── core/
│   ├── base/
│   │   ├── persona.md
│   │   └── multimodal_rules.md
│   ├── contracts/
│   │   ├── speech_only.md
│   │   ├── speech_brief.md
│   │   └── speech_ui_dual.md
│   ├── renderer/
│   │   ├── education_renderer.md
│   │   └── mode_renderer.md
│   └── router/
│       └── router_prompt.md
└── plugins/
    ├── education/
    │   ├── plugin.md
    │   └── modules/
    │       ├── solve/
    │       ├── check/
    │       ├── explain/
    │       ├── answer/
    │       ├── qa/
    │       └── drill/
    ├── general_qa/
    ├── casual_chat/
    └── clarify/
```

每层的职责如下。

### 3.1 `core/base`

放全局都适用的底层原则。

- `persona.md`
  定义助手的总体身份、基本行为边界。
- `multimodal_rules.md`
  定义图片、材料、附件这类跨分支通用的处理要求。

为什么这么拆：

- 这些原则不应该散落在每个学科文件里重复写。
- 一旦全局行为要调整，只改一处。

### 3.2 `core/contracts`

按输出形态补充约束。

- `speech_only.md`
- `speech_brief.md`
- `speech_ui_dual.md`

为什么要有 contract：

- 同样的教学内容，在语音场景和图文场景里，回答长度、句式、信息密度都不一样。
- 把“怎么说”里和交付渠道强相关的部分抽出来，能避免每个 module 都重复写一遍。

### 3.3 `core/renderer`

renderer 决定最终 system prompt 的组织顺序。

- `education_renderer.md`
  负责教育分支。
- `mode_renderer.md`
  负责非教育分支。

为什么 renderer 很关键：

- 资产写得再好，如果 system prompt 组织顺序错了，模型照样会跑偏。
- 教育场景尤其依赖顺序：先锁定对象，再判断诉求，再锁定回答边界，再给证据和讲法。

### 3.4 `core/router`

- `router_prompt.md`

这里描述的是 Router 的系统提示词，不是 responder 的提示词。

为什么放在 `prompt-plugin/` 里：

- 顶层 plan 选择和下游资产体系必须使用同一套概念名词。
- 比如 `module / subject / style / primary_scenario / primary_action / answer_boundary`，必须在上游和下游保持一致。

### 3.5 `plugins/*`

每个分支自己维护自己的内容资产。

- `education`
  用 `plugin -> module -> subject -> style`
- `general_qa / casual_chat / clarify`
  用 `plugin -> mode`

为什么教育要比其他分支更细：

- 教育回答不仅有“回答什么”，还有“按什么教学动作回答”“按什么学科证据回答”“讲到多深”。
- `mode` 一层对教育来说不够表达这些差异。

## 4. 当前运行时到底怎么装配 Prompt

代码上的真实链路是：

1. Router 输出 `route + router_plan`
2. `model_plan_builder.py` 读取 plan 里的 `module / subject / style`
3. `ComposedPromptRuntime` 加载对应 Markdown 资产
4. 运行时组出 `ResolvedPromptSpec`
5. `prompt_builder.py` 把 `base + contract + renderer + shared_context` 拼成 system prompt

可以理解成：

```text
Markdown Asset
-> Typed Spec
-> BranchStrategy
-> ResolvedPromptSpec
-> Final System Prompt
```

这里有两个实现细节很重要。

### 4.1 资产先变成结构化对象，再渲染

Markdown 不是直接拼给模型，而是先解析成：

- `PluginSpec`
- `ModuleSpec`
- `SubjectSpec`
- `StyleSpec`
- `ModeSpec`
- `ResolvedPromptSpec`

这样做的好处：

1. 写法更稳定。
   文件是内容资产，不是自由散文。
2. 程序可校验。
   缺字段、字段错名、id 不存在，能在运行时发现。
3. renderer 更简单。
   renderer 只消费结构化对象，不用从自由文本里猜字段。

### 4.2 system prompt 不再重复塞满历史原文

当前 responder 的原始历史问答会直接进入 `messages`。
因此 system prompt 里只保留短摘要和约束，不再把长历史全文重复展开。

这样做的好处：

1. 避免历史信息重复注入。
2. system prompt 更短、更稳。
3. 模型更容易把注意力放在“这轮该怎么答”，而不是消耗在重复上下文上。

## 5. 教育场景为什么要拆成 `plugin / module / subject / style`

教育回答最容易失败的地方，不是“语气不老师”，而是这 4 件事没分开：

1. 当前对象是什么。
2. 这一轮动作是什么。
3. 该按哪门学科的证据讲。
4. 该讲多深。

所以教育资产必须拆层。

### 5.1 `plugin.md` 解决“跨教育场景都该守什么底线”

`plugins/education/plugin.md` 应该只写跨教育场景都成立的规则。

例如：

- 当前对象优先级
- 新题与旧题如何区分
- 先判断学生诉求再回答
- 回答边界要服从 `hint_first / full_solution / direct_explain / targeted_answer`
- 多模态题先看当前素材

为什么这些规则要放在 plugin 层：

- 它们不属于某一门学科，也不属于某一种教学动作。
- 它们是整个教育分支都必须一致遵守的“教学操作系统”。

### 5.2 `module.md` 解决“这一轮要做什么动作”

`module` 是教育 Prompt 里最重要的一层。

它定义的是当前动作，而不是当前学科。

例如：

- `solve`
  当前重点是推进求解。
- `check`
  当前重点是判断对错、定位问题。
- `explain`
  当前重点是解释原因、方法、概念。
- `qa`
  当前重点是局部答疑或短答确认。
- `drill`
  当前重点是生成练习和巩固。

`module.md` 里最值得写清楚的是：

1. `Goal`
   这一类回答真正要完成什么。
2. `Applies To`
   适用在哪些场景。
3. `Response Structure`
   回答顺序是什么。
4. `Global Rules`
   这类动作最重要的教学边界是什么。
5. `Interaction Policy`
   用户追问时应该如何延续。
6. `Output Defaults`
   默认是语音优先还是图文双模、是否直接给答案、最多讲几层。

为什么 `module` 是核心：

- 教学失败很多时候不是学科错，而是动作错。
- 比如用户明明在验题，你却按讲题来答；或者用户只问局部原因，你却整题重讲。

### 5.3 `subject.md` 解决“按哪门学科的证据和讲法回答”

同样是 `solve`，数学、英语、计算机、物理的讲法完全不同。

`subject` 负责定义：

1. 这门学科的关注点
2. 证据优先级
3. 解释顺序
4. 常见误区
5. 这门学科最需要避免的错误迁移

为什么不把这些写在 `module`：

- `module` 解决的是动作。
- `subject` 解决的是领域证据。
- 把两者混在一起，会让文件越来越大，而且很难维护。

### 5.4 `style.md` 解决“讲多深、讲多快、讲多完整”

`style` 不该承载学科规则，它只管表达深度和呈现节奏。

例如：

- `hint_only`
  只推进下一步，不偷跑到整题终局。
- `step_by_step`
  分步讲清，每步有依据。
- `explain_careful`
  重点解释原因和局部卡点。
- `direct`
  结论优先，最小必要依据。

为什么要单独拆 style：

- 同一个 `solve.math`，有时只该给提示，有时需要完整展开。
- 如果不拆 style，就会被迫在同一个 subject 或 module 里写互相冲突的指令。

## 6. 教育 Prompt 到底应该怎么写

教育 Prompt 不应该写成“老师口吻大全”，而应该写成“教学执行规范”。

最有效的写法通常遵守下面 5 条。

### 6.1 先写对象，不先写口号

先写清：

- 当前在处理什么对象
- 新对象和旧对象怎么区分
- 当前对象优先级是什么

因为真实失败里，最常见的问题不是不会讲，而是讲错对象。

### 6.2 先写动作顺序，不先写漂亮措辞

一个好 module，应该先让模型知道：

1. 先确认当前对象
2. 再判断学生诉求
3. 再判断回答边界
4. 再给证据、方法或下一步

这比堆很多“耐心、鼓励、温柔、像老师”更有用。

### 6.3 学科文件要写证据顺序，不只写知识点名称

坏写法：

- “数学要严谨”
- “英语要注意语法”

好写法：

- 数学先判断所求、已知、方法入口，再解释变形依据
- 英语先锁定句法结构，再定位考点，再解释选项差异

模型最需要的是“怎么判断”，不是“这门学科很重要”。

### 6.4 style 文件要写边界，不要写重复内容

style 最有价值的是约束：

- 这一轮能不能直接给终局
- 这一轮能不能跨出当前小问
- 每次回答最多推进几步
- 应该先给结论还是先给依据

不要在 style 里重写一遍 module 和 subject 已经写过的东西。

### 6.5 renderer 要把执行顺序写死

教育 renderer 的价值不是“把字段打印出来”，而是明确告诉模型：

1. 先锁定对象
2. 再判断诉求
3. 再锁定边界
4. 再按模块、学科和风格回答
5. 看不清就明确说看不清

这能显著降低：

- 串题
- 跑题
- 局部问题被扩成整节课
- 素材没看清却硬答

## 7. 为什么还保留 `Module Selection Rules` 这类表格

当前主链已经不靠这些表格做热路径选择，但它们仍然有价值。

价值在于：

1. 它们是资产边界的显式说明。
   让人一眼看懂某个 `module / subject / style` 设计给什么场景用。
2. 它们是 Router 语义的对照表。
   方便保证上游的 plan 命名和下游资产理解一致。
3. 它们仍可作为辅助解析能力和离线检查依据。

所以现在的理解应该是：

- 它们主要是“说明文档和语义边界”
- 不是当前 turn 主链里的第二套裁决器

## 8. 这样设计到底能带来什么效果

如果这个目录写得好，效果不只是“Prompt 更整洁”，而是会直接改善回答质量。

### 8.1 更不容易串题

因为 plugin 和 renderer 都明确强调：

- 当前对象优先
- 新附件默认新对象
- 除非用户明确回指，否则不把上一题带进来

### 8.2 更不容易动作错位

因为 `module` 单独建模了：

- 求解
- 验题
- 解释
- 局部答疑
- 练习生成

这会减少“用户在验题，你却在重讲整题”这类错误。

### 8.3 更不容易学科迁移错误

因为 `subject` 独立定义了学科证据顺序和易错点。

这会减少：

- 把英语题讲成阅读理解背景题
- 把接口识别题讲成数学题
- 把历史材料题讲成通用概念答疑

### 8.4 更容易控制回答深浅

因为 `style` 和 `answer_boundary` 一起工作。

这会减少：

- 用户只想要提示，你却直接给完整答案
- 用户明明要完整过程，你却只给一句判断

### 8.5 更容易维护

你可以更有针对性地改问题：

- 教学目标不对：改 `module.md`
- 学科讲法不对：改 `subjects/*.md`
- 讲太深或太浅：改 `styles/*.md`
- 全教育分支都容易串题：改 `plugins/education/plugin.md`
- system prompt 顺序不对：改 `core/renderer/education_renderer.md`

## 9. 什么时候该改哪一层

这是最实用的排障地图。

| 现象 | 优先修改位置 |
| --- | --- |
| 回答串到上一题 | `plugins/education/plugin.md`、`core/renderer/education_renderer.md` |
| 用户在验题却被当成讲题 | Router prompt、上游 plan；其次看 `check/module.md` |
| 学科判断正确，但讲法像另一门学科 | 对应 `subjects/*.md` |
| 用户只要提示，却给了完整答案 | 对应 `styles/*.md`，以及 `answer_boundary` 相关描述 |
| 回答像在背 prompt，结构混乱 | `core/renderer/*.md` |
| 语音场景太长、太绕、不适合听 | `core/contracts/*.md` |
| 教育分支整体价值观不统一 | `plugins/education/plugin.md` |

## 10. 写资产时的约束

为了让这一层长期可维护，建议坚持下面这些约束。

### 10.1 不把 Router 逻辑复制进资产里

资产里可以描述边界语义，但不要把完整路由逻辑再写一遍。

原因：

- 顶层判断已经由 Router 负责。
- 再复制一份只会制造分叉。

### 10.2 不把所有规则都写在 plugin 层

plugin 只写跨教育分支通用的底线。

不要把：

- 学科讲法
- 风格差异
- 某个模块独有的教学动作

全部挤到 `plugin.md` 里。

### 10.3 不在 style 里塞学科知识

style 只管深度、节奏和边界。

如果 style 里出现大量“数学应该如何讲”“英语应该如何讲”，说明职责已经串了。

### 10.4 不写空泛价值观

像下面这种低信息句子应该尽量少：

- “要像老师一样耐心”
- “要认真讲解”
- “要循循善诱”

更好的写法是可执行规则：

- “先判断学生当前卡在哪一步，再决定讲多深”
- “提示型回答只推进下一步，不给整题终局”
- “如果当前轮出现新图，默认按新对象处理”

## 11. 一句话总结

`prompt-plugin/` 的目标不是“把 Prompt 写得更长”，而是把教育回答拆成可维护的策略资产：

- plugin 决定通用教学底线
- module 决定这一轮动作
- subject 决定学科证据和讲法
- style 决定回答深浅
- renderer 决定 system prompt 的执行顺序
- contract 决定交付形态约束

这样做的核心收益是：

1. 回答更稳定。
2. 串题和跑题更少。
3. 教学动作更清楚。
4. 学科讲法更像对应学科。
5. 后续优化时知道该改哪里，而不是只能盲调整段 Prompt。
