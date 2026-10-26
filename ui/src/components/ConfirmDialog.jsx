import { useEffect, useRef } from "react";

/** A modal confirmation built on <dialog>: focus stays inside it and Escape closes it. */
export default function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel,
  busy,
  confirmDisabled = false,
  danger,
  onConfirm,
  onClose,
}) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal?.();
    if (!open && dialog.open) dialog.close?.();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby="modal-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      {open && (
        <>
          <h2 id="modal-title">{title}</h2>
          <div className="modal-body">{children}</div>
          <div className="modal-actions">
            <button type="button" className="quiet" disabled={busy} onClick={onClose}>
              {cancelLabel}
            </button>
            <button
              type="button"
              className={danger ? "danger" : undefined}
              disabled={busy || confirmDisabled}
              onClick={onConfirm}
            >
              {confirmLabel}
            </button>
          </div>
        </>
      )}
    </dialog>
  );
}
