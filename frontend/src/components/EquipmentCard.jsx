import { IconPump, IconTank } from "./Icons";

export default function EquipmentCard({ type, item, selected, value, disabled, onToggle, onChange, children }) {
  const isPump = type === "pump";
  const inputId = `${type}-${item.id}`;
  const entered = String(value ?? "").trim() !== "";
  const grade = String(item.product_type || "").toLowerCase();

  return (
    <article className={`unit unit--${grade} ${selected ? "is-on" : "is-off"}`}>
      <header className="unit__head">
        <span className="unit__glyph">{isPump ? <IconPump size={22} /> : <IconTank size={22} />}</span>
        <div className="unit__id">
          <h4 className="unit__name">{item.label}</h4>
          <span className={`grade grade--${grade}`}>{item.product_type}</span>
        </div>
        <label className="switch">
          <input type="checkbox" role="switch" checked={selected} disabled={disabled} onChange={(event) => onToggle(event.target.checked)} />
          <span className="switch__track" aria-hidden="true"><span className="switch__thumb" /></span>
          <span className="switch__label">{selected ? "In service today" : "Not used today"}</span>
        </label>
      </header>

      {selected && (
        <div className="unit__body">
          <div className="readout">
            <label htmlFor={inputId} className="readout__label">{isPump ? "Closing meter reading" : "Closing dip reading"}</label>
            <div className={`readout__screen ${entered ? "has-value" : ""}`}>
              <input id={inputId} className="readout__input" type="number" inputMode="decimal" min="0" step="0.01" placeholder="0.00" value={value ?? ""} onChange={(event) => onChange(event.target.value)} disabled={disabled} required />
              <span className="readout__unit">{isPump ? "L" : "DIP"}</span>
            </div>
          </div>
          {children}
        </div>
      )}
    </article>
  );
}
