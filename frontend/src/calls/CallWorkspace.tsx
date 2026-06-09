import { Clock, Phone } from "lucide-react";
import { CallConversationListItem, CallRecord } from "../api";
import { CallDetailsForm, CallDetailsPayload } from "./CallDetailsForm";
import {
  callDirectionLabel,
  callDuration,
  callTypeLabel,
  cleanPhone,
  formatDate,
  followUpLabel,
  outcomeLabel,
  workflowLabel,
} from "./callUtils";

function customerName(row: CallConversationListItem | null) {
  if (!row) return "No call selected";
  return row.customer.name || cleanPhone(row.customer.phone) || cleanPhone(row.latestCall.customerPhone) || "Unknown customer";
}

function callTime(call: CallRecord) {
  return formatDate(call.startedAt || call.createdAt);
}

function timelineTitle(call: CallRecord) {
  return `${callDirectionLabel(call.direction)} call`;
}

function callStatusTone(status?: string | null) {
  const normalized = (status || "").toLowerCase();
  if (normalized === "completed") return "complete";
  if (["busy", "canceled", "cancelled", "failed", "no-answer"].includes(normalized)) return "failed";
  if (["initiated", "in-progress", "queued", "ringing"].includes(normalized)) return "active";
  return "unknown";
}

export function CallWorkspace({
  calls,
  isLoadingDetail,
  onSaveCallDetails,
  onSelectCall,
  onTranscribeCall,
  selectedCall,
  selectedRow,
}: {
  calls: CallRecord[];
  isLoadingDetail: boolean;
  onSaveCallDetails: (callId: string, payload: CallDetailsPayload) => Promise<void>;
  onSelectCall: (callId: string) => void;
  onTranscribeCall: (callId: string) => Promise<void>;
  selectedCall: CallRecord | null;
  selectedRow: CallConversationListItem | null;
}) {
  if (!selectedRow) {
    return (
      <section className="call-workspace empty-call-workspace">
        <Phone size={28} />
        <h1>Select a call customer</h1>
        <p>Call activity, outcomes, notes, recap, and transcription will live here.</p>
      </section>
    );
  }

  const timeline = calls.length ? calls : [selectedRow.latestCall];
  const latestCall = selectedRow.latestCall;
  const editableCall = selectedCall || timeline[0] || latestCall;
  const duration = callDuration(latestCall);

  return (
    <section className="call-workspace">
      <header className="call-workspace-header">
        <div>
          <span className="workspace-kicker">Calls</span>
          <h1>{customerName(selectedRow)}</h1>
          <p>
            {cleanPhone(selectedRow.customer.phone || latestCall.customerPhone)}
            {selectedRow.conversation?.code && <span>Session ID: #{selectedRow.conversation.code}</span>}
          </p>
        </div>
        <span className={`workflow-pill workflow-${selectedRow.workflowStatus || "pending_follow_up"}`}>
          {workflowLabel(selectedRow.workflowStatus)}
        </span>
      </header>

      <div className="call-workspace-grid">
        <div className="call-workspace-main">
          <section className="call-summary-card">
            <div>
              <span className={`call-row-icon direction-${latestCall.direction || "unknown"}`}>
                <Phone size={17} />
              </span>
              <div>
                <h2>Latest call summary</h2>
                <p>{callTypeLabel(latestCall)} - {callDirectionLabel(latestCall.direction)}</p>
              </div>
            </div>
            <p className="call-summary-meta">
              <span
                aria-label={`Status: ${latestCall.status || "unknown"}`}
                className="call-summary-status"
                title={`Status: ${latestCall.status || "unknown"}`}
              >
                <span className={`call-summary-status-dot status-${callStatusTone(latestCall.status)}`} />
              </span>
              <span>
                <strong>Outcome:</strong> {outcomeLabel(latestCall.outcome)}
              </span>
              <span>
                <strong>Follow-up:</strong> {followUpLabel(latestCall.followUpStatus)}
              </span>
              <span>
                <strong>Started:</strong> {callTime(latestCall)}
              </span>
              {duration && (
                <span>
                  <strong>Duration:</strong> {duration}
                </span>
              )}
            </p>
          </section>

          <section className="call-timeline-section">
            <h2>Call timeline</h2>
            {isLoadingDetail && <p className="panel-note">Loading calls...</p>}
            <div className="call-timeline-list">
              {timeline.map((call) => (
                <button
                  className={[
                    "call-timeline-item",
                    `direction-${call.direction || "unknown"}`,
                    editableCall?.id === call.id ? "selected" : "",
                  ].filter(Boolean).join(" ")}
                  key={call.id}
                  onClick={() => onSelectCall(call.id)}
                  type="button"
                >
                  <span className={`call-row-icon direction-${call.direction || "unknown"}`}>
                    <Phone size={15} />
                  </span>
                  <span className="call-timeline-copy">
                    <strong>{timelineTitle(call)}</strong>
                    <em>{call.status || "unknown"}{call.outcome ? ` - ${outcomeLabel(call.outcome)}` : ""}</em>
                  </span>
                  <span className="call-timeline-meta">
                    {callTime(call)}
                    {callDuration(call) && (
                      <span>
                        <Clock size={12} />
                        {callDuration(call)}
                      </span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          </section>
        </div>

        <section className="call-editor-panel">
          <div className="call-editor-heading">
            <h2>Call details</h2>
            <p>{editableCall ? `${callTypeLabel(editableCall)} - ${cleanPhone(editableCall.customerPhone)}` : "Choose a call"}</p>
          </div>
          <CallDetailsForm
            call={editableCall}
            compactActions
            onSave={onSaveCallDetails}
            onTranscribe={onTranscribeCall}
          />
        </section>
      </div>
    </section>
  );
}
