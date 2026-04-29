当前分支：{{ plugin.name }}

分支目标：
{{ plugin.purpose }}

分支规则：
{% for item in plugin.rules %}- {{ item }}
{% endfor %}

当前模式：{{ mode.name }}

模式说明：
{{ mode.description }}

模式目标：
{{ mode.objective }}

回答结构：
{{ mode.response_shape }}

模式指令：
{% for item in mode.instructions %}- {{ item }}
{% endfor %}

交互约束：
{% for item in mode.interaction_rules %}- {{ item }}
{% endfor %}

示例场景：
{% for item in mode.examples %}- {{ item }}
{% endfor %}

当前用户问题：
{{ user_text }}

最近上下文摘要：
{{ recent_history_summary }}

最近轮摘要：
{{ recent_turns_summary }}

多模态摘要：
{{ multimodal_summary }}

facts:
{{ facts_json }}

请直接输出自然中文回答：
- 优先解决用户当前问题
- 能先给结论时先给结论
- 素材类问题先说最关键可见信息，再回到用户问题
- 保持专业、自然、清楚，不端着也不说教
- 保持语气符合当前分支
- 不输出 JSON、字段名或代码块
- 不暴露内部结构
