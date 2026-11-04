import { Check } from "lucide-react";

/** A short row of numbered steps (booking: what you need → pick a time → confirm). `current` is 0-based. */
export default function Steps({ steps, current, label }) {
  return (
    <ol className="stepper" aria-label={label}>
      {steps.map((name, i) => {
        const state = i < current ? "done" : i === current ? "current" : "todo";
        return (
          <li key={name} className={state} aria-current={state === "current" ? "step" : undefined}>
            <span className="step-dot" aria-hidden="true">
              {state === "done" ? <Check size={14} strokeWidth={3} /> : i + 1}
            </span>
            <span>{name}</span>
          </li>
        );
      })}
    </ol>
  );
}
