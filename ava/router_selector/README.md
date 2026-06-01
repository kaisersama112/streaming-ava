# 路由选择模块

`ava/router_selector` 是正式的路由与当前轮计划前置层。

它只负责回答一个问题：

> 基于当前多轮上下文，这一轮应该进入哪个场景，并且应该如何组织当前轮执行计划。

## 模块职责

- 调用 router model 做场景判定
- 解析 `RouteDecision`
- 读取 router 返回的 `plan`
- 把 `plan` 归一化为正式教育计划或通用 mode 计划
- 产出当前轮的 `BranchStrategy`
- 把 Prompt 选择结果收口为 `ResolvedPromptSpec`

## 与 Prompt Skill 架构的关系

当前版本已经统一到新的 Prompt Skill 架构：

- Prompt 资产目录：`prompt-plugin/`
- 资产结构：`SKILL.md + references/spec.md`
- 加载入口：`ava/capabilities/prompt/loaders.py`

也就是说，`router_selector` 不再拼接旧式：

- `plugin.md`
- `branch.md`
- `mode.md`
- `style.md`
- 路径字符串 + 变量字典

现在它只做两件事：

1. 选出当前轮该使用哪些 Prompt Skill
2. 把这些 Skill 对应的正式 Spec 对象放进 `ResolvedPromptSpec`

## 目录

```text
ava/router_selector/
  __init__.py
  schema.py
  service.py
  education_plan.py
  education_resolver.py
  strategy_builder.py
  README.md
  ARCHITECTURE.md
```

## 输出对象

- `RouteDecision`
- `EducationTurnPlan`
- `ResolvedEducationPlan`
- `BranchStrategy`
- `ResolvedPromptSpec`

## 不负责

- 多轮消息底层拼装
- 模型请求发送
- responder 最终执行
- Prompt Markdown 文件读取细节

这些职责分别属于：

- `ava/multi_turn_context_builder`
- `ava/llm_model_executor`
- `ava/inference_runtime`
- `ava/capabilities/prompt`
