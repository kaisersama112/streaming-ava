---
name: chinese
description: 语文：用于教育场景下的学科解释策略提示技能。
asset:
  kind: knowledge
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

语文：用于教育场景下的学科解释策略提示技能。

该知识 Skill 关注以下内容：

当前句子、当前段落或当前材料

题干问法

文本依据

表达作用

修辞或写作任务

# Instructions

- 先确认当前轮已经进入 education 分支。
- 读取 references/spec.md，拿到当前 subject 的稳定规则。
- 与教育分支、其它教育层资产组合后，再交给外层提示渲染器。
- 先抓当前题的考点和语境，再做分析。
- 阅读或写作题要把“依据在哪里、为什么这样答”说清楚，不空讲技巧。
- 当前轮如果换了新材料，只围绕当前材料回答，不沿用上一题的文本对象。
- 优先指出依据句、限定词和表达作用，不空讲术语。
- 先确认当前处理的是哪一句、哪一段、哪一题或哪一则材料
- 再回到原文、题干和问法
- 再定位考点、语境和关键信息
- 最后解释答案依据或作答路径
- 原文
- 语境
- 表达效果
- 题干限定词

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当当前轮教育计划选择 subject = chinese 时使用
- 当需要把当前 subject 规则注入教育系统提示时使用
- 只背术语，不回到文本
- 表达判断没有依据
- 忽略语境和修辞作用
- 把上一段文本的理解迁到当前新材料
- 只讲套路，不指出依据句
- 当前资产核心作用：当前句子、当前段落或当前材料 / 题干问法 / 文本依据 / 表达作用 / 修辞或写作任务
- 该 Skill 不负责选择逻辑，选择由 ava/router_selector 决定。
