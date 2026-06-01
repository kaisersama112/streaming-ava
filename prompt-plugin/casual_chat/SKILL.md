---
name: prompt-casual_chat
description: 用于轻聊天、陪伴互动、短反馈表达等场景的分支提示技能。
asset:
  id: casual_chat
  type: branch
  version: 1
  entry: references/spec.md
references:
  - path: references/spec.md
    purpose: 该分支的正式规则与目标
    when: 当路由已选择 casual_chat 分支并需要构建 responder 系统提示时读取
metadata:
  pattern: Domain Knowledge Pack
  load_policy: 先读取本 Skill 卡片，再按需读取 references/spec.md
---

# 轻聊天

## Trigger
- 当路由结果 turn_scene = casual_chat 时使用
- 当需要为 casual_chat 分支构建系统提示时使用

## Procedure
1. 先读取本文件的 frontmatter，确认资产入口与加载策略。
2. 构建正式系统提示前，再读取 references/spec.md。
3. 仅注入稳定分支目标与规则；当前轮输入、多轮历史、运行时上下文由外层模块提供。

## References
- references/spec.md：casual_chat 分支正式规范
