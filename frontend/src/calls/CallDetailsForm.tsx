import { FormEvent, useEffect, useState } from "react";
import { CallOutcome, CallRecord, FollowUpStatus } from "../api";
import { CALL_OUTCOMES, FOLLOW_UP_STATUSES } from "./callUtils";

export type CallDetailsPayload = {
  outcome: CallOutcome | null;
  followUpStatus: FollowUpStatus;
  notes: string;
  recap: string;
  transcription: string;
};

export function CallDetailsForm({
  call,
  compactActions = false,
  onCancel,
  onSave,
}: {
  call: CallRecord | null;
  compactActions?: boolean;
  onCancel?: () => void;
  onSave: (callId: string, payload: CallDetailsPayload) => Promise<void>;
}) {
  const [outcome, setOutcome] = useState<CallOutcome | null>(null);
  const [followUpStatus, setFollowUpStatus] = useState<FollowUpStatus>("none");
  const [notes, setNotes] = useState("");
  const [recap, setRecap] = useState("");
  const [transcription, setTranscription] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!call) return;
    setOutcome((call.outcome as CallOutcome | null) || null);
    setFollowUpStatus(call.followUpStatus || "none");
    setNotes(call.notes || "");
    setRecap(call.recap || "");
    setTranscription(call.transcription || "");
    setError("");
  }, [call]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!call) return;
    setIsSaving(true);
    setError("");
    try {
      await onSave(call.id, { outcome, followUpStatus, notes, recap, transcription });
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not save call details.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className={`drawer-form call-details-form ${compactActions ? "is-inline" : ""}`} onSubmit={handleSubmit}>
      <div className="call-detail-select-row">
        <label>
          <span>Outcome</span>
          <select
            disabled={!call || isSaving}
            onChange={(event) => setOutcome(event.target.value ? (event.target.value as CallOutcome) : null)}
            value={outcome || ""}
          >
            <option value="">No outcome</option>
            {CALL_OUTCOMES.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>

        <label>
          <span>Follow-up status</span>
          <select
            disabled={!call || isSaving}
            onChange={(event) => setFollowUpStatus(event.target.value as FollowUpStatus)}
            value={followUpStatus}
          >
            {FOLLOW_UP_STATUSES.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="call-recording-status">
        <span>Recording</span>
        {call?.recordingUrl ? (
          <div>
            <strong>{recordingLabel(call.recordingStatus)}</strong>
            {call.recordingDurationSeconds != null && <em>{formatDuration(call.recordingDurationSeconds)}</em>}
            <a href={call.recordingUrl} rel="noreferrer" target="_blank">Open recording</a>
          </div>
        ) : (
          <p>No recording captured yet.</p>
        )}
      </div>

      <label>
        <span>Notes</span>
        <textarea disabled={!call || isSaving} onChange={(event) => setNotes(event.target.value)} rows={4} value={notes} />
      </label>

      <label>
        <span>Recap</span>
        <textarea disabled={!call || isSaving} onChange={(event) => setRecap(event.target.value)} rows={4} value={recap} />
      </label>

      <label>
        <span>Transcription</span>
        <textarea
          disabled={!call || isSaving}
          onChange={(event) => setTranscription(event.target.value)}
          rows={6}
          value={transcription}
        />
      </label>

      {error && <p className="form-error">{error}</p>}
      <div className="drawer-actions">
        {onCancel && (
          <button className="ghost-button" disabled={isSaving} onClick={onCancel} type="button">
            Cancel
          </button>
        )}
        <button className="send-button" disabled={!call || isSaving} type="submit">
          {isSaving ? "Saving..." : "Save call"}
        </button>
      </div>
    </form>
  );
}

function recordingLabel(status: string | null) {
  if (!status) return "Captured";
  return status
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
}
