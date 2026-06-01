---
name: prompt-general_qa
description: 用于普通事实问答、操作指导、排查解释等场景的分支提示技能。
asset:
  id: general_qa
  type: branch
  version: 1
  entry: references/spec.md
references:
  - path: references/spec.md
    purpose: 该分支的正式规则与目标
    when: 当路由已选择 general_qa 分支并需要构建 responder 系统提示时读取
metadata:
  pattern: Domain Knowledge Pack
  load_policy: 先读取本 Skill 卡片，再按需读取 references/spec.md
---

# 通用问答

## Trigger
- 当路由结果 turn_scene = general_qa 时使用
- 当需要为 general_qa 分支构建系统提示时使用

## Procedure
1. 先读取本文件的 frontmatter，确认资产入口与加载策略。
2. 构建正式系统提示前，再读取 references/spec.md。
3. 仅注入稳定分支目标与规则；当前轮输入、多轮历史、运行时上下文由外层模块提供。

## References
- references/spec.md：general_qa 分支正式规范
