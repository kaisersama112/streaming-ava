# 教育提示资产目录

这个目录现在是教育提示资产的唯一结构入口。

## 设计目标

- 把“教学任务”“学科偏好”“教学法”拆成正交层
- 不再把 `subject`、`pedagogy` 挂在每个 `module` 下面重复维护
- 让教育提示资产围绕单一目录长期演进

## 当前状态

- 系统只读取 `prompt-plugin/education/`
- 旧 `prompt-plugin/plugins/education/` 已完成迁移并已删除

## 目录结构

```text
education/
  branch.md
  modules/
    solve.md
    check.md
    explain.md
    qa.md
    answer.md
    drill.md
  subjects/
    math.md
    english.md
    chinese.md
    physics.md
    history.md
    cs.md
    general.md
  pedagogies/
    step_by_step.md
    explain_careful.md
    hint_only.md
    direct.md
```

## 迁移原则

- `module` 只描述教学任务
- `subject` 只描述学科解释策略
- `pedagogy` 只描述教学法
- 选择规则不再继续写进 markdown 资产里，后续应放在 resolver 或配置层
