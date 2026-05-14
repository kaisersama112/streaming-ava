"""独立于路由 / 状态机的会话记忆模型。"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from typing import Any, Callable

from ava.domain.multimodal import MediaArtifact, TurnInput
from ava.domain.conversation.summary import summarize_history


class SessionMemory:
    """会话级持久记忆槽位与连续性元数据。"""

    def __init__(self, memory_size: int = 8) -> None:
        # 记忆窗口大小，至少为 1；默认保留最近 8 个单位
        self.memory_size = max(1, int(memory_size or 8))

        # 初始化所有记忆字段
        self.reset()

    @staticmethod
    def empty_education_state() -> dict[str, Any]:
        """返回教育场景状态的空模板。"""

        return {
            # 学科，例如数学、英语、物理等
            "subject": "",

            # 当前知识点
            "knowledge_point": "",

            # 当前学习阶段，例如讲解、练习
            "stage": "",

            # 最近一次题目或问题内容
            "last_problem": "",

            # 学习水平或难度等级
            "level": "",

            # 学习场景，例如 lesson、practice
            "learning_scenario": "",

            # 当前涉及的学习对象，例如 problem、lesson_segment
            "learning_objects": [],

            # 学习对象范围
            "object_scope": "",

            # 学习对象连续性，用于判断是否承接上一轮
            "object_continuity": "",

            # 当前主要动作，例如 explain、solve、check
            "primary_action": "",

            # 当前次要动作列表
            "secondary_actions": [],

            # 回答边界，例如 contextual_only
            "answer_boundary": "",

            # 上一轮分支
            "previous_branch": "",

            # 上一轮策略 ID
            "previous_strategy_id": "",

            # 上一轮 policy ID
            "previous_policy_id": "",

            # 上一轮策略相关状态快照
            "previous_strategy_state": {},
        }

    def reset(self) -> None:
        """重置当前会话记忆。"""

        # 简单事实槽位，例如姓名、身份、位置、偏好等
        self.facts: dict[str, str] = {}

        # 最近话题，使用固定长度队列限制记忆大小
        self.recent_topics: deque[str] = deque(maxlen=self.memory_size)

        # 文本上下文摘要
        self.context_summary: str = "无"

        # 多模态上下文摘要
        self.multimodal_context_summary: str = "无"

        # 附件分析缓存，key 为 artifact bundle key
        self.artifact_analysis_cache: dict[str, dict[str, Any]] = {}

        # 教育场景连续性状态
        self.education_state: dict[str, Any] = self.empty_education_state()

    def to_payload(
        self,
        *,
        history: list[dict[str, Any]],
        turn_records: list[dict[str, Any]],
        summarize_turn_records: Callable[[list[dict[str, Any]]], str],
    ) -> dict[str, Any]:
        """将当前记忆序列化为可持久化 payload。"""

        return {
            # 已抽取的事实槽位
            "facts": dict(self.facts),

            # 最近话题列表
            "recent_topics": list(self.recent_topics),

            # 基于最近 history 动态生成文本摘要
            "context_summary": summarize_history(
                history[-(self.memory_size * 2) :]
            ),

            # 基于最近 turn records 动态生成多模态摘要
            "multimodal_context_summary": summarize_turn_records(
                turn_records[-self.memory_size :]
            ),

            # 附件分析缓存
            "artifact_analysis_cache": dict(self.artifact_analysis_cache),

            # 教育场景状态
            "education_state": dict(self.education_state),
        }

    def load_payload(
        self,
        data: dict[str, Any],
        *,
        history: list[dict[str, Any]],
        turn_records: list[dict[str, Any]],
        summarize_turn_records: Callable[[list[dict[str, Any]]], str],
    ) -> None:
        """从持久化 payload 恢复会话记忆。"""

        # 兼容外层 data 中不存在 memory 字段，或 memory 字段类型异常的情况
        payload = data.get("memory")
        memory_payload = dict(payload) if isinstance(payload, dict) else {}

        # 恢复事实槽位：
        # - key/value 都转为字符串
        # - 过滤空 key 和空值
        self.facts = {
            str(key): str(value)
            for key, value in dict(memory_payload.get("facts") or {}).items()
            if str(key).strip() and value not in (None, "")
        }

        # 恢复最近话题，并重新绑定 maxlen
        self.recent_topics = deque(
            [
                str(item)
                for item in (memory_payload.get("recent_topics") or [])
                if str(item).strip()
            ],
            maxlen=self.memory_size,
        )

        # 摘要不直接信任持久化值，而是根据当前 history / turn_records 重新生成
        self.context_summary = summarize_history(
            history[-(self.memory_size * 2) :]
        )
        self.multimodal_context_summary = summarize_turn_records(
            turn_records[-self.memory_size :]
        )

        # 恢复并规范化附件分析缓存
        self.artifact_analysis_cache = self.normalize_artifact_analysis_cache(
            memory_payload.get("artifact_analysis_cache") or {}
        )

        # 用空模板兜底，避免旧 payload 缺少新增字段
        base_education_state = self.empty_education_state()
        base_education_state.update(
            dict(memory_payload.get("education_state") or {})
        )
        self.education_state = base_education_state

    def refresh_summaries(
        self,
        *,
        history: list[dict[str, Any]],
        turn_records: list[dict[str, Any]],
        summarize_turn_records: Callable[[list[dict[str, Any]]], str],
    ) -> None:
        """刷新文本摘要与多模态摘要。"""

        # 基于最近若干条 history 重新生成文本摘要
        self.context_summary = summarize_history(
            history[-(self.memory_size * 2) :]
        )

        # 基于最近若干条 turn record 重新生成多模态摘要
        self.multimodal_context_summary = summarize_turn_records(
            turn_records[-self.memory_size :]
        )

    def update_fact_slots(self, user_text: str) -> None:
        """从用户文本中用简单规则抽取事实槽位。"""

        # 基于中文显式表达的轻量正则抽取
        patterns = [
            (r"我叫([\u4e00-\u9fa5A-Za-z0-9_]{1,20})", "name"),
            (r"我是([\u4e00-\u9fa5A-Za-z0-9_]{1,20})", "identity"),
            (r"我在([\u4e00-\u9fa5A-Za-z0-9_]{1,20})", "location"),
            (r"我喜欢([\u4e00-\u9fa5A-Za-z0-9_]{1,30})", "likes"),
            (r"我讨厌([\u4e00-\u9fa5A-Za-z0-9_]{1,30})", "dislikes"),
        ]

        # 命中后写入对应事实槽位
        for pattern, slot in patterns:
            match = re.search(pattern, user_text)
            if match:
                self.facts[slot] = match.group(1)

    def apply_route_transition(
        self,
        *,
        should_preserve_teaching_state: bool,
    ) -> None:
        """根据路由切换结果决定是否保留教学状态。"""

        # 如果新路由不应延续教学状态，则清空教育场景状态
        if not should_preserve_teaching_state:
            self.education_state = self.empty_education_state()

    def update_education_state_from_text(self, user_text: str) -> None:
        """根据用户原始文本更新教育场景状态。"""

        # 粗略识别学科
        match_subject = re.search(
            r"(数学|语文|英语|物理|化学|生物|历史|地理|政治)",
            user_text,
        )
        if match_subject:
            self.education_state["subject"] = match_subject.group(1)

        # 粗略识别知识点描述
        match_point = re.search(
            r"(?:讲解|解释|学习|复习|辅导|讲题|知识点是|关于)([\u4e00-\u9fa5A-Za-z0-9_、，,（）()\-]{2,30})",
            user_text,
        )

        # 出现“知识点”但未命中结构化表达时，截取前 30 字作为兜底知识点
        if "知识点" in user_text and not match_point:
            self.education_state["knowledge_point"] = user_text[:30]

        # 命中知识点表达时，清理常见标点后写入
        elif match_point:
            self.education_state["knowledge_point"] = match_point.group(1).strip(
                "：:，,。 "
            )

        # 根据关键词判断讲解阶段
        if any(keyword in user_text for keyword in ["讲解", "解释", "思路", "为什么"]):
            self.education_state["stage"] = "讲解"

        # 根据关键词判断练习阶段，并记录最近题目
        if any(keyword in user_text for keyword in ["练习", "做题", "题目"]):
            self.education_state["stage"] = "练习"
            self.education_state["last_problem"] = user_text[:40]

    def update_education_state_from_strategy(
        self,
        strategy: dict[str, Any] | None,
        *,
        turn_input: TurnInput | None = None,
    ) -> None:
        """根据路由 / 策略分析结果更新教育场景状态。"""

        # 没有策略结果时不更新
        if not strategy:
            return

        # 策略分析信息
        analysis = dict(strategy.get("analysis") or {})

        # 教育轮次结构；兼容旧字段 task_frame
        frame = dict(
            analysis.get("education_turn_frame")
            or analysis.get("task_frame")
            or {}
        )

        # 场景策略配置
        scenario_policy = dict(frame.get("scenario_policy") or {})

        # 学科优先从策略显式字段读取，其次从 analysis 读取，最后沿用已有状态
        subject = str(
            strategy.get("subject")
            or analysis.get("subject_axis")
            or analysis.get("subject")
            or self.education_state.get("subject")
            or ""
        ).strip()
        if subject:
            self.education_state["subject"] = subject

        # 读取核心教育场景字段
        learning_scenario = str(
            frame.get("primary_scenario")
            or analysis.get("primary_scenario")
            or ""
        ).strip()
        primary_action = str(
            frame.get("primary_action")
            or analysis.get("primary_action")
            or ""
        ).strip()
        object_scope = str(
            frame.get("object_scope")
            or analysis.get("object_scope")
            or ""
        ).strip()
        object_continuity = str(
            frame.get("object_continuity")
            or analysis.get("object_continuity")
            or ""
        ).strip()

        # 学习对象列表
        learning_objects = [
            str(item).strip()
            for item in (
                frame.get("learning_objects")
                or analysis.get("learning_objects")
                or []
            )
            if str(item).strip()
        ]

        # 次要动作列表
        secondary_actions = [
            str(item).strip()
            for item in (frame.get("secondary_actions") or [])
            if str(item).strip()
        ]

        # 回答边界
        answer_boundary = str(
            scenario_policy.get("answer_boundary")
            or analysis.get("answer_boundary")
            or ""
        ).strip()

        # 写入学习场景，并同步粗粒度 stage
        if learning_scenario:
            self.education_state["learning_scenario"] = learning_scenario
            self.education_state["stage"] = (
                "练习" if learning_scenario == "practice" else "讲解"
            )

        # 写入学习对象
        if learning_objects:
            self.education_state["learning_objects"] = learning_objects

        # 写入对象范围
        if object_scope:
            self.education_state["object_scope"] = object_scope

        # 写入对象连续性
        if object_continuity:
            self.education_state["object_continuity"] = object_continuity

        # 写入主要动作
        if primary_action:
            self.education_state["primary_action"] = primary_action

        # 次要动作允许为空列表，用于覆盖上一轮遗留值
        self.education_state["secondary_actions"] = secondary_actions

        # 写入回答边界
        if answer_boundary:
            self.education_state["answer_boundary"] = answer_boundary

        # 写入知识点；优先使用 analysis 中的知识点，否则沿用已有知识点
        knowledge_point = str(
            analysis.get("knowledge_point")
            or self.education_state.get("knowledge_point")
            or ""
        ).strip()
        if knowledge_point:
            self.education_state["knowledge_point"] = knowledge_point

        # 如果当前学习对象包含 problem，则记录当前题目内容
        if turn_input is not None and "problem" in set(learning_objects):
            current_problem = (
                turn_input.normalized_text()
                or turn_input.multimodal_summary()
            )
            if current_problem:
                self.education_state["last_problem"] = current_problem[:80]

        # 记录上一轮策略标识与关键状态，供后续连续性判断使用
        branch = str(strategy.get("branch") or "").strip()
        strategy_id = str(strategy.get("strategy_id") or "").strip()
        policy_id = str(
            strategy.get("policy_id")
            or analysis.get("selected_policy_id")
            or ""
        ).strip()

        previous_state = {
            "previous_branch": branch,
            "previous_strategy_id": strategy_id,
            "previous_policy_id": policy_id,
            "previous_subject": subject,
            "previous_primary_scenario": learning_scenario,
            "previous_primary_action": primary_action,
            "previous_learning_objects": learning_objects,
            "previous_object_scope": object_scope,
            "previous_object_continuity": object_continuity,
            "previous_answer_boundary": answer_boundary,
        }

        self.education_state["previous_branch"] = branch
        self.education_state["previous_strategy_id"] = strategy_id
        self.education_state["previous_policy_id"] = policy_id
        self.education_state["previous_strategy_state"] = previous_state

    @staticmethod
    def normalize_artifact_analysis_cache(
        cache: dict[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        """规范化附件分析缓存结构。"""

        normalized: dict[str, dict[str, Any]] = {}

        for key, value in dict(cache or {}).items():
            # 缓存 key 必须是非空字符串
            cache_key = str(key or "").strip()

            # 缓存值必须是 dict
            if not cache_key or not isinstance(value, dict):
                continue

            # 统一将内层 key 转为字符串
            normalized[cache_key] = {
                str(item_key): item_value
                for item_key, item_value in value.items()
            }

        return normalized

    @staticmethod
    def _artifact_source_token(
        artifact: MediaArtifact | dict[str, Any],
    ) -> str:
        """为单个附件生成稳定的来源 token。"""

        # 支持 MediaArtifact 对象
        if isinstance(artifact, MediaArtifact):
            ref = artifact.data_url or artifact.uri or artifact.name
            kind = artifact.kind
            name = artifact.name
            summary = artifact.summary

        # 也支持 dict 形式的附件
        else:
            ref = (
                artifact.get("data_url")
                or artifact.get("uri")
                or artifact.get("name")
                or ""
            )
            kind = str(artifact.get("kind", "") or "")
            name = str(artifact.get("name", "") or "")
            summary = str(artifact.get("summary", "") or "")

        # 对来源引用做 hash，避免把 data_url 等大字段直接写入 key
        digest = hashlib.sha256(
            str(ref).encode("utf-8", errors="ignore")
        ).hexdigest()[:16]

        # 组合附件类型、名称、摘要片段与来源 hash
        return f"{kind}:{name}:{digest}:{summary[:32]}"

    def artifact_bundle_key(
        self,
        artifacts: tuple[MediaArtifact, ...]
        | list[MediaArtifact]
        | list[dict[str, Any]],
    ) -> str:
        """为一组附件生成 bundle key。"""

        # 每个附件生成一个 token
        parts = [
            self._artifact_source_token(artifact)
            for artifact in list(artifacts or [])
        ]

        # 最多取前 4 个附件，限制 key 长度
        return "|".join(parts[:4])

    @staticmethod
    def _truncate_text(value: str, limit: int) -> str:
        """截断文本并追加省略号。"""

        text = str(value or "").strip()

        # 未超过限制时直接返回
        if len(text) <= limit:
            return text

        # 超过限制时截断并补充省略号
        return text[:limit].rstrip() + "..."

    def _metadata_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
    ) -> dict[str, Any]:
        """基于附件 metadata 构建轻量级附件分析结果。"""

        items = list(artifacts or [])

        # 没有附件时不生成分析结果
        if not items:
            return {}

        # 当前只取第一个附件作为代表性分析对象
        first = items[0]
        metadata = dict(first.metadata or {})

        return {
            # 附件内容摘要
            "summary": self._truncate_text(
                first.summary or first.name or "附件内容",
                120,
            ),

            # 面向题目 / 问题理解的摘要
            "question_summary": self._truncate_text(
                first.summary or first.name or "附件内容",
                120,
            ),

            # 学科提示
            "subject_hint": str(
                metadata.get("subject_hint") or "unknown"
            ).strip() or "unknown",

            # 任务提示
            "task_hint": str(
                metadata.get("task_hint") or "unknown"
            ).strip() or "unknown",

            # 是否包含学生作答内容
            "contains_student_work": bool(
                metadata.get("contains_student_work")
            ),

            # 是否包含课程上下文
            "contains_lesson_context": bool(
                metadata.get("contains_lesson_context")
            ),

            # 是否包含子题
            "contains_sub_problem": bool(
                metadata.get("contains_sub_problem")
            ),

            # 是否包含题干
            "contains_problem_statement": bool(
                metadata.get("contains_problem_statement")
            ),

            # 教育相关性：
            # 特定 artifact_role 认为是中等相关，否则较弱
            "education_relevance": (
                "medium"
                if metadata.get("artifact_role")
                in {"problem_material", "answer_sheet", "lesson_clip"}
                else "weak"
            ),

            # 如果包含学生作答，则后续追问通常需要重新视觉读取
            "followup_requires_visual_reread": bool(
                metadata.get("contains_student_work")
            ),

            # metadata 推断的默认置信度
            "confidence": 0.45,

            # 标记该分析结果来自 metadata
            "source": "metadata",
        }

    def cached_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
    ) -> dict[str, Any]:
        """读取已缓存的附件分析结果。"""

        # 根据附件组生成缓存 key
        cache_key = self.artifact_bundle_key(artifacts)

        # 没有有效 key 时无法读取缓存
        if not cache_key:
            return {}

        # 命中缓存时返回副本，避免调用方修改内部缓存
        cached = self.artifact_analysis_cache.get(cache_key)
        if cached:
            return dict(cached)

        return {}

    def cached_or_metadata_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
    ) -> dict[str, Any]:
        """优先读取缓存分析；没有缓存时回退到 metadata 分析。"""

        # 优先使用已缓存的 LLM / 上游分析结果
        cached = self.cached_artifact_analysis(artifacts)
        if cached:
            return cached

        # 未命中缓存时，用 metadata 生成轻量分析结果
        return self._metadata_artifact_analysis(artifacts)

    def remember_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
        analysis: dict[str, Any],
    ) -> None:
        """缓存一组附件的分析结果。"""

        # 根据附件组生成缓存 key
        cache_key = self.artifact_bundle_key(artifacts)

        # 没有 key 或没有分析内容时不缓存
        if not cache_key or not analysis:
            return

        # 缓存最多保留 64 条；超过上限时删除最早插入的 key
        if (
            len(self.artifact_analysis_cache) >= 64
            and cache_key not in self.artifact_analysis_cache
        ):
            oldest_key = next(iter(self.artifact_analysis_cache))
            self.artifact_analysis_cache.pop(oldest_key, None)

        # 写入缓存，并统一 key 为字符串
        self.artifact_analysis_cache[cache_key] = {
            str(key): value
            for key, value in dict(analysis or {}).items()
        }

    def to_debug_payload(self) -> dict[str, Any]:
        """返回用于调试的记忆状态摘要。"""

        return {
            # 事实槽位
            "facts": dict(self.facts),

            # 最近话题
            "recent_topics": list(self.recent_topics),

            # 文本上下文摘要
            "context_summary": self.context_summary,

            # 多模态上下文摘要
            "multimodal_context_summary": self.multimodal_context_summary,

            # 教育状态
            "education_state": dict(self.education_state),

            # 附件分析缓存条数
            "artifact_analysis_cache_size": len(self.artifact_analysis_cache),
        }