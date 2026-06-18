import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";
import { ApiError, getOperationalStatus, OperationalStatusResponse } from "../api";
import { cleanPhone, relativeDate } from "../calls/callUtils";

function issueTitle(kind: string) {
  if (kind === "recording_failed") return "Recording failed";
  if (kind === "recording_missing") return "Recording missing";
  if (kind === "transcription_missing") return "Needs transcription";
  if (kind === "recap_missing") return "Needs recap";
  return "Call attention";
}

function customerLabel(name: string | null, phone: string | null) {
  return name || cleanPhone(phone || "") || "Unknown customer";
}

export function OperationalStatusView() {
  const [status, setStatus] = useState<OperationalStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setIsLoading(true);
    setError("");
    try {
      setStatus(await getOperationalStatus());
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setError("Session expired. Please sign in again.");
      } else {
        setError(error instanceof Error ? error.message : "Could not load operational status.");
      }
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const hasIssues = Boolean(status?.summary.total);

  return (
    <section className="settings-section operational-status">
      <div className="settings-section-heading">
        <div>
          <h3>Operational status</h3>
          <p>Recent Twilio sends, recordings, transcriptions, and recaps.</p>
        </div>
        <button className="mini-action-button" disabled={isLoading} onClick={refresh} type="button">
          <RefreshCw size={15} />
          Refresh
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}
      {!error && isLoading && !status && <p className="panel-note compact">Loading operational status...</p>}
      {!error && status && !hasIssues && (
        <div className="status-empty">
          <CheckCircle2 size={18} />
          <span>No recent operational issues.</span>
        </div>
      )}
      {status && hasIssues && (
        <>
          <div className="status-summary-grid">
            <span>
              <strong>{status.summary.messageFailures}</strong>
              Failed sends
            </span>
            <span>
              <strong>{status.summary.callAttention}</strong>
              Call items
            </span>
          </div>

          {status.messageFailures.length > 0 && (
            <div className="status-issue-group">
              <h4>Failed Twilio sends</h4>
              {status.messageFailures.map((issue) => (
                <article className="status-issue-card" key={issue.id}>
                  <header>
                    <AlertTriangle size={15} />
                    <strong>{customerLabel(issue.customerName, issue.customerPhone)}</strong>
                    <em>{relativeDate(issue.createdAt)}</em>
                  </header>
                  <p>{issue.bodyPreview || "No message body"}</p>
                  <small>
                    {issue.deliveryStatus || "failed"}
                    {issue.deliveryErrorCode ? ` · ${issue.deliveryErrorCode}` : ""}
                    {issue.conversationCode ? ` · #${issue.conversationCode}` : ""}
                  </small>
                  <span>{issue.hint}</span>
                </article>
              ))}
            </div>
          )}

          {status.callAttention.length > 0 && (
            <div className="status-issue-group">
              <h4>Call recording and AI</h4>
              {status.callAttention.map((issue) => (
                <article className="status-issue-card" key={`${issue.kind}-${issue.id}`}>
                  <header>
                    <AlertTriangle size={15} />
                    <strong>{issueTitle(issue.kind)}</strong>
                    <em>{relativeDate(issue.completedAt || issue.startedAt || issue.createdAt)}</em>
                  </header>
                  <p>{customerLabel(issue.customerName, issue.customerPhone)}</p>
                  <small>
                    {issue.status || "unknown"}
                    {issue.recordingStatus ? ` · recording ${issue.recordingStatus}` : ""}
                    {issue.conversationCode ? ` · #${issue.conversationCode}` : ""}
                  </small>
                  <span>{issue.hint}</span>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
