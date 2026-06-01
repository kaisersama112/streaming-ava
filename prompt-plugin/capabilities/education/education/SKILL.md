---
name: prompt-education
description: 用于教育场景的分支提示技能，负责定义教学总目标与教育全局规则。
asset:
  id: education
  type: branch
  version: 1
  entry: references/spec.md
references:
  - path: references/spec.md
    purpose: 教育分支总目标与全局规则
    when: 当路由结果 turn_scene = education 并需要构建教育回答系统提示时读取
metadata:
  pattern: Domain Knowledge Pack
  load_policy: 先读取教育分支 Skill 卡片，再按需读取 references/spec.md
---

# 教育

## Trigger
- 当当前轮被路由到 education 时使用
- 当需要装配教育域全局提示规则时使用

## Procedure
1. 先读取本 Skill 卡片，确认教育分支的正式规范入口。
2. 再读取 references/spec.md，获取教育分支总目标与全局规则。
3. 与 module、subject、pedagogy 三层资产组合后，再交给外层提示构建器渲染。

## References
- references/spec.md：教育分支正式规范
