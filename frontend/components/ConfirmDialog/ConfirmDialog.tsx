"use client";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  onCancel,
  onConfirm
}: ConfirmDialogProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 id="confirm-title">{title}</h2>
        <p>{message}</p>
        <div className="button-row">
          <button className="button danger" type="button" onClick={onConfirm}>
            {confirmLabel}
          </button>
          <button className="button ghost" type="button" onClick={onCancel}>
            Keep
          </button>
        </div>
      </div>
    </div>
  );
}
