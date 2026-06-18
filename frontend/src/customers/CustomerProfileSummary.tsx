import { FileText, Pencil, X } from "lucide-react";
import { useState } from "react";

type CustomerProfileSummaryProps = {
  name: string;
  phone: string;
  sessionCode?: string | null;
  notes?: string | null;
  isLoading?: boolean;
  canEdit: boolean;
  onEdit: () => void;
};

export function CustomerProfileSummary({
  name,
  phone,
  sessionCode,
  notes,
  isLoading = false,
  canEdit,
  onEdit,
}: CustomerProfileSummaryProps) {
  const [isNotesOpen, setIsNotesOpen] = useState(false);
  const hasNotes = Boolean(notes?.trim());

  return (
    <>
      <section className="context-section customer-profile-summary">
        <div className="context-section-heading">
          <h2>Customer Profile</h2>
          <div className="profile-action-buttons">
            {hasNotes && (
              <button
                aria-label="View customer notes"
                className="icon-button"
                onClick={() => setIsNotesOpen(true)}
                title="View customer notes"
                type="button"
              >
                <FileText size={15} />
              </button>
            )}
            <button
              aria-label="Edit customer profile"
              className="icon-button"
              disabled={!canEdit || isLoading}
              onClick={onEdit}
              title="Edit customer profile"
              type="button"
            >
              <Pencil size={15} />
            </button>
          </div>
        </div>
        <strong>{name}</strong>
        <p>{phone}</p>
        {sessionCode && <em>Session ID: #{sessionCode}</em>}
        {isLoading && <p className="panel-note compact">Loading customer profile...</p>}
      </section>

      {isNotesOpen && hasNotes && (
        <div className="drawer-backdrop" role="presentation">
          <section aria-labelledby="customer-notes-title" aria-modal="true" className="drawer-surface notes-surface" role="dialog">
            <div className="drawer-header">
              <div>
                <h2 id="customer-notes-title">Customer notes</h2>
                <p>{name}</p>
              </div>
              <button aria-label="Close customer notes" className="drawer-close" onClick={() => setIsNotesOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>
            <div className="customer-notes-full">{notes}</div>
          </section>
        </div>
      )}
    </>
  );
}
