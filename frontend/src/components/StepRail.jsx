import { IconCalendar, IconCheckSquare, IconLedger, IconPump, IconTank } from "./Icons";
import { STEPS } from "./steps";

const ICONS = {
  "step-date": IconCalendar,
  "step-pumps": IconPump,
  "step-tanks": IconTank,
  "step-ledger": IconLedger,
  "step-submit": IconCheckSquare,
};


export default function StepRail({ activeId, done, onJump }) {
  return (
    <ol className="steps" aria-label="Entry progress">
      {STEPS.map((step, index) => {
        const Icon = ICONS[step.id];
        const complete = done[step.id];
        return (
          <li key={step.id}>
            <button type="button" className={`steps__item ${activeId === step.id ? "is-active" : ""} ${complete ? "is-done" : ""}`} onClick={() => onJump(step.id)} aria-current={activeId === step.id ? "step" : undefined}>
              <span className="steps__num">{complete ? <IconCheckSquare size={14} /> : String(index + 1).padStart(2, "0")}</span>
              <span className="steps__label">{step.label}</span>
              <Icon size={16} className="steps__icon" />
            </button>
          </li>
        );
      })}
    </ol>
  );
}
