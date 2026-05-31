import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace

# from ava.llm_model_executor.service import LLMService
# from ava.llm_model_executor.request import InferenceRequestBuilder
from ava.capabilities.prompt import EducationPromptCatalog
from ava.llm_model_executor.types import InferenceTask
from ava.capabilities.prompt import PromptCenter, PromptCenterConfig
from ava.multi_turn_context_builder.compiler import ContextCompiler
# from ava.multi_turn_context_builder.input import AttachmentPayload
from ava.multi_turn_context_builder.types import ConversationBuildOptions
from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.strategy import BranchStrategy, ResolvedPromptSpec
from ava.pipeline.generation.education_resolver import EducationPlanResolver
from ava.router_selector.service import RouterService
from ava.router_selector.schema import RouteDecision
from ava.pipeline.generation.types import TurnPlan


class ContextRequestBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.prompt_dir = self.root / "prompt-plugin"
        (self.prompt_dir / "core" / "router").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "core" / "base").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "core" / "contracts").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "core" / "renderer").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "plugins" / "general_qa" / "modes").mkdir(parents=True, exist_ok=True)

        (self.prompt_dir / "core" / "router" / "router_prompt.md").write_text(
            "ROUTER PROMPT",
            encoding="utf-8",
        )
        (self.prompt_dir / "core" / "base" / "persona.md").write_text(
            "BASE PERSONA",
            encoding="utf-8",
        )
        (self.prompt_dir / "core" / "contracts" / "speech_only.md").write_text(
            "SPEECH CONTRACT",
            encoding="utf-8",
        )
        (self.prompt_dir / "core" / "renderer" / "mode_renderer.md").write_text(
            "RENDERER",
            encoding="utf-8",
        )
        (self.prompt_dir / "plugins" / "general_qa" / "plugin.md").write_text(
            "---\n"
            "id: general_qa\n"
            "type: plugin\n"
            "version: 1\n"
            "plugin_kind: general_qa\n"
            "---\n\n"
            "# Plugin\n\n"
            "## Name\n"
            "General QA\n\n"
            "## Purpose\n"
            "General QA.\n\n"
            "## Rules\n"
            "- Be direct.\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "plugins" / "general_qa" / "modes" / "fact.md").write_text(
            "---\n"
            "id: fact\n"
            "type: mode\n"
            "version: 1\n"
            "mode_kind: fact\n"
            "---\n"
            "# Mode\n\n"
            "## Name\n"
            "Fact Mode\n\n"
            "## Description\n"
            "Factual answers\n\n"
            "## Delivery Mode\n"
            "speech_only\n\n"
            "## UI Mode\n"
            "none\n\n"
            "## Response Shape\n"
            "direct\n\n"
            "## Objective\n"
            "Answer directly\n\n"
            "## Instructions\n"
            "- Give a factual answer.\n\n"
            "## Interaction Rules\n"
            "- Keep it concise.\n\n"
            "## Examples\n"
            "- Example question\n\n"
            "## Response Contract\n"
            "- answer_first = true\n\n"
            "## Speech Policy\n"
            "- style = concise\n",
            encoding="utf-8",
        )

        self.prompt_center = PromptCenter(PromptCenterConfig(prompt_dir=self.prompt_dir))
        self.compiler = ContextCompiler()
        self.builder = InferenceRequestBuilder()
        self.llm_service = LLMService(
            prompt_center=self.prompt_center,
            context_compiler=self.compiler,
            request_builder=self.builder,
        )
        self.state = ConversationState(self.root / "state.json", memory_size=8, session_id="test")

    def _strategy(self) -> BranchStrategy:
        return BranchStrategy(
            branch="general_qa",
            strategy_id="general_qa.fact",
            name="Fact",
            description="Fact mode",
            render_template="core/renderer/mode_renderer.md",
            delivery_mode="speech_only",
            ui_mode="none",
            mode="fact",
            response_contract={},
            speech_policy={},
            resolved_prompt_spec=ResolvedPromptSpec(
                branch="general_qa",
                strategy_id="general_qa.fact",
                base_files=("core/base/persona.md",),
                contract_file="core/contracts/speech_only.md",
                renderer_file="core/renderer/mode_renderer.md",
                variables={},
            ),
        )

    def _decision(self) -> RouteDecision:
        return RouteDecision.model_validate(
            {
                "session_scene": "general",
                "turn_scene": "general_qa",
                "intent": "fact_query",
                "confidence": 0.9,
                "should_preserve_teaching_state": False,
                "need_clarification": False,
            }
        )

    def test_router_request_uses_prompt_as_instructions_and_history_messages(self) -> None:
        self.state.turn_records = [
            {
                "turn_id": 1,
                "user_text": "prev question",
                "assistant_text": "prev answer",
                "multimodal_summary": "",
                "artifacts": [],
                "turn_status": "completed",
            }
        ]

        llm_context = self.llm_service.build_context(
            task=InferenceTask.ROUTE,
            state=self.state,
            turn_input="current question",
        )
        request = self.builder.build(llm_context)
        payload = dict(request.payload or {})
        input_items = list(payload.get("input") or [])

        self.assertIn("ROUTER PROMPT", payload.get("instructions", ""))
        self.assertGreaterEqual(len(input_items), 2)
        self.assertEqual(input_items[0]["role"], "user")
        self.assertEqual(input_items[0]["content"][0]["type"], "input_text")
        self.assertEqual(input_items[0]["content"][0]["text"], "prev question")
        self.assertEqual(input_items[1]["role"], "assistant")
        self.assertEqual(input_items[1]["content"][0]["type"], "output_text")
        self.assertEqual(input_items[1]["content"][0]["text"], "prev answer")
        self.assertEqual(input_items[-1]["role"], "user")
        self.assertNotIn("conversation", payload)
        self.assertNotIn("previous_response_id", payload)

    def test_responder_request_uses_explicit_history_and_disables_stateful_chain(self) -> None:
        self.state.turn_records = [
            {
                "turn_id": 1,
                "user_text": "prev question",
                "assistant_text": "prev answer",
                "multimodal_summary": "",
                "artifacts": [],
                "turn_status": "completed",
            }
        ]
        self.state.update_responder_conversation_state(
            conversation_id="conv_123",
            previous_response_id="resp_456",
        )

        strategy = self._strategy()
        decision = self._decision()
        plan = TurnPlan(
            decision=decision,
            orchestrator_name="test",
            strategy=strategy,
            responder_messages=[],
        )

        llm_context = self.llm_service.build_context(
            task=InferenceTask.GENERATE,
            state=self.state,
            turn_input="current question",
            decision=decision,
            plan=plan,
        )
        request = self.builder.build(llm_context)
        payload = dict(request.payload or {})
        input_items = list(payload.get("input") or [])

        self.assertIn("BASE PERSONA", payload.get("instructions", ""))
        self.assertIn("SPEECH CONTRACT", payload.get("instructions", ""))
        self.assertEqual(input_items[0]["role"], "user")
        self.assertEqual(input_items[0]["content"][0]["type"], "input_text")
        self.assertEqual(input_items[0]["content"][0]["text"], "prev question")
        self.assertTrue(
            any(
                item["role"] == "assistant"
                and isinstance(item["content"], list)
                and item["content"][0]["type"] == "output_text"
                and item["content"][0]["text"] == "prev answer"
                for item in input_items
            )
        )
        self.assertEqual(input_items[-1]["role"], "user")
        self.assertEqual(input_items[-1]["content"][0]["type"], "input_text")
        self.assertEqual(input_items[-1]["content"][0]["text"], "current question")
        self.assertNotIn("conversation", payload)
        self.assertNotIn("previous_response_id", payload)
        self.assertEqual(request.metadata.get("strategy", {}).get("strategy_id"), "general_qa.fact")

    def test_current_turn_attachments_are_included_without_reference_inheritance(self) -> None:
        attachment = AttachmentPayload(
            name="diagram.png",
            mime_type="image/png",
            data=b"fake-image",
            summary="geometry problem",
        )
        turn_input = self.compiler.build_turn_input(
            text="help me inspect this",
            attachments=[attachment],
            source="test",
        )
        context = self.compiler.build_conversation_context(
            state=self.state,
            turn_input=turn_input,
            options=ConversationBuildOptions(
                history_window=8,
                profile="responder_minimal",
            ),
        )

        self.assertEqual(len(context.current.artifacts), 1)
        self.assertEqual(len(tuple(context.current.artifacts or ())), 1)
        strategy = self._strategy()
        messages = self.compiler.build_responder_messages(
            context=context,
            strategy=strategy,
        )
        self.assertEqual(messages[-1]["role"], "user")
        self.assertIsInstance(messages[-1]["content"], list)
        self.assertTrue(
            any(
                isinstance(part, dict) and part.get("type") == "input_image"
                for part in messages[-1]["content"]
            )
        )

    def test_router_service_falls_back_when_model_omits_plan(self) -> None:
        router = RouterService(
            prompt_center=self.prompt_center,
            compiler=self.compiler,
        )
        raw_output = (
            '{'
            '"session_scene":"general",'
            '"turn_scene":"general_qa",'
            '"intent":"fact_query",'
            '"confidence":0.84,'
            '"should_preserve_teaching_state":false,'
            '"need_clarification":false'
            '}'
        )

        with patch.object(LLMService, "route", return_value=type("Result", (), {"text": raw_output})()):
            result = router.route(
                turn_input="current question",
                state=self.state,
                history_window=8,
            )

        self.assertEqual(result.decision.turn_scene, "general_qa")
        self.assertEqual(result.router_plan.get("mode"), "fact")
        self.assertEqual(
            result.router_plan.get("plan_reason"),
            "router_plan_missing_fallback",
        )

    def test_education_plan_resolver_normalizes_plan_and_loads_assets(self) -> None:
        (self.prompt_dir / "education" / "modules").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "education" / "subjects").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "education" / "pedagogies").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "education" / "branch.md").write_text(
            "---\n"
            "id: education\n"
            "type: plugin\n"
            "version: 1\n"
            "plugin_kind: education\n"
            "---\n\n"
            "# Plugin\n\n"
            "## Name\n"
            "教育\n\n"
            "## Purpose\n"
            "面向教学讲解。\n\n"
            "## Rules\n"
            "- 保持教学连续性。\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "education" / "modules" / "solve.md").write_text(
            "---\n"
            "id: solve\n"
            "type: module\n"
            "version: 1\n"
            "---\n\n"
            "# Module\n\n"
            "## Name\n"
            "讲题求解\n\n"
            "## Goal\n"
            "帮助学生推进当前问题。\n\n"
            "## Applies To\n"
            "- 讲题\n\n"
            "## Response Structure\n"
            "- 先定位对象\n\n"
            "## Global Rules\n"
            "- 方法优先\n\n"
            "## Interaction Policy\n"
            "- 推进下一步\n\n"
            "## Output Defaults\n"
            "- delivery_mode = speech_ui_dual\n"
            "- ui_mode = learning_card\n\n"
            "## Instructions\n"
            "- 先解释再推进。\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "education" / "subjects" / "math.md").write_text(
            "---\n"
            "id: math\n"
            "type: subject\n"
            "version: 1\n"
            "---\n\n"
            "# Subject\n\n"
            "## Name\n"
            "数学\n\n"
            "## Focus\n"
            "- 条件\n\n"
            "## Explanation Strategy\n"
            "- 先梳理条件\n\n"
            "## Common Mistakes\n"
            "- 忽略条件\n\n"
            "## Evidence Preference\n"
            "- 题目条件\n\n"
            "## UI Hints\n"
            "- ui_mode_default = math_steps\n\n"
            "## Instructions\n"
            "- 强调条件与关系。\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "education" / "pedagogies" / "step_by_step.md").write_text(
            "---\n"
            "id: step_by_step\n"
            "type: style\n"
            "version: 1\n"
            "---\n\n"
            "# Style\n\n"
            "## Name\n"
            "分步引导\n\n"
            "## Tone\n"
            "structured\n\n"
            "## Constraints\n"
            "- 不跳步\n\n"
            "## Output Adjustments\n"
            "- max_steps = 3\n\n"
            "## Instructions\n"
            "- 每次只推进一步。\n",
            encoding="utf-8",
        )

        context = self.compiler.build_conversation_context(
            state=self.state,
            turn_input="这一步我不会了，下一步怎么做？",
            options=ConversationBuildOptions(
                history_window=8,
                profile="router",
            ),
        )
        resolver = EducationPlanResolver()
        decision = RouteDecision.model_validate(
            {
                "session_scene": "education",
                "turn_scene": "education",
                "intent": "solve_problem",
                "confidence": 0.92,
                "should_preserve_teaching_state": True,
                "need_clarification": False,
            }
        )
        resolved = resolver.resolve(
            prompt_center=self.prompt_center,
            decision=decision,
            context=context,
            router_plan={
                "module": "solve",
                "subject": "math",
                "pedagogy": "step_by_step",
                "primary_scenario": "practice",
                "primary_action": "solve_current_problem",
                "learning_objects": ["problem"],
                "object_scope": "whole_problem",
                "object_continuity": "follow_current_object",
            },
        )

        self.assertEqual(resolved.plan.subject, "math")
        self.assertEqual(resolved.plan.learner_state, "blocked")
        self.assertEqual(resolved.plan.answer_boundary, "hint_first")
        self.assertEqual(resolved.assets.subject.name, "数学")
        self.assertEqual(resolved.ui_mode, "math_steps")

    def test_education_strategy_uses_pedagogy_field(self) -> None:
        (self.prompt_dir / "education" / "modules").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "education" / "subjects").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "education" / "pedagogies").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "education" / "branch.md").write_text(
            "---\n"
            "id: education\n"
            "type: plugin\n"
            "version: 1\n"
            "---\n\n"
            "# Plugin\n\n"
            "## Name\n"
            "教育\n\n"
            "## Purpose\n"
            "教育场景。\n\n"
            "## Rules\n"
            "- 保持教学连续性。\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "education" / "modules" / "solve.md").write_text(
            "---\n"
            "id: solve\n"
            "type: module\n"
            "version: 1\n"
            "---\n\n"
            "# Module\n\n"
            "## Name\n"
            "讲题求解\n\n"
            "## Goal\n"
            "推进当前问题。\n\n"
            "## Applies To\n"
            "- 讲题\n\n"
            "## Response Structure\n"
            "- 先定位对象\n\n"
            "## Global Rules\n"
            "- 不串题\n\n"
            "## Interaction Policy\n"
            "- 推进下一步\n\n"
            "## Output Defaults\n"
            "- delivery_mode = speech_ui_dual\n"
            "- ui_mode = learning_card\n\n"
            "## Instructions\n"
            "- 推进当前问题。\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "education" / "subjects" / "math.md").write_text(
            "---\n"
            "id: math\n"
            "type: subject\n"
            "version: 1\n"
            "---\n\n"
            "# Subject\n\n"
            "## Name\n"
            "数学\n\n"
            "## Focus\n"
            "- 条件\n\n"
            "## Explanation Strategy\n"
            "- 梳理条件\n\n"
            "## Common Mistakes\n"
            "- 忽略条件\n\n"
            "## Evidence Preference\n"
            "- 条件\n\n"
            "## UI Hints\n"
            "- ui_mode_default = math_steps\n\n"
            "## Instructions\n"
            "- 强调条件。\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "education" / "pedagogies" / "step_by_step.md").write_text(
            "---\n"
            "id: step_by_step\n"
            "type: style\n"
            "version: 1\n"
            "---\n\n"
            "# Style\n\n"
            "## Name\n"
            "分步引导\n\n"
            "## Tone\n"
            "structured\n\n"
            "## Constraints\n"
            "- 不跳步\n\n"
            "## Output Adjustments\n"
            "- max_steps = 3\n\n"
            "## Instructions\n"
            "- 每次只推进一步。\n",
            encoding="utf-8",
        )

        from ava.pipeline.generation.model_plan_builder import build_strategy_from_model_plan

        context = self.compiler.build_conversation_context(
            state=self.state,
            turn_input="下一步怎么做？",
            options=ConversationBuildOptions(
                history_window=8,
                profile="router",
            ),
        )
        decision = RouteDecision.model_validate(
            {
                "session_scene": "education",
                "turn_scene": "education",
                "intent": "solve_problem",
                "confidence": 0.91,
                "should_preserve_teaching_state": True,
                "need_clarification": False,
            }
        )
        strategy = build_strategy_from_model_plan(
            self.prompt_center,
            decision,
            context,
            router_plan={
                "module": "solve",
                "subject": "math",
                "pedagogy": "step_by_step",
                "primary_scenario": "practice",
                "primary_action": "solve_current_problem",
                "learning_objects": ["problem"],
                "object_scope": "whole_problem",
                "object_continuity": "follow_current_object",
            },
        )

        self.assertEqual(strategy.pedagogy, "step_by_step")
        self.assertEqual(strategy.selection.to_metadata().get("pedagogy"), "step_by_step")
        self.assertEqual(strategy.analysis.get("pedagogy"), "step_by_step")

    def test_education_prompt_catalog_prefers_new_directory_layout(self) -> None:
        (self.prompt_dir / "education" / "modules").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "education" / "subjects").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "education" / "pedagogies").mkdir(parents=True, exist_ok=True)

        (self.prompt_dir / "education" / "branch.md").write_text(
            "---\n"
            "id: education\n"
            "type: plugin\n"
            "version: 1\n"
            "---\n\n"
            "# Plugin\n\n"
            "## Name\n"
            "教育新结构\n\n"
            "## Purpose\n"
            "使用新教育目录结构。\n\n"
            "## Rules\n"
            "- 优先读取新目录。\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "education" / "modules" / "solve.md").write_text(
            "---\n"
            "id: solve\n"
            "type: module\n"
            "version: 1\n"
            "---\n\n"
            "# Module\n\n"
            "## Name\n"
            "新结构讲题\n\n"
            "## Goal\n"
            "用新结构推进讲题。\n\n"
            "## Applies To\n"
            "- 讲题\n\n"
            "## Response Structure\n"
            "- 先定位对象\n\n"
            "## Global Rules\n"
            "- 不串题\n\n"
            "## Interaction Policy\n"
            "- 按当前轮推进\n\n"
            "## Output Defaults\n"
            "- delivery_mode = speech_ui_dual\n"
            "- ui_mode = learning_card\n\n"
            "## Instructions\n"
            "- 使用新结构模块。\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "education" / "subjects" / "math.md").write_text(
            "---\n"
            "id: math\n"
            "type: subject\n"
            "version: 1\n"
            "---\n\n"
            "# Subject\n\n"
            "## Name\n"
            "新结构数学\n\n"
            "## Focus\n"
            "- 数学条件\n\n"
            "## Explanation Strategy\n"
            "- 先梳理条件\n\n"
            "## Common Mistakes\n"
            "- 忽略条件\n\n"
            "## Evidence Preference\n"
            "- 条件\n\n"
            "## UI Hints\n"
            "- ui_mode_default = math_steps\n\n"
            "## Instructions\n"
            "- 使用新结构学科。\n",
            encoding="utf-8",
        )
        (self.prompt_dir / "education" / "pedagogies" / "step_by_step.md").write_text(
            "---\n"
            "id: step_by_step\n"
            "type: style\n"
            "version: 1\n"
            "---\n\n"
            "# Style\n\n"
            "## Name\n"
            "新结构分步引导\n\n"
            "## Tone\n"
            "structured\n\n"
            "## Constraints\n"
            "- 不跳步\n\n"
            "## Output Adjustments\n"
            "- max_steps = 4\n\n"
            "## Instructions\n"
            "- 使用新结构 pedagogy。\n",
            encoding="utf-8",
        )

        catalog = EducationPromptCatalog(self.prompt_center)
        assets = catalog.load_assets(
            module="solve",
            subject="math",
            pedagogy="step_by_step",
        )

        self.assertEqual(assets.branch.name, "教育新结构")
        self.assertEqual(assets.module.name, "新结构讲题")
        self.assertEqual(assets.subject.name, "新结构数学")
        self.assertEqual(assets.pedagogy.name, "新结构分步引导")

    def test_real_education_assets_can_be_loaded_from_new_layout(self) -> None:
        real_root = Path.cwd() / "prompt-plugin"
        prompt_center = PromptCenter(PromptCenterConfig(prompt_dir=real_root))
        catalog = EducationPromptCatalog(prompt_center)

        assets = catalog.load_assets(
            module="solve",
            subject="math",
            pedagogy="step_by_step",
        )

        self.assertTrue(str(assets.branch.name).strip())
        self.assertTrue(str(assets.module.name).strip())
        self.assertTrue(str(assets.subject.name).strip())
        self.assertTrue(str(assets.pedagogy.name).strip())

    def test_migrated_education_assets_in_new_layout_no_longer_keep_rule_sections(self) -> None:
        real_root = Path.cwd() / "prompt-plugin"
        branch_text = (real_root / "education" / "branch.md").read_text(encoding="utf-8")
        solve_text = (real_root / "education" / "modules" / "solve.md").read_text(encoding="utf-8")
        check_text = (real_root / "education" / "modules" / "check.md").read_text(encoding="utf-8")

        self.assertNotIn("## Module Selection Rules", branch_text)
        self.assertNotIn("## Subject Selection Rules", solve_text)
        self.assertNotIn("## Style Selection Rules", solve_text)
        self.assertNotIn("## Subject Selection Rules", check_text)
        self.assertNotIn("## Style Selection Rules", check_text)


if __name__ == "__main__":
    unittest.main()
