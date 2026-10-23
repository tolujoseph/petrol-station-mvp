import { useEffect, useRef } from "react";
import { IconAlert, IconInfo } from "./Icons";

export default function ConfirmDialog({ dialog, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (dialog && !node.open) node.showModal();
    if (!dialog && node.open) node.close();
  }, [dialog]);

  const tone = dialog?.tone ?? "neutral";

  return (
    <dialog ref={ref} className={`confirm confirm--${tone}`} onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === ref.current) onClose(); }}>
      {dialog && (
        <div className="confirm__body">
          <span className="confirm__icon">{tone === "danger" ? <IconAlert size={22} /> : <IconInfo size={22} />}</span>
          <div>
            <h2 className="confirm__title">{dialog.title}</h2>
            <p className="confirm__text">{dialog.body}</p>
          </div>
        </div>
      )}
      <div className="confirm__actions">
        <button type="button" className="btn btn--ghost" onClick={onClose} autoFocus>{dialog?.cancelLabel ?? "Keep editing"}</button>
        <button type="button" className={`btn ${tone === "danger" ? "btn--danger" : "btn--secondary"}`} onClick={() => { const action = dialog?.onConfirm; onClose(); action?.(); }}>
          {dialog?.confirmLabel ?? "Confirm"}
        </button>
      </div>
    </dialog>
  );
}
