import { Pencil } from "lucide-react";

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
  return (
    <section className="context-section customer-profile-summary">
      <div className="context-section-heading">
        <h2>Customer Profile</h2>
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
      <strong>{name}</strong>
      <p>{phone}</p>
      {sessionCode && <em>Session ID: #{sessionCode}</em>}
      {notes && <p className="profile-notes-preview">{notes}</p>}
      {isLoading && <p className="panel-note compact">Loading customer profile...</p>}
    </section>
  );
}
