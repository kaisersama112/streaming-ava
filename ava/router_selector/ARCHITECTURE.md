# Router Selector Architecture

## 定位

`ava/router_selector` 位于四层正式链路中的第二层：

1. `ava/multi_turn_context_builder`
2. `ava/router_selector`
3. `ava/inference_runtime`
4. `ava/llm_model_executor`

它的输入是：

- 原始多轮标准消息上下文
- 当前轮用户消息
- router model 返回结果

它的输出是：

- 当前轮正式 `BranchStrategy`
- 当前轮正式 `PromptPackage`

## 新 Prompt Skill 架构口径

Prompt 资产现在统一采用：

```text
prompt-plugin/
  capabilities/
    general/
    education/
  components/
    task/
    knowledge/
    method/
    audience/
  core/
```

每个 Skill 统一为：

```text
skill/
  SKILL.md
  references/spec.md
  assets/
```

因此 `router_selector` 只面向一个正式 Prompt 对象：

- `Skill`
  - 对应统一 Skill 合同
  - 由 `ava/capabilities/prompt` 负责解析

## 内部数据流

### 1. `service.py`

负责：

- 接收上下文
- 组织 router 输入
- 调用 router model
- 输出 `RouteDecision + router_plan`

### 2. `education_plan.py`

负责：

- 定义教育计划数据结构
- 作为 router `plan` 的教育子结构承载体

### 3. `education_resolver.py`

负责：

- 归一化 router 给出的教育计划
- 选择教育组合中的 `task / knowledge / method`
- 读取正式 `Skill`

### 4. `strategy_builder.py`

负责：

- 把 `RouteDecision + router_plan` 转成正式 `BranchStrategy`
- 同时构造当前轮正式 `PromptPackage`

## 设计边界

### 这里负责的

- 场景路由
- 当前轮 plan 归一化
- 当前轮 Prompt Skill 选择
- 当前轮策略对象生成

### 这里不负责的

- 多轮消息剪裁与上下文拼装
- prompt 文件的底层解析与缓存
- responder 执行
- SDK 请求发送

## 结果

这一层现在的正式职责可以概括为：

> 从“当前轮要去哪”推进到“当前轮应该带着哪一组 Skill 与 PromptPackage 去执行”。
