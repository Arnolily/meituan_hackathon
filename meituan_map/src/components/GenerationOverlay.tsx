import { useAppStore } from "../store/appStore";
import type { GenerationStage } from "../types";

const STEPS: GenerationStage[] = ["intent_parsing", "poi_filtering", "route_comparing", "route_generating", "route_ready"];

export function GenerationOverlay() {
  const stage = useAppStore((s) => s.generationStage);
  const text = useAppStore((s) => s.generationProgressText);

  if (stage === "idle" || stage === "route_ready") return null;
  const index = Math.max(0, STEPS.indexOf(stage));

  return (
    <section className="generation-overlay" aria-live="polite">
      <div className="generation-spinner" aria-hidden />
      <p>{text}</p>
      <div className="generation-steps">
        {STEPS.slice(0, 4).map((item, itemIndex) => (
          <span key={item} className={itemIndex <= index ? "is-active" : ""} />
        ))}
      </div>
    </section>
  );
}
