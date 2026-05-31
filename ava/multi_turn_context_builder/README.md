# 多轮上下文构造器

`ava.multi_turn_context_builder` 是当前系统的正式上下文实现层。

## 结构

- `compiler.py`：唯一主实现，统一负责输入装配、上下文构造、消息组装、instructions 编译
- `types.py`：最小数据类型定义
- `__init__.py`：对外导出正式入口

## 职责

- 接收标准 `user message`
- 构建多轮会话上下文
- 编译每轮 `instructions`
- 构建传给模型的 `input` 消息数组

当前实现不再拆分多个细粒度子构造器，避免过度封装。
上下文层不再负责附件 DTO 装配，只接受标准 `user message` 作为当前轮输入。

## 输出目标

最终面向模型的输入结构始终围绕：

```json
{
  "instructions": "...",
  "input": [
    {
      "role": "system",
      "content": [
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": ""
        },
        {
          "type": "input_image",
          "image_url": ""
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
      ]
    }
  ]
}
```

说明：

- `instructions` 作为本轮系统指令单独传递
- `input` 始终是按对话顺序排列的消息数组
- `system` / `developer` / `user` / `assistant` 都通过统一消息结构承载
- `assistant` 内容块使用 `output_text`
- `user` 内容块优先使用 `input_text` / `input_image`

参数详解：
instructions:
作为系统指令插入到上下文的起始位置。使用 previous_response_id 时，上一轮指定的 instructions 不会传入本轮上下文
role string （必选）：
消息角色，可选值：user、assistant、system、developer。
content string 或 array （必选）：
消息内容。若输入为纯文本，则为 string 类型；若输入为结构化内容数组，则为 array 类型。role 为 system/developer 时，array 元素类型为
input_text；role 为 user 时，array 元素类型为 input_text 或 input_image；role 为 assistant 时，array 元素类型为 output_text。
type string （必选）
可选值：input_text（文本输入）、input_image（图片输入，仅 user 角色）、output_text（助手回复，仅 assistant 角色）。
text string
文本内容。当 type 为 input_text 或 output_text 时必填。
image_url string
图片的公网 URL。当 type 为 input_image 时必填。

## 边界

- 不负责路由决策
- 不负责模型执行
- 不负责最终回复编排
- 不把附件领域对象作为上下文主体字段继续向下游暴露
