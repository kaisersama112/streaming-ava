# Routing

`ava/application/routing/` 负责把当前用户输入一次性转成两类结果：

- `RouteDecision`
- `router_plan`

当前主链已经不是“先粗路由，再让下游再猜一次”。Router 现在会在一次模型调用里同时完成：

- 当前会话是否仍处在 `education` 或 `general`
- 当前这一轮属于 `education / general_qa / casual_chat / clarify` 哪个分支
- 当前这一轮真正的意图是什么
- 后续 `TurnPlan` 应该落到哪个 prompt 资产

## 目标

Router 当前必须一次性回答这些问题：

- 当前轮 `session_scene` 是什么
- 当前轮 `turn_scene` 是什么
- 当前轮 `intent` 是什么
- 是否需要澄清
- 是否保留教学状态
- 如果进入 `education`，该用哪个 `module / subject / style / policy_id / primary_action`
- 如果进入 `general_qa / casual_chat / clarify`，该用哪个 `mode`

## 当前主链

```text
TurnInput + ConversationState
-> assemble_context(profile="router")
-> 最近原始问答 + 最近轮摘要 + 当前输入附件 + 当前状态
-> build_router_messages
-> llm_client.chat
-> JSON extract / schema validate
-> confidence policy
-> RouteDecision + router_plan
```

## 这一步到底做什么

可以把 Router 理解成“当前轮意图判定 + 当前轮策略草案生成”的单轮规划器。

它实际做的是：

1. 读取当前用户文本、最近几轮原始 `history_messages`、摘要、附件、`education_state` 和事实状态。
2. 结合这些证据判断当前这一轮是不是在延续前几轮里的同一个对象。
3. 直接输出结构化 JSON，而不是只给一个场景标签。
4. 把当前轮后续需要的 `plan` 一起产出，交给下游直接落地。

教育分支返回示例：

```json
{
  "session_scene": "education",
  "turn_scene": "education",
  "intent": "solve_problem",
  "confidence": 0.91,
  "should_preserve_teaching_state": true,
  "need_clarification": false,
  "plan": {
    "branch": "education",
    "module": "explain",
    "subject": "math",
    "style": "explain_careful",
    "policy_id": "practice.error_diagnosis",
    "primary_scenario": "practice",
    "primary_action": "diagnose_error",
    "learning_objects": ["knowledge_gap"],
    "object_scope": "knowledge_gap",
    "object_continuity": "uncertain",
    "answer_boundary": "direct_explain",
    "prompt_overrides": ["..."],
    "plan_reason": "..."
  }
}
```

非教育分支返回示例：

```json
{
  "session_scene": "general",
  "turn_scene": "general_qa",
  "intent": "ask_fact",
  "confidence": 0.87,
  "should_preserve_teaching_state": false,
  "need_clarification": false,
  "plan": {
    "branch": "general_qa",
    "mode": "reasoned",
    "plan_reason": "..."
  }
}
```

这意味着 Router 当前不只是“把用户送进某个分支”，而是已经直接给出：

- 当前轮是不是 follow-up
- 当前轮跟前几轮在不在说同一个对象
- 当前轮后续应该使用哪个资产 id

一个典型例子是用户只说“我不会”“没懂”“下一步呢”这类短句。当前链路要求 Router 不能只看这句话本身，而必须回看最近几轮原始问答和状态，恢复它实际在追问哪道题、哪一步、哪种困难。

## 当前输入证据

Router 做判断时，依赖这些证据：

- 当前用户文本
- 最近几轮原始 `history_messages`
- `recent_history_summary`
- `recent_turns_summary`
- 当前附件与继承参考附件
- 当前 `education_state`
- 当前 `facts`

当前约束：

- 不能只看当前一句短文本
- 必须把“短追问”放回最近几轮上下文里解释
- 一旦模型成功返回 `plan`，后续主链不再做第二轮语义判定

## 失败兜底

当前仍保留 `heuristics.py`，但它只在这些情况下介入：

- Router 模型调用失败
- 模型输出无法解析
- `plan` 缺失或明显不完整

兜底时会同时生成本地 `router_plan`，这样下游仍然走同一条 `build_turn_plan()` 主链，而不是退回旧的多段 selector 方案。

## 关键文件

- [service.py](/app/streaming-ava/ava/application/routing/service.py)
  - `RouterService.route_with_context()`
  - 单次模型调用、JSON 解析、fallback plan 构造
- [multimodal.py](/app/streaming-ava/ava/application/routing/multimodal.py)
  - Router 请求消息组装
- [parser.py](/app/streaming-ava/ava/application/routing/parser.py)
  - 从模型输出中提取 JSON
- [heuristics.py](/app/streaming-ava/ava/application/routing/heuristics.py)
  - 仅在模型失败时兜底

## 输出契约

核心字段：

- `session_scene`
- `turn_scene`
- `intent`
- `confidence`
- `should_preserve_teaching_state`
- `need_clarification`
- `plan`

领域定义见：

- [ava/domain/routing/schema.py](/app/streaming-ava/ava/domain/routing/schema.py)
- [ava/domain/routing/policy.py](/app/streaming-ava/ava/domain/routing/policy.py)

## 与其他模块关系

- 下游由 [orchestration/README.md](/app/streaming-ava/ava/application/orchestration/README.md) 直接消费 `router_plan`
- 上下文来自 [ava/domain/README.md](/app/streaming-ava/ava/domain/README.md)
- Prompt 文本由 [ava/infrastructure/prompts/prompt_builder.py](/app/streaming-ava/ava/infrastructure/prompts/prompt_builder.py) 组装
