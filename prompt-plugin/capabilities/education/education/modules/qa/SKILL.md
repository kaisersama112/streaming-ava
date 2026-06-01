---
name: prompt-education-module-qa
description: 知识答疑：用于教育场景下的教学任务提示技能。
asset:
  id: qa
  type: module
  version: 1
  entry: references/spec.md
references:
  - path: references/spec.md
    purpose: 当前 module 的正式规范
    when: 当教育计划已经选择 module = qa 并需要构建 responder 系统提示时读取
metadata:
  pattern: Domain Knowledge Pack
  load_policy: 先读取本 Skill 卡片，再按需读取 references/spec.md
---

# 知识答疑

## Trigger
- 当当前轮教育计划选择 module = qa 时使用
- 当需要把当前 module 规则注入教育系统提示时使用

## Procedure
1. 先确认当前轮已经进入 education 分支。
2. 读取 references/spec.md，拿到当前 module 的稳定规则。
3. 与教育分支、其它教育层资产组合后，再交给外层提示渲染器。

## Decision Notes
- 当前资产核心作用：解释概念、原理或方法，消除一个明确的理解障碍，而不是泛泛讲一大段背景，更不要把旧题和当前新对象混在一起。
- 该 Skill 不负责选择逻辑，选择由 ava/router_selector 决定。

## References
- references/spec.md：教育 module 正式规范
