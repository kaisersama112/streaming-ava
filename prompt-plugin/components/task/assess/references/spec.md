# assess 规范

## 输入契约

- `education_state`：当前学科、知识点、学段、水平（只读事实）
- `message_block_memory`：附件分析摘要（含 contains_student_work 标记）
- `recent_topics` / `context_summary`：近期主题与会话摘要
- 学生本轮文本与作答内容

## 输出契约

固定四段，总长度控制在 120 字以内（语音场景）：

1. 掌握判断：`掌握` / `部分掌握` / `未掌握` / `证据不足`
2. 关键证据：引用学生具体一步或一句
3. 薄弱点：单一最关键的缺口
4. 下一步建议：一个可立即执行的动作

## 状态写回

只允许提交白名单 patch 建议：

- `knowledge_point`：本轮确认的知识点
- `stage`：学段
- `level`：掌握水平（如 basic / developing / fluent）

禁止写入 session_scene、turn_records、memory 结构等核心事实源。

## 边界

- 不做整题重解
- 不跨题沿用旧掌握判断
- 证据不足时不得给出确定性结论