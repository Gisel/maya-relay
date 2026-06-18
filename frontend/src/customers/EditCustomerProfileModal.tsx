import { FormEvent, useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import { ContactProfile } from "../api";

type EditCustomerProfileModalProps = {
  contact: ContactProfile | null;
  fallbackName: string;
  phone: string;
  open: boolean;
  isSaving: boolean;
  error: string;
  status: string;
  onClose: () => void;
  onSave: (payload: { displayName: string; notes: string }) => Promise<void>;
};

export function EditCustomerProfileModal({
  contact,
  fallbackName,
  phone,
  open,
  isSaving,
  error,
  status,
  onClose,
  onSave,
}: EditCustomerProfileModalProps) {
  const [displayName, setDisplayName] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!open) return;
    setDisplayName(contact?.displayName || contact?.name || fallbackName || "");
    setNotes(contact?.notes || "");
  }, [contact?.displayName, contact?.name, contact?.notes, fallbackName, open]);

  const hasChanges = useMemo(
    () => displayName !== (contact?.displayName || contact?.name || fallbackName || "") || notes !== (contact?.notes || ""),
    [contact?.displayName, contact?.name, contact?.notes, displayName, fallbackName, notes],
  );

  if (!open) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!contact || !hasChanges || isSaving) return;
    try {
      await onSave({ displayName, notes });
    } catch {
      // The parent owns the user-facing error state.
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation">
      <section aria-labelledby="edit-customer-profile-title" aria-modal="true" className="drawer-surface" role="dialog">
        <div className="drawer-header">
          <div>
            <h2 id="edit-customer-profile-title">Edit customer profile</h2>
            <p>Update the customer name and internal notes.</p>
          </div>
          <button aria-label="Close customer profile editor" className="drawer-close" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>
        <form className="drawer-form" onSubmit={handleSubmit}>
          <label>
            Name
            <input
              disabled={!contact || isSaving}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder={fallbackName}
              value={displayName}
            />
          </label>
          <label>
            Phone
            <input disabled value={phone} />
          </label>
          <label>
            Notes
            <textarea
              disabled={!contact || isSaving}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Add customer notes"
              rows={5}
              value={notes}
            />
          </label>
          {!contact && <p className="form-error">Could not load this customer profile yet.</p>}
          {error && <p className="form-error">{error}</p>}
          {status && <p className="app-success compact">{status}</p>}
          <div className="drawer-actions">
            <button className="ghost-button" disabled={isSaving} onClick={onClose} type="button">
              Cancel
            </button>
            <button className="send-button" disabled={!contact || !hasChanges || isSaving} type="submit">
              {isSaving ? "Saving..." : "Save profile"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
