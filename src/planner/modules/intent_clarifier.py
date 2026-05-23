from __future__ import annotations

from planner.schemas import ClarificationPlan, ClarificationQuestion, EventPOIGroup, Intent
from planner.vocab import ALLOWED_CATEGORIES


DO_NOT_CARE = "do_not_care"
BUDGET_OPTIONS = ["low", "medium", "high", DO_NOT_CARE]
BROAD_FOOD_CATEGORIES = {"Restaurants", "Food", "Breakfast & Brunch"}
FOOD_GOALS = {"breakfast", "lunch", "dinner"}
CUISINE_OPTIONS = [
    "Chinese",
    "Japanese",
    "Italian",
    "Mexican",
    "American (New)",
    "American (Traditional)",
    "Seafood",
    "Thai",
    "Indian",
    "Korean",
    "Vietnamese",
    DO_NOT_CARE,
]


def build_clarification_plan(intent: Intent) -> ClarificationPlan:
    questions: list[ClarificationQuestion] = []

    for event_index, event in enumerate(intent.events, start=1):
        event_label = event.name or event.goal or f"event {event_index}"
        if event.budget_level == "unknown":
            questions.append(
                ClarificationQuestion(
                    id=f"event_{event_index}_budget_level",
                    event_index=event_index,
                    field="budget_level",
                    question=f"Budget preference for {event_label}?",
                    options=BUDGET_OPTIONS,
                )
            )

    return ClarificationPlan(questions=questions)


def build_poi_refinement_plan(intent: Intent, poi_groups: list[EventPOIGroup]) -> ClarificationPlan:
    questions: list[ClarificationQuestion] = []
    event_by_index = {index: event for index, event in enumerate(intent.events, start=1)}
    valid_cuisine_options = [option for option in CUISINE_OPTIONS if option != DO_NOT_CARE and option in ALLOWED_CATEGORIES]

    for group in poi_groups:
        event = event_by_index.get(group.event_index)
        if event is None or not _needs_cuisine_refinement(event.goal, event.categories):
            continue
        available_options = [
            option
            for option in valid_cuisine_options
            if any(option in poi.categories for poi in group.pois)
        ]
        if len(available_options) >= 2:
            event_label = event.name or event.goal or f"event {group.event_index}"
            questions.append(
                ClarificationQuestion(
                    id=f"event_{group.event_index}_cuisine_category",
                    event_index=group.event_index,
                    field="cuisine_category",
                    question=f"What kind of food for {event_label}?",
                    options=available_options + [DO_NOT_CARE],
                )
            )

    return ClarificationPlan(questions=questions)


def apply_clarification_answers(
    intent: Intent,
    answers: dict[str, str],
    *,
    plan: ClarificationPlan | None = None,
) -> Intent:
    events = [event.model_dump() for event in intent.events]
    active_plan = plan or build_clarification_plan(intent)
    question_by_id = {question.id: question for question in active_plan.questions}

    for question_id, answer in answers.items():
        question = question_by_id.get(question_id)
        if question is None or answer == DO_NOT_CARE or answer not in question.options:
            continue
        event_payload = events[question.event_index - 1]
        if question.field == "budget_level":
            event_payload["budget_level"] = answer
        elif question.field == "cuisine_category":
            existing_categories = list(event_payload.get("categories", []) or [])
            refined_categories = [category for category in existing_categories if category not in BROAD_FOOD_CATEGORIES]
            if answer not in refined_categories:
                refined_categories.append(answer)
            event_payload["categories"] = refined_categories

    return Intent.model_validate({**intent.model_dump(), "events": events})


def _needs_cuisine_refinement(goal: str, categories: list[str]) -> bool:
    if any(category in CUISINE_OPTIONS and category != DO_NOT_CARE for category in categories):
        return False
    return goal in FOOD_GOALS or any(category in BROAD_FOOD_CATEGORIES for category in categories)
