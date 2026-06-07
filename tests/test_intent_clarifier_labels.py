from planner.modules.intent_clarifier import build_clarification_plan
from planner.schemas import Intent


def test_budget_clarification_uses_readable_chinese_question() -> None:
    intent = Intent(
        raw_query="coffee",
        events=[{"name": "咖啡休息", "goal": "coffee", "budget_level": "unknown"}],
    )

    plan = build_clarification_plan(intent)

    assert plan.questions[0].question == "咖啡休息 的预算范围"
