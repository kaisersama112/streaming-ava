---
name: general-knowledge
description: 通用教育：用于教育场景下的学科解释策略提示技能。
asset:
  kind: knowledge
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

通用教育：用于教育场景下的学科解释策略提示技能。

该知识 Skill 关注以下内容：

题意重建

当前对象

关键条件

当前卡点

# Instructions

- 先确认当前轮已经进入 education 分支。
- 读取 references/spec.md，拿到当前 subject 的稳定规则。
- 与教育分支、其它教育层资产组合后，再交给外层提示渲染器。
- 当学科不确定时，先准确重建当前对象，再给最稳的解释或引导。
- 当前轮如果带来新附件或新题干，以当前对象为准，不从旧历史里强行补另一道题。
- 不因为学科不确定就泛讲，要始终落回当前题、当前对象和下一步。
- 先确认当前到底在处理哪个对象
- 再抓关键条件、关键关系或判断标准
- 最后推进下一步
- 题意重建
- 当前附件或当前文本
- 关键条件
- 当前对象
- 最稳妥解释

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当当前轮教育计划选择 subject = general 时使用
- 当需要把当前 subject 规则注入教育系统提示时使用
- 对象没重建清楚就开始解释
- 忽略用户当前卡点
- 给了泛泛答案没有落回问题
- 把旧历史里的对象误当成当前对象
- 当前资产核心作用：题意重建 / 当前对象 / 关键条件 / 当前卡点
- 该 Skill 不负责选择逻辑，选择由 ava/router_selector 决定。
