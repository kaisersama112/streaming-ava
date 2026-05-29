# 四层推理架构

当前系统围绕四个正式模块组织：

## 1. 路由选择模块

目录：

```text
ava/router_selector/
```

职责：

- 路由决策 schema
- 路由策略归一
- router 请求装配
- router 模型执行编排

## 2. 多轮上下文构造器

目录：

```text
ava/multi_turn_context_builder/
```

职责：

- 当前输入装配
- 多轮历史拼接
- instructions 编译
- messages 构造
- ConversationContext 构建

## 3. 模型执行器

目录：

```text
ava/llm_model_executor/
```

职责：

- ModelRequestContext 构建
- InferenceRequest 构建
- provider 调用
- 流式 / 非流式结果标准化

## 4. 推理运行时

目录：

```text
ava/inference_runtime/
```

职责：

- turn plan 生成
- reply 执行
- 路由后到最终回答的运行编排

## 兼容层说明

以下目录已降为兼容层：

```text
ava/context_engine/
ava/routing/
ava/capabilities/llm/
```

它们保留旧导入路径，但不再承载核心实现。
