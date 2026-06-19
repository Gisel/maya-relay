import { CheckCircle2, Clock3, FileCheck2, FolderUp, XCircle } from "lucide-react";
import { CustomerActionRequest } from "../api";

type CustomerActionRequestsPanelProps = {
  cancelingRequestId?: string;
  onCancelRequest: (requestId: string) => void;
  requests: CustomerActionRequest[];
};

const STATUS_LABELS: Record<string, string> = {
  approved: "Approved",
  canceled: "Canceled",
  changes_requested: "Changes requested",
  expired: "Expired",
  pending: "Pending",
  submitted: "Submitted",
};

export function CustomerActionRequestsPanel({
  cancelingRequestId = "",
  onCancelRequest,
  requests,
}: CustomerActionRequestsPanelProps) {
  const visibleRequests = requests.slice(0, 8);

  return (
    <div className="customer-action-requests">
      {visibleRequests.length === 0 ? (
        <p className="customer-action-empty">No proof or asset requests yet.</p>
      ) : (
        visibleRequests.map((request) => (
          <article className={`customer-action-card status-${request.status}`} key={request.id}>
            <div className="customer-action-card-header">
              <div className="customer-action-title">
                {request.type === "assets" ? <FolderUp size={16} /> : <FileCheck2 size={16} />}
                <strong>{request.title || defaultRequestTitle(request.type)}</strong>
              </div>
              <span className={`customer-action-status status-${request.status}`}>
                {request.status === "pending" ? <Clock3 size={13} /> : <CheckCircle2 size={13} />}
                {STATUS_LABELS[request.status] || request.status}
              </span>
            </div>
            <p className="customer-action-meta">
              {request.type === "assets" ? "Assets" : "Proof"} request
              {request.createdAt ? ` - ${formatRequestDate(request.createdAt)}` : ""}
            </p>
            {request.operatorNote && <p className="customer-action-note">{request.operatorNote}</p>}
            {request.status === "pending" && (
              <button
                className="customer-action-cancel"
                disabled={cancelingRequestId === request.id}
                onClick={() => onCancelRequest(request.id)}
                type="button"
              >
                <XCircle size={14} />
                {cancelingRequestId === request.id ? "Canceling" : "Cancel request"}
              </button>
            )}
          </article>
        ))
      )}
    </div>
  );
}

function defaultRequestTitle(type: string) {
  return type === "assets" ? "Asset upload" : "Proof approval";
}

function formatRequestDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recently";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}
