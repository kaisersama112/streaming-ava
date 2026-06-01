# Prompt Plugin

`prompt-plugin/` 是系统的提示资产层。

它现在采用统一的 **Skill 目录结构 + 渐进披露加载** 方案：

- 第一层：`SKILL.md`
  - 只放触发摘要、用途说明、正式资产入口
- 第二层：`references/spec.md`
  - 放稳定的结构化 Prompt 规范
- 第三层：`core/`
  - 放渲染模板、合同片段、基础人格与路由提示

## 设计目标

- 让分支、模式、教育模块、学科、教学法都用统一结构表达
- 让加载器先读轻量 `SKILL.md`，再按需读取正式规范
- 把稳定提示资产与运行时上下文彻底分开
- 让 Prompt 资产更接近标准 Skill，而不是散落 Markdown 文件

## 采用的 Skill 模式

Prompt 资产主要采用：

- **Pattern B — Domain Knowledge Pack**
  - 适用于稳定规则、边界、回答风格、结构合同
- 部分结合 **Pattern D — Template Renderer**
  - `core/renderer/` 与 `core/contracts/` 负责渲染与输出结构

不采用的部分：

- 不在这里做路由判断
- 不在这里做多轮上下文拼装
- 不在这里直接发模型请求

## 当前目录结构

```text
prompt-plugin/
  core/
    base/
    contracts/
    renderer/
    router/
  general_qa/
    SKILL.md
    references/spec.md
    modes/
      fact/
        SKILL.md
        references/spec.md
      ...
  casual_chat/
    SKILL.md
    references/spec.md
    modes/
      smalltalk/
        SKILL.md
        references/spec.md
      ...
  clarify/
    SKILL.md
    references/spec.md
    modes/
      subject/
        SKILL.md
        references/spec.md
      ...
  education/
    SKILL.md
    references/spec.md
    modules/
      solve/
        SKILL.md
        references/spec.md
      ...
    subjects/
      math/
        SKILL.md
        references/spec.md
      ...
    pedagogies/
      step_by_step/
        SKILL.md
        references/spec.md
      ...
```

## 加载原则

## 正式资产契约

### 1. `SKILL.md` 统一结构

每个正式 Prompt Skill 都必须包含：

- frontmatter
  - `name`
  - `description`
  - `asset.id`
  - `asset.type`
  - `asset.version`
  - `asset.entry`
  - `metadata.pattern`
  - `metadata.load_policy`
- section
  - `Trigger`
  - `Procedure`
  - `References`
- 可选 section
  - `Decision Notes`

当前允许的 `asset.type` 只有：

- `branch`
- `mode`
- `module`
- `subject`
- `pedagogy`

### 2. `references/spec.md` 统一结构

每个正式规范文件都必须有 frontmatter：

- `id`
- `type`
- `version`

其中 `type` 必须与对应 Skill 的 `asset.type` 一致。

各类型要求如下：

- `branch`
  - section：`Name` `Purpose` `Rules`
- `mode`
  - section：`Name` `Description` `Delivery Mode` `UI Mode` `Response Shape` `Objective` `Instructions` `Interaction Rules` `Examples` `Response Contract` `Speech Policy`
- `module`
  - section：`Name` `Goal` `Applies To` `Response Structure` `Global Rules` `Interaction Policy` `Output Defaults` `Instructions`
- `subject`
  - section：`Name` `Focus` `Explanation Strategy` `Common Mistakes` `Evidence Preference` `UI Hints` `Instructions`
- `pedagogy`
  - section：`Name` `Tone` `Constraints` `Output Adjustments` `Instructions`

### 3. `core/` 不是 Skill

`core/` 下的资产不走 Skill 解析器，它们是内部渲染与合同片段：

- `core/base/`
- `core/contracts/`
- `core/renderer/`
- `core/router/`

## 加载原则

### 1. Skill 卡片优先

加载器先读 `SKILL.md`，只拿：

- `name`
- `description`
- `asset`
- `references`
- `metadata`
- `Trigger / Procedure / References` 的轻量结构

这一步只用于：

- 识别资产类型
- 确认正式规范入口
- 控制按需继续读取

### 2. 正式规范按需读取

只有当上层真正需要构造系统提示时，才继续读取：

- `references/spec.md`

正式规范负责提供：

- 分支目标
- mode 目标与回答合同
- 教育模块目标
- 学科解释策略
- 教学法约束

### 3. 渲染模板单独维护

`core/` 下的 Markdown 不是 Skill，而是内部渲染资产：

- `core/base/`：通用人格与多模态基础规则
- `core/contracts/`：交付模式合同
- `core/renderer/`：系统提示渲染模板
- `core/router/`：路由模型系统提示

## 工程边界

Prompt 资产层只定义 **稳定规则**，不承载运行时动态信息。

运行时动态信息应来自：

- `ava/multi_turn_context_builder`
- `ava/router_selector`
- `ava/inference_runtime`
- `ava/llm_model_executor`

也就是说：

- Prompt 资产定义“该怎么答”
- 上下文层提供“现在拿到了什么输入与历史”
- 推理运行时决定“这一轮实际怎么执行”
