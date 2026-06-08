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
      <fieldset disabled={!call || isSaving}>
        <legend>Outcome</legend>
        <div className="button-grid outcome-grid">
          {CALL_OUTCOMES.map((item) => (
            <button
              className={outcome === item.value ? "is-active" : ""}
              key={item.value}
              onClick={() => setOutcome(item.value)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset disabled={!call || isSaving}>
        <legend>Follow-up status</legend>
        <div className="button-grid follow-up-grid">
          {FOLLOW_UP_STATUSES.map((item) => (
            <button
              className={followUpStatus === item.value ? "is-active" : ""}
              key={item.value}
              onClick={() => setFollowUpStatus(item.value)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
      </fieldset>

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
