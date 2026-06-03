import { useEffect, useMemo, useState } from "react";
import { useAppStore } from "../store/appStore";

function optionLabel(value: string) {
  if (value === "low") return "低预算";
  if (value === "medium") return "中等预算";
  if (value === "high") return "高预算";
  if (value === "do_not_care") return "无偏好";
  const labels: Record<string, string> = {
    Chinese: "中餐",
    Japanese: "日料",
    Italian: "意餐",
    Mexican: "墨西哥菜",
    "American (New)": "新式美餐",
    "American (Traditional)": "传统美餐",
    Seafood: "海鲜",
    Thai: "泰餐",
    Indian: "印度菜",
    Korean: "韩餐",
    Vietnamese: "越南菜",
    Restaurants: "餐厅",
    Food: "餐饮",
    "Breakfast & Brunch": "早午餐",
    "Coffee & Tea": "咖啡或茶饮",
    Cafes: "咖啡馆",
    Museums: "博物馆",
    "Art Museums": "艺术博物馆",
    "Art Galleries": "画廊或艺术空间",
    Parks: "公园",
    "Shopping Centers": "购物中心",
    "Arts & Entertainment": "文化娱乐空间",
    Arcades: "游戏厅",
    "Active Life": "户外活动",
    Bars: "酒吧",
    "Beer Gardens": "啤酒花园",
    "Beer Bar": "啤酒吧",
    "Cocktail Bars": "鸡尾酒吧",
    Vegetarian: "素食",
    Vegan: "纯素",
    Tacos: "塔可",
    Bakeries: "烘焙店",
    Desserts: "甜品",
    "Juice Bars & Smoothies": "果汁和冰沙",
    "Ice Cream & Frozen Yogurt": "冰淇淋和冻酸奶",
  };
  return labels[value] ?? value.replace(/ & /g, "和");
}

function questionLabel(question: string) {
  const cleaned = question
    .replace("Budget preference for", "预算偏好")
    .replace("What kind of food for", "餐饮类型")
    .replace("What kind of POI for", "地点类型")
    .replace("?", "");
  return cleaned
    .replace("Meal", "用餐")
    .replace("Coffee", "咖啡")
    .replace("Dinner", "晚餐")
    .replace("Lunch", "午餐")
    .replace("Park", "公园")
    .replace("Museum", "博物馆")
    .replace("Art", "艺术空间")
    .replace("Shopping", "购物")
    .replace("Activity", "活动")
    .replace("event_", "第 ")
    .replace(/(\d+)$/, "$1 段");
}

export function BackendClarificationDialog() {
  const clarification = useAppStore((s) => s.backendClarification);
  const submitBackendClarification = useAppStore((s) => s.submitBackendClarification);
  const clearBackendClarification = useAppStore((s) => s.clearBackendClarification);
  const [submitting, setSubmitting] = useState(false);

  const initialAnswers = useMemo(() => {
    const answers: Record<string, string> = {};
    clarification?.questions.forEach((question) => {
      answers[question.id] = question.options.includes("do_not_care") ? "do_not_care" : question.options[0] ?? "";
    });
    return answers;
  }, [clarification]);
  const [answers, setAnswers] = useState<Record<string, string>>(initialAnswers);

  useEffect(() => {
    setAnswers(initialAnswers);
  }, [initialAnswers]);

  if (!clarification) return null;

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await submitBackendClarification({ ...initialAnswers, ...answers });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="intent-review-shell" aria-label="补充路线偏好">
      <div className="intent-review-dialog backend-clarification-dialog" role="dialog" aria-modal="true">
        <p className="intent-confirm__eyebrow">还需要确认</p>
        <h2>补充每一段行程的偏好。</h2>
        <p className="intent-review-dialog__summary">回答后，我会继续挑选地点并生成路线。</p>

        <div className="backend-clarification-list">
          {clarification.questions.map((question) => (
            <label className="backend-clarification-question" key={question.id}>
              <span>{questionLabel(question.question)}</span>
              <select
                value={answers[question.id] ?? initialAnswers[question.id] ?? ""}
                onChange={(event) => setAnswers((current) => ({ ...current, [question.id]: event.target.value }))}
              >
                {question.options.map((option) => (
                  <option value={option} key={option}>
                    {optionLabel(option)}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>

        <div className="intent-review-actions">
          <button type="button" className="btn-secondary" onClick={clearBackendClarification} disabled={submitting}>
            稍后再说
          </button>
          <button type="button" className="btn-primary" onClick={() => void handleSubmit()} disabled={submitting}>
            {submitting ? "继续生成中..." : "继续生成路线"}
          </button>
        </div>
      </div>
    </section>
  );
}
