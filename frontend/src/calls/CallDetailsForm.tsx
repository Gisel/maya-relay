import { FormEvent, useEffect, useId, useState } from "react";
import { CallOutcome, CallRecord, FollowUpStatus, getCallRecordingUrl } from "../api";
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
  onGenerateRecap,
  onSave,
  onTranscribe,
}: {
  call: CallRecord | null;
  compactActions?: boolean;
  onCancel?: () => void;
  onGenerateRecap?: (callId: string) => Promise<void>;
  onSave: (callId: string, payload: CallDetailsPayload) => Promise<void>;
  onTranscribe?: (callId: string) => Promise<void>;
}) {
  const recapId = useId();
  const transcriptionId = useId();
  const [outcome, setOutcome] = useState<CallOutcome | null>(null);
  const [followUpStatus, setFollowUpStatus] = useState<FollowUpStatus>("none");
  const [notes, setNotes] = useState("");
  const [recap, setRecap] = useState("");
  const [transcription, setTranscription] = useState("");
  const [error, setError] = useState("");
  const [isGeneratingRecap, setIsGeneratingRecap] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);

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

  async function handleTranscribe() {
    if (!call || !onTranscribe) return;
    setIsTranscribing(true);
    setError("");
    try {
      await onTranscribe(call.id);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not transcribe the call recording.");
    } finally {
      setIsTranscribing(false);
    }
  }

  async function handleGenerateRecap() {
    if (!call || !onGenerateRecap) return;
    setIsGeneratingRecap(true);
    setError("");
    try {
      await onGenerateRecap(call.id);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not generate the call recap.");
    } finally {
      setIsGeneratingRecap(false);
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
            <a href={getCallRecordingUrl(call.id)} rel="noreferrer" target="_blank">Open recording</a>
            <audio controls preload="none" src={getCallRecordingUrl(call.id)}>
              <a href={getCallRecordingUrl(call.id)}>Open recording</a>
            </audio>
          </div>
        ) : (
          <p>No recording captured yet.</p>
        )}
      </div>

      <label>
        <span>Notes</span>
        <textarea disabled={!call || isSaving} onChange={(event) => setNotes(event.target.value)} rows={4} value={notes} />
      </label>

      <div className="call-textarea-field">
        <div className="call-transcription-heading">
          <label htmlFor={recapId}>Recap</label>
          {onGenerateRecap && (
            <button
              className="text-action-button"
              disabled={!call?.transcription || isGeneratingRecap || isSaving || isTranscribing}
              onClick={handleGenerateRecap}
              type="button"
            >
              {isGeneratingRecap ? "Generating..." : "Generate recap"}
            </button>
          )}
        </div>
        <textarea
          disabled={!call || isSaving}
          id={recapId}
          onChange={(event) => setRecap(event.target.value)}
          rows={4}
          value={recap}
        />
      </div>

      <div className="call-textarea-field">
        <div className="call-transcription-heading">
          <label htmlFor={transcriptionId}>Transcription</label>
          {onTranscribe && (
            <button
              className="text-action-button"
              disabled={!call?.recordingUrl || isSaving || isTranscribing}
              onClick={handleTranscribe}
              type="button"
            >
              {isTranscribing ? "Transcribing..." : "Transcribe recording"}
            </button>
          )}
        </div>
        <textarea
          disabled={!call || isSaving || isTranscribing}
          id={transcriptionId}
          onChange={(event) => setTranscription(event.target.value)}
          rows={6}
          value={transcription}
        />
      </div>

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
