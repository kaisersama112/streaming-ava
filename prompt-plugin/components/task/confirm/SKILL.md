---
name: confirm
description: 快速确认：用于通用问答分支下的回答模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

快速确认：用于通用问答分支下的回答模式提示技能。

用一个极短回合完成确认，不拖成长解释。

# Instructions

- 先确认当前分支已经是 general_qa。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 先明确 yes/no 或结论。
- 再补一句最必要的依据或成立条件。
- 不能确认时，明确缺什么条件。
- 不拖长。
- 不回避结论。
- 不把一句确认问答讲成分析课。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 general_qa.confirm 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 我这样理解对吗
- 这样设置可以吗
- 当前 mode 目标：用一个极短回合完成确认，不拖成长解释。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
