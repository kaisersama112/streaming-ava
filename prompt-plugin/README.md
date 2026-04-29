# Prompt Plugin

本文档描述当前 `prompt-plugin/` Prompt 资产模块的真实结构、Markdown schema 和维护规则。

当前系统已经完成重构，并且教育分支的策略选择已经升级为：

- 不再使用旧文档里的 `prompt-management/assets/`
- Prompt 内容资产统一使用结构化 Markdown
- `router` 一次模型调用直接决定当前轮使用哪个 prompt 资产
- `education` 直接落到 `module / subject / style`
- `general_qa`、`casual_chat`、`clarify` 直接落到 `mode`
- prompt 运行时不再承担第二轮 selector 判定
- 运行时链路统一为：

```text
Markdown Asset
-> Parser
-> Structured Spec
-> ResolvedPromptSpec
-> Renderer
-> Final Prompt
```

## 1. 设计原则

Prompt 内容资产不是直接拼给模型的最终 Prompt。

正确方式是：

1. 先把 Markdown 解析成结构化对象
2. 再把结构化对象灌进 renderer
3. 最后产出 system prompt

当前约束：

- 内容资产只用 Markdown
- 不再保留内容资产 YAML 兼容
- `education` 使用 `plugin -> module -> subject -> style`
- `general_qa`、`casual_chat`、`clarify` 使用 `plugin -> mode`
- 当前轮使用哪个 `module / subject / style / mode` 由 Router 单次模型规划决定
- prompt runtime 负责解析和装配资产，不负责再次判断用户意图

补充约束：

- `prompt-plugin/` 当前保存的是内容资产与资产边界语义，不再承担主链热路径里的第二轮本地选择
- 文档里如果提到旧 selector，应理解为历史设计，或者理解为 runtime 仍保留的辅助解析能力，而不是当前 turn 主链

## 2. 目录结构

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
├── plugins/
│   ├── education/
│   │   ├── plugin.md
│   │   └── modules/
│   │       ├── solve/
│   │       │   ├── module.md
│   │       │   ├── subjects/
│   │       │   └── styles/
│   │       ├── answer/
│   │       └── qa/
│   ├── general_qa/
│   │   ├── plugin.md
│   │   └── modes/
│   ├── casual_chat/
│   │   ├── plugin.md
│   │   └── modes/
│   └── clarify/
│       ├── plugin.md
│       └── modes/
└── evals/
    └── strategy_regression.yaml
```

说明：

- `core/` 放跨分支共用资产
- `plugins/` 放各分支自己的结构化内容资产
- `evals/` 放历史样例与评估数据
- 教育分支已不再保留 `selectors/` 目录；如果要表达资产适用边界，统一写在对应 Markdown 资产里

## 3. 运行时抽象

当前运行时主要使用这些结构：

- `PluginSpec`
- `ModuleSpec`
- `SubjectSpec`
- `StyleSpec`
- `ModeSpec`
- `ResolvedPromptSpec`
- `ScenarioPolicy`

对应代码：

- 解析与渲染入口：[ava/infrastructure/prompts/loader.py](/app/streaming-ava/ava/infrastructure/prompts/loader.py)
- schema 运行时：[ava/infrastructure/prompts/runtime.py](/app/streaming-ava/ava/infrastructure/prompts/runtime.py)
- 模型规划落地：[ava/application/orchestration/model_plan_builder.py](/app/streaming-ava/ava/application/orchestration/model_plan_builder.py)
- prompt 拼装：[ava/infrastructure/prompts/prompt_builder.py](/app/streaming-ava/ava/infrastructure/prompts/prompt_builder.py)

## 4. Core 资产

### 4.1 `core/base/`

- `persona.md`：全局助手身份与总原则
- `multimodal_rules.md`：跨分支的多模态处理规则

### 4.2 `core/contracts/`

按 `delivery_mode` 注入输出约束：

- `speech_only.md`
- `speech_brief.md`
- `speech_ui_dual.md`

### 4.3 `core/renderer/`

- `education_renderer.md`：education 模块式 renderer
- `mode_renderer.md`：非教育 mode renderer

### 4.4 `core/router/`

- `router_prompt.md`：Router 的 system prompt

## 5. 运行时职责边界

当前主链里：

1. Router 一次模型调用输出 `route + plan`
2. `plan` 直接给出当前轮该用哪个 `module / subject / style / mode`
3. `model_plan_builder.py` 校验这些 id 是否存在
4. prompt runtime 只负责把对应 Markdown 资产解析成结构化 spec

这意味着：

- `prompt-plugin/` 不再承担主链热路径里的本地 selector 判定
- `prompt-plugin/` 的重点是内容表达、输出结构和交互约束
- 如果回答质量不对，先判断是 Router 选错资产，还是资产本身写得不好
- `runtime.py` 里虽然仍保留了规则表格/YAML 的解析能力，但当前 `dispatcher.py` 主链不会逐条执行这些规则来选 module / subject / style

## 6. Education 插件

### 6.1 当前资产落地顺序

`education` 的资产组织仍然是：

```text
plugin -> module -> subject -> style
```

当前运行时已经不是“本地 selector 逐层判定”，而是：

```text
Router(route + plan)
-> model_plan_builder
-> plugin / module / subject / style asset
-> BranchStrategy
```

其中：

- Router 已经直接给出当前轮该用哪个 `module / subject / style`
- `model_plan_builder` 只做校验、补默认值和资产装配
- 最终 responder prompt 仍然来自这些 Markdown 资产本身

当前 module：

- `solve`
- `check`
- `drill`
- `explain`
- `answer`
- `qa`

最终策略 ID 仍然保持：

```text
education.{module}.{subject}.{style}
```

例如：

- `education.solve.math.step_by_step`
- `education.answer.math.direct`
- `education.qa.english.explain_careful`

### 6.2 目录职责

`plugins/education/plugin.md`

- 教育插件级目标和通用规则
- 可选地补充 module 选择语义，帮助资产作者把适用边界写清楚

`plugins/education/modules/<module>/module.md`

- 定义该 module 的目标、适用范围、回答结构、互动规则和默认输出参数
- 可选地补充该 module 的 `Subject Selection Rules` 与 `Style Selection Rules`
- 也可在 frontmatter 中声明 `capabilities`、`supports_modalities`、`supports_question_kinds`
- 是该 module 的“内容规则单一事实源”

`plugins/education/modules/<module>/subjects/*.md`

- 定义该 module 下的学科差异
- 可在 frontmatter 中声明 `capabilities`、`supports_artifacts`

`plugins/education/modules/<module>/styles/*.md`

- 定义该 module 下的表达风格
- 可在 frontmatter 中声明 `style_traits`

### 6.3 Education Markdown Schema

#### `plugin.md`

必填 frontmatter：

- `id = education`
- `type = plugin`
- `version = 1`
- `plugin_kind = education`

必填 section：

- `## Name`
- `## Purpose`
- `## Rules`

其中：

- `Rules` 使用 Markdown 列表
- `Module Selection Rules` 当前是推荐保留的可选 section，用来表达 module 适用边界；它不是当前 turn 主链里的强制执行入口

#### `module.md`

必填 frontmatter：

- `id = solve`
- `type = module`
- `version = 1`
- `module_kind = education`

必填 section：

- `## Name`
- `## Goal`
- `## Applies To`
- `## Response Structure`
- `## Global Rules`
- `## Interaction Policy`
- `## Output Defaults`
- `## Instructions`

其中：

- `Applies To`、`Response Structure`、`Global Rules`、`Interaction Policy`、`Instructions` 使用 Markdown 列表
- `Output Defaults` 使用 Markdown 键值列表：`- key = value`
- `Subject Selection Rules`、`Style Selection Rules` 当前是推荐保留的可选 section，用来表达该 module 的适用边界和选择语义；主链不会在本地逐条执行它们
- 如果某个 module 想增加更细的教学表达示例，优先写进 `Instructions`，不要引入第二套独立示例格式

#### `subject.md`

必填 frontmatter：

- `id = math`
- `type = subject`
- `version = 1`
- `subject_kind = math`

必填 section：

- `## Name`
- `## Focus`
- `## Explanation Strategy`
- `## Common Mistakes`
- `## Evidence Preference`
- `## UI Hints`
- `## Instructions`

其中：

- `Focus`、`Explanation Strategy`、`Common Mistakes`、`Evidence Preference`、`Instructions` 使用 Markdown 列表
- `UI Hints` 使用 Markdown 键值列表：`- key = value`
- `Instructions` 可以包含“老师可用表达”或“少样例表达”，但要保持短小、可迁移，不能写成长篇示例库

#### `style.md`

必填 frontmatter：

- `id = step_by_step`
- `type = style`
- `version = 1`
- `style_kind = step_by_step`

必填 section：

- `## Name`
- `## Tone`
- `## Constraints`
- `## Output Adjustments`
- `## Instructions`

其中：

- `Constraints`、`Instructions` 使用 Markdown 列表
- `Output Adjustments` 使用 Markdown 键值列表：`- key = value`

#### 选择语义 section 语法

映射类 section 的写法：

- `- delivery_mode = speech_ui_dual`
- `- direct_answer = false`
- `- max_points = 3`

选择语义类 section 的写法：

- 推荐表格写法：

```md
| subject_axis | answer_boundary | primary_action | primary_scenario | select |
| --- | --- | --- | --- | --- |
| math | | | | math |
| | hint_first | | | hint_only |
| | | diagnose_error | practice, lesson | check |
```

- 兼容旧写法：
  - `- if subject_axis = math -> math`
  - `- if answer_boundary = hint_first -> hint_only`
  - `- if primary_action = diagnose_error and primary_scenario in [practice, lesson] -> check`
- 更复杂的条件可直接写 YAML `rules:` code block

补充说明：

- `runtime.py` 仍然支持解析这些表格或 YAML `rules:` block
- 但当前实时主链不会在本地逐条执行这些规则来挑选资产
- 当前真正生效的资产选择来自 Router 返回的 `plan`
- 因此这里更适合把它理解为“资产作者写清适用边界的结构化语义”，而不是“热路径判定脚本”

### 6.4 Education 设计边界

`module` 负责：

- 任务目标
- 适用场景
- 回答结构
- 互动规则

`subject` 负责：

- 学科关注点
- 学科解释策略
- 常见误区
- 证据偏好

`style` 只负责：

- 语气
- 长短
- 直给程度
- 步骤数

不要把这些内容放错层：

- 不要把任务目标塞进 `style`
- 不要把学科逻辑塞进 `module` 之外的无关文件
- 如果要保留选择语义，集中写在对应资产的 selection sections，不要散落到 README、注释或临时文档里

### 6.5 教师化写法建议

教育 prompt 的改写优先顺序：

1. 先改 `Goal / Response Structure / Global Rules`
2. 再改学科 `Explanation Strategy / Instructions`
3. 最后改 style 的输出约束

推荐保留的教师动作：

- 先重建对象，再解释
- 先判断学生卡点，再决定讲多深
- 先结论再依据，或先方向再下一步
- 需要肯定时指出“具体对在哪里”
- 需要纠错时区分“结果错 / 步骤错 / 表述不严谨”

不推荐的写法：

- 空泛鼓励
- 只报规则名不落回题目
- 把短答写成长篇讲课
- 把所有学科都写成同一套抽象口号

## 7. 非教育插件

当前包含：

- `general_qa`
- `casual_chat`
- `clarify`

这些插件统一使用：

```text
plugin -> mode
```

### 6.1 目录职责

`plugins/<branch>/plugin.md`

- 分支目标和通用规则

`plugins/<branch>/modes/*.md`

- mode 级内容资产

### 6.2 `mode.md` schema

必填 frontmatter：

- `id = reasoned`
- `type = mode`
- `version = 1`
- `mode_kind = reasoned`

必填 section：

- `## Name`
- `## Description`
- `## Delivery Mode`
- `## UI Mode`
- `## Response Shape`
- `## Objective`
- `## Instructions`
- `## Interaction Rules`
- `## Examples`
- `## Response Contract`
- `## Speech Policy`

可选 section：

- `## UI Policy`

其中：

- `Instructions`、`Interaction Rules`、`Examples` 使用 Markdown 列表
- `Response Contract`、`Speech Policy`、`UI Policy` 使用 YAML code block

## 7. 选择语义资产

如果需要把资产边界显式写出来，优先写在 Markdown 资产里：

- `plugins/education/plugin.md#Module Selection Rules`
- `plugins/education/modules/<module>/module.md#Subject Selection Rules`
- `plugins/education/modules/<module>/module.md#Style Selection Rules`

当前仍保留 `evals/strategy_regression.yaml`，但它的定位是历史样例集，不再是当前主链的离线 selector 回归脚本输入。

如果语义复杂到表格不够表达，可在对应 section 内直接写 YAML `rules:` code block；不要再新增独立 selector YAML 文件。

## 8. Renderer 规则

当前 renderer 统一使用 Jinja 渲染。

原则：

- Markdown 资产先解析成结构化 spec
- renderer 只吃结构化对象，不直接吃自由文本说明
- 最终 system prompt 由：
  - `core/base/*`
  - `core/contracts/*`
  - `core/renderer/*`
  - runtime context
  共同组成

## 9. 日常维护指引

| 问题现象 | 优先修改位置 |
| --- | --- |
| 教学目标不对 | `plugins/education/modules/*/module.md` |
| 学科讲法不对 | `plugins/education/modules/*/subjects/*.md` |
| 太啰嗦 / 太简短 | `plugins/education/modules/*/styles/*.md` |
| 通用问答模式不对 | `plugins/general_qa/modes/*.md` |
| 轻聊天语气不对 | `plugins/casual_chat/modes/*.md` |
| 澄清问题问得不对 | `plugins/clarify/modes/*.md` |
| 选错 module / subject / style | `core/router/router_prompt.md`、`ava/infrastructure/prompts/prompt_builder.py`、相关资产边界说明 |
| 选错 mode | `core/router/router_prompt.md`、`plugins/*/modes/*.md` |
| 输出结构不对 | `core/renderer/*.md` |
| 上下文注入太多或太少 | `prompt_builder.py` / runtime context builder |

### 9.1 新增 education module

至少新增：

- `plugins/education/modules/<module>/module.md`
- `plugins/education/modules/<module>/subjects/*.md`
- `plugins/education/modules/<module>/styles/*.md`

推荐同步做：

- 在 `plugin.md` / `module.md` 里补充对应的选择语义 section
- 检查 `core/router/router_prompt.md` 是否需要让模型知道这个新 module
- 做真实 E2E 场景验证

### 9.2 新增 education subject

至少新增：

- `plugins/education/modules/<module>/subjects/<subject>.md`
- 如有必要，在对应 module 的 selection section 里补充语义
- 做真实 E2E 场景验证

### 9.3 新增 education style

只改：

- `plugins/education/modules/<module>/styles/<style>.md`
- 如有必要，在对应 module 的 selection section 里补充语义
- 做真实 E2E 场景验证

### 9.4 新增非教育 mode

至少新增：

- `plugins/<branch>/modes/<mode>.md`
- `model_plan_builder.py` 中的 mode 白名单或映射支持
- 做真实 E2E 场景验证

## 10. 回归

当前主链已经切为单次模型规划，不再维护离线 selector 回归脚本。

这些改动后至少要做：

- 语法检查
- 实际对话链路验证
- 修改任何 `plugin/module/subject/style/mode` Markdown 资产后，做一次真实 E2E 场景验证

`evals/strategy_regression.yaml` 当前可以继续作为样例数据参考，但不应再把它理解成“当前主链的自动真相源”。

## 11. 禁止事项

不要重新引入这些旧结构：

- 旧的 `prompt-management/assets/`
- 内容资产 `.yaml`
- 平铺的 `scene / subject / style` 旧目录
- `manifest.yaml`
- `branches/*`
- `policies/*.yaml`
- `render_templates/*.md`

后续只允许沿用当前两类模式：

- `education`: plugin -> module -> subject -> style
- 其他分支: plugin -> mode
