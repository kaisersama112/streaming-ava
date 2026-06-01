---
name: prompt-education-module-drill
description: 练习生成：用于教育场景下的教学任务提示技能。
asset:
  id: drill
  type: module
  version: 1
  entry: references/spec.md
references:
  - path: references/spec.md
    purpose: 当前 module 的正式规范
    when: 当教育计划已经选择 module = drill 并需要构建 responder 系统提示时读取
metadata:
  pattern: Domain Knowledge Pack
  load_policy: 先读取本 Skill 卡片，再按需读取 references/spec.md
---

# 练习生成

## Trigger
- 当当前轮教育计划选择 module = drill 时使用
- 当需要把当前 module 规则注入教育系统提示时使用

## Procedure
1. 先确认当前轮已经进入 education 分支。
2. 读取 references/spec.md，拿到当前 module 的稳定规则。
3. 与教育分支、其它教育层资产组合后，再交给外层提示渲染器。

## Decision Notes
- 当前资产核心作用：围绕当前知识点、题型或课内对象生成有组织的练习，让学生知道这组题是怎么安排的，而不是把练习生成写成当前题的继续讲解。
- 该 Skill 不负责选择逻辑，选择由 ava/router_selector 决定。

## References
- references/spec.md：教育 module 正式规范
