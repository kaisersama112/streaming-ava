# Prompt Plugin

这是 Prompt Skill 资产目录。

整个目录只管理一类资产：

`Skill`

所有 Skill 遵循统一的 Prompt Skill Runtime Contract。

## 目录说明

### `core/`

内部共享运行时资产目录。

当前只保留两类非业务 Skill 资源：

- `core/router/`
  - router 阶段正式 Skill
- `core/renderer/`
  - 统一 responder 渲染器

`core/` 不参与业务 Skill 扫描；
其中 `core/router/SKILL.md` 只由 router 阶段显式加载，
`core/renderer/prompt_renderer.md` 只作为统一渲染模板使用。

### `capabilities/`

顶层能力 Skill 目录。

例如：

- `general`
- `education`

### `components/`

可组合组件 Skill 目录。

例如：

- `task/`
- `knowledge/`
- `method/`
- `audience/`

## 组合模型

运行时采用固定组合顺序：

Capability → Task → Knowledge → Method → Audience

例如：

- `education`
- `solve`
- `math`
- `step-by-step`
- `high-school`

最终组合为一个统一 PromptPackage。

## Skill 结构

每个 Skill 必须满足：

```text
skill/
├── SKILL.md
├── references/
└── assets/
```

## 规范入口

完整规范请参见：

- `CONTRACT.md`

## 设计原则

- 所有 Prompt 资产统一抽象为 Skill
- 所有 Skill 使用统一合同
- 所有 Skill 使用统一解析对象
- 所有 Skill 使用固定组合顺序
- Prompt 资产与运行时上下文解耦
