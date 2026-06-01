# Prompt Skill Runtime Contract v1

## 1. 定义

Prompt Plugin 不是 Markdown 文件集合，而是统一的 Prompt Skill 资产系统。

在本规范中，整个系统只存在一种资产模型：

`Skill`

所有 Prompt 资产都必须以 Skill 形式存在，并遵循统一的目录协议、元数据协议、正文协议、解析协议、组合协议、渲染协议与校验协议。

---

## 2. 目标

本规范用于解决以下问题：

- 统一 Prompt 资产组织方式
- 统一 Prompt 资产元数据格式
- 统一 Prompt 资产解析输出
- 统一 Prompt 资产组合顺序
- 统一 Prompt 资产渲染结果
- 统一 Prompt 资产校验规则

本规范的目标不是管理 Prompt 文件，而是定义一套稳定的 Prompt Skill Runtime Contract。

---

## 3. 核心原则

### 3.1 单一资产模型

整个系统只允许一种 Prompt 资产模型：

`Skill`

不得并行引入独立的一等资产概念，例如：

- Prompt
- Rule
- Profile
- Template
- Spec

上述内容如果存在，只能作为 Skill 的内部组成部分或统一渲染模板存在，不能成为独立业务运行时对象。

### 3.2 单一合同

所有 Skill 必须使用统一协议。

统一协议包括：

- 目录结构
- Frontmatter 字段
- 正文章节
- 解析对象
- 组合顺序
- 输出对象
- 校验规则

### 3.3 固定组合顺序

Skill 的运行时组合顺序固定为：

Capability → Task → Knowledge → Method → Audience

不允许根据场景动态调整顺序。

### 3.4 Prompt 与运行时解耦

Prompt Plugin 仅负责静态 Prompt 资产定义，不负责以下运行时职责：

- 会话管理
- 多轮上下文构造
- 历史压缩
- 路由决策
- 模型调用
- 推理执行

---

## 4. Skill 目录协议

每个 Skill 目录必须遵循统一结构：

```text
skill/
├── SKILL.md
├── references/
└── assets/
```

### 4.1 必需项

- `SKILL.md` 必须存在

### 4.2 可选项

- `references/` 可以存在
- `assets/` 可以存在

### 4.3 目录职责

#### `SKILL.md`

Skill 的唯一入口文件，负责描述：

- 身份
- 触发
- 执行摘要
- 引用入口

#### `references/`

负责存放：

- 长篇规范
- 详细说明
- 扩展规则
- 合同文档

#### `assets/`

负责存放：

- 模板
- 示例
- 固定片段
- 素材

### 4.4 约束

- `references/` 和 `assets/` 不能被视为独立 Skill
- 运行时只能通过 `SKILL.md` 识别一个 Skill
- 不允许一个目录内存在多个 Skill 入口文件

---

## 5. Frontmatter 协议

所有 Skill 的 `SKILL.md` 必须包含 YAML Frontmatter。

标准格式如下：

```yaml
---
name: solve
description: 帮助学习者完成题目并理解解题过程。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
  - references/spec.md
assets: []
---
```

### 5.1 必填字段

#### `name`

- 类型：`string`
- 含义：Skill 名称
- 约束：
  - 必须使用 `kebab-case`
  - 在整个 Prompt Plugin 范围内必须唯一

#### `description`

- 类型：`string`
- 含义：Skill 描述
- 用途：
  - 检索
  - 匹配
  - 触发识别

#### `asset.kind`

- 类型：`string`
- 含义：Skill 类型
- 允许值：
  - `capability`
  - `task`
  - `knowledge`
  - `method`
  - `audience`

#### `version`

- 类型：`string`
- 含义：Skill 版本
- 建议格式：语义化版本号

#### `load_policy`

- 类型：`string`
- 含义：加载策略
- 允许值：
  - `preload`
  - `on_demand`

#### `references`

- 类型：`list[string]`
- 含义：引用的规范文件路径
- 约束：
  - 路径必须相对当前 Skill 根目录
  - 文件必须真实存在

#### `assets`

- 类型：`list[string]`
- 含义：引用的资源路径
- 约束：
  - 路径必须相对当前 Skill 根目录
  - 文件必须真实存在

---

## 6. 正文协议

所有 Skill 的正文只允许使用以下四个一级标题：

- `# Purpose`
- `# Instructions`
- `# References`
- `# Examples`

不允许新增其他一级标题。

### 6.1 Purpose

用于回答：

- 这个 Skill 为什么存在
- 这个 Skill 解决什么问题
- 这个 Skill 在组合中的职责是什么

### 6.2 Instructions

用于回答：

- 这个 Skill 应该如何执行
- 这个 Skill 的行为约束是什么
- 这个 Skill 的输出要求是什么

### 6.3 References

用于回答：

- 当前 Skill 依赖哪些规范入口
- 哪些 references 文件与当前 Skill 相关

### 6.4 Examples

用于回答：

- 典型触发场景
- 典型输入样式
- 典型使用方式

---

## 7. Skill 解析协议

所有 Skill 解析后必须输出为统一对象：

```python
class Skill:
    name: str
    description: str
    kind: str
    version: str
    load_policy: str
    purpose: str
    instructions: str
    references: list[str]
    assets: list[str]
    examples: list[str]
```

### 7.1 解析原则

- 不为不同 kind 创建不同类
- 不允许并行存在 `TaskSkill`、`MethodSkill`、`KnowledgeSkill`
- 整个系统只允许统一的 `Skill` 运行时对象

### 7.2 字段来源

- `name`、`description`、`kind`、`version`、`load_policy`、`references`、`assets` 来自 Frontmatter
- `purpose`、`instructions`、`examples` 来自正文
- `references` 章节用于表达引用说明，不单独形成第二套对象

---

## 8. Skill 组合协议

Skill 按固定顺序组合：

1. Capability
2. Task
3. Knowledge
4. Method
5. Audience

### 8.1 组合原则

- 顺序固定
- 不允许动态排序
- 不允许跳出主顺序构造自定义树形结构

### 8.2 组合语义

- Capability：回答“为什么答”
- Task：回答“做什么”
- Knowledge：回答“讲什么”
- Method：回答“怎么讲”
- Audience：回答“讲给谁”

---

## 9. Skill 渲染协议

每个 Skill 渲染为统一片段：

```text
[Skill: <name>]

Purpose:
...

Instructions:
...
```

### 9.1 渲染要求

- 必须输出 Skill 名称
- 必须输出 Purpose
- 必须输出 Instructions
- References 与 Examples 是否进入最终 prompt，由 Prompt Package Builder 决定

### 9.2 渲染目标

渲染结果用于构造系统级 Prompt 片段，而不是替代运行时上下文。

---

## 10. PromptPackage 协议

Prompt 渲染器最终只允许输出统一对象：

```python
class PromptPackage:
    capability: Skill
    skills: list[Skill]
    references: list[str]
    assets: list[str]
    prompt: str
```

### 10.1 字段含义

#### `capability`

当前主能力 Skill。

#### `skills`

参与当前组合的全部 Skill，顺序必须符合正式组合顺序。

#### `references`

聚合后的规范路径列表。

#### `assets`

聚合后的资源路径列表。

#### `prompt`

最终渲染出的 Prompt 文本。

---

## 11. 校验协议

必须提供统一校验器，对全部 Skill 进行结构化检查。

### 11.1 Directory Validator

检查：

- Skill 目录是否存在 `SKILL.md`

### 11.2 Metadata Validator

检查：

- `name`
- `description`
- `asset.kind`
- `version`
- `load_policy`
- `references`
- `assets`

### 11.3 Section Validator

检查是否完整存在以下四个一级标题：

- `Purpose`
- `Instructions`
- `References`
- `Examples`

### 11.4 Reference Validator

检查 Frontmatter 中声明的 `references` 文件是否存在。

### 11.5 Asset Validator

检查 Frontmatter 中声明的 `assets` 文件是否存在。

### 11.6 Global Name Validator

检查全局是否存在重名 Skill。

---

## 12. 职责边界

### 12.1 Prompt Plugin 负责

- Skill 资产定义
- Skill 规范组织
- Prompt 组合规则定义
- Prompt 渲染输入准备

### 12.2 Prompt Plugin 不负责

- 多轮上下文管理
- 对话历史存储
- 路由选择
- 模型执行
- 推理流程编排

---

## 13. 版本边界

当前规范版本为：

`v1`

v1 明确不包含以下能力：

- 全局 `id`
- `dependencies`
- `applies_to`
- `scripts` 执行协议

如需扩展，必须在后续版本中显式升级。
