---
name: prompt-general_qa-mode-reasoned
description: 结论加原因：用于通用问答分支下的回答模式提示技能。
asset:
  id: reasoned
  type: mode
  version: 1
  entry: references/spec.md
references:
  - path: references/spec.md
    purpose: 当前 mode 的正式结构、交互规则与输出合同
    when: 当 general_qa 分支已选择 mode = reasoned 并需要构建 responder 系统提示时读取
metadata:
  pattern: Domain Knowledge Pack
  load_policy: 先读取 mode Skill 卡片，再按需读取 references/spec.md
---

# 结论加原因

## Trigger
- 当路由计划选择 general_qa.reasoned 时使用
- 当需要为当前轮回答注入 mode 级约束时使用

## Procedure
1. 先确认当前分支已经是 general_qa。
2. 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
3. 把 mode 规则交给外层提示构建器与渲染模板使用。

## Decision Notes
- 当前 mode 目标：先解决“是什么/会不会”，再用最短理由满足解释需求。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。

## References
- references/spec.md：general_qa.reasoned 正式规范
