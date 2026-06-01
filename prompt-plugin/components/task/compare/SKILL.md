---
name: compare
description: 简短对比：用于通用问答分支下的回答模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

简短对比：用于通用问答分支下的回答模式提示技能。

帮用户快速做出选择，让他知道“该怎么选”和“主要差在哪”，而不是展开成长评测。

# Instructions

- 先确认当前分支已经是 general_qa。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 直接给倾向判断。
- 差异只保留最关键的一到两个维度。
- 优先围绕用户当前目标给建议，不做泛泛罗列。
- 条件不足时，也给保守结论口径。
- 不写长表格。
- 不回避做判断。
- 如果差异其实不大，要直接说清。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 general_qa.compare 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 平板和学习机哪个好
- 这两个设置有什么区别
- 当前 mode 目标：帮用户快速做出选择，让他知道“该怎么选”和“主要差在哪”，而不是展开成长评测。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
