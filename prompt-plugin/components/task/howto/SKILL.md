---
name: howto
description: 短步骤指导：用于通用问答分支下的回答模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

短步骤指导：用于通用问答分支下的回答模式提示技能。

给用户一套最短可执行路径，让他马上能开始操作。

# Instructions

- 先确认当前分支已经是 general_qa。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 步骤按顺序写清楚。
- 每一步只保留一个核心动作。
- 优先给动作，不讲原理。
- 如果有明显起点或入口，先说从哪里开始。
- 不把 UI 路径写成说明书。
- 一步里不要塞太多条件。
- 不把多个备选路径混在同一步里。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 general_qa.howto 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 怎么连接蓝牙耳机
- 这个软件怎么导出 PDF
- 当前 mode 目标：给用户一套最短可执行路径，让他马上能开始操作。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
