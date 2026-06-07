import { useMemo, useState } from "react";
import { useAppStore } from "../store/appStore";
import { optionLabel, questionLabel } from "../utils/clarificationLabels";

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
        <h2>补充这次路线的偏好</h2>
        <p className="intent-review-dialog__summary">这些选项会直接影响地点筛选和路线排序；不确定的项目可以保持“不特别限制”。</p>

        <div className="backend-clarification-list">
          {clarification.questions.map((question) => (
            <label className="backend-clarification-question" key={question.id}>
              <span>{questionLabel(question.question, question.field, question.event_index)}</span>
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
          <button
            type="button"
            className="btn-secondary"
            onClick={clearBackendClarification}
            disabled={submitting}
          >
            稍后再说
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => void handleSubmit()}
            disabled={submitting}
          >
            {submitting ? "继续生成中..." : "应用偏好并生成路线"}
          </button>
        </div>
      </div>
    </section>
  );
}
