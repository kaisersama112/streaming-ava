# Overview

该文档描述 `clarify-scene` Skill 的详细规范与扩展说明。

references/spec.md：clarify.scene 正式规范

旧资产名称：回答场景

# Detailed Rules

## Instructions

- 优先澄清回答方式，不问内容细节。
- 问法自然简短，让用户能直接选“直接答”还是“像老师一样讲”。

## Description

当前轮不确定是老师式讲解还是普通回答。

## Objective

先把回答场景对齐，避免整条分支走偏。

# Rendering Notes

## Response Contract

- single_question_only = true

## Speech Policy

- style = brief

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 你是直接答，还是像老师一样讲
- 当路由计划选择 clarify.scene 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
