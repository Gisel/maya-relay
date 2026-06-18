import { CheckCircle2, Download, FileText, Loader2, MessageSquareText, XCircle } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  CustomerActionRequest,
  PublicProofRequest,
  approvePublicProofRequest,
  getPublicProofRequest,
  requestPublicProofChanges,
} from "../api";
import logoMaya from "../assets/logo-maya.jpg";

type PublicProofPageProps = {
  token: string;
};

type SubmissionMode = "approve" | "changes" | "";

export function PublicProofPage({ token }: PublicProofPageProps) {
  const [proofRequest, setProofRequest] = useState<PublicProofRequest | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [changeComment, setChangeComment] = useState("");
  const [submissionMode, setSubmissionMode] = useState<SubmissionMode>("");

  useEffect(() => {
    let ignore = false;
    setLoadError("");
    getPublicProofRequest(token)
      .then((response) => {
        if (!ignore) setProofRequest(response.proofRequest);
      })
      .catch((error) => {
        if (ignore) return;
        if (error instanceof ApiError && error.status === 404) {
          setLoadError("This proof link is unavailable.");
        } else {
          setLoadError(error instanceof Error ? error.message : "Could not load this proof.");
        }
      });
    return () => {
      ignore = true;
    };
  }, [token]);

  const proofFile = useMemo(() => proofRequest?.files.find((file) => file.role === "proof") || proofRequest?.files[0], [proofRequest]);
  const proofUrl = proofFile?.publicUrl || proofFile?.externalUrl || "";
  const isPending = proofRequest?.status === "pending";
  const statusCopy = statusMessage(proofRequest);

  async function submitApproval() {
    if (!proofRequest || !isPending) return;
    setSubmissionMode("approve");
    setActionError("");
    try {
      const response = await approvePublicProofRequest(token);
      setProofRequest((current) => mergeRequestStatus(current, response.proofRequest, "approved"));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not approve this proof.");
    } finally {
      setSubmissionMode("");
    }
  }

  async function submitChanges(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!proofRequest || !isPending) return;
    const comment = changeComment.trim();
    if (!comment) {
      setActionError("Please describe the changes you need.");
      return;
    }
    setSubmissionMode("changes");
    setActionError("");
    try {
      const response = await requestPublicProofChanges(token, comment);
      setProofRequest((current) => mergeRequestStatus(current, response.proofRequest, "changes_requested", comment));
      setChangeComment("");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not send your requested changes.");
    } finally {
      setSubmissionMode("");
    }
  }

  if (loadError) {
    return (
      <main className="public-proof-shell">
        <section className="public-proof-card public-proof-message-card">
          <BrandHeader />
          <XCircle size={42} />
          <h1>Proof link unavailable</h1>
          <p>{loadError}</p>
        </section>
      </main>
    );
  }

  if (!proofRequest) {
    return (
      <main className="public-proof-shell">
        <section className="public-proof-card public-proof-message-card">
          <BrandHeader />
          <Loader2 className="public-proof-spinner" size={34} />
          <p>Loading proof...</p>
        </section>
      </main>
    );
  }

  return (
    <main className="public-proof-shell">
      <section className="public-proof-card">
        <BrandHeader />

        <div className="public-proof-heading">
          <div>
            <p className="section-kicker">Proof review</p>
            <h1>{proofRequest.title || "Proof approval"}</h1>
          </div>
          <span className={`public-proof-status status-${proofRequest.status}`}>{statusCopy.label}</span>
        </div>

        <ProofPreview contentType={proofFile?.contentType || ""} filename={proofFile?.originalFilename || "Proof file"} proofUrl={proofUrl} />

        <div className="public-proof-status-note">
          {statusCopy.icon}
          <p>{statusCopy.body}</p>
        </div>

        {isPending ? (
          <div className="public-proof-actions">
            {actionError && <p className="form-error">{actionError}</p>}
            <button className="public-proof-approve" disabled={Boolean(submissionMode)} onClick={submitApproval} type="button">
              <CheckCircle2 size={18} />
              {submissionMode === "approve" ? "Approving..." : "Approve proof"}
            </button>

            <form className="public-proof-changes-form" onSubmit={submitChanges}>
              <label>
                <span>Need changes?</span>
                <textarea
                  disabled={Boolean(submissionMode)}
                  onChange={(event) => setChangeComment(event.target.value)}
                  placeholder="Tell us what needs to change before approval."
                  rows={4}
                  value={changeComment}
                />
              </label>
              <button className="public-proof-change-button" disabled={Boolean(submissionMode)} type="submit">
                <MessageSquareText size={18} />
                {submissionMode === "changes" ? "Sending..." : "Request changes"}
              </button>
            </form>
          </div>
        ) : null}
      </section>
    </main>
  );
}

function BrandHeader() {
  return (
    <div className="public-proof-brand">
      <img alt="Maya Graphics and Signs" src={logoMaya} />
      <strong>MAYA <span>RELAY</span></strong>
    </div>
  );
}

function ProofPreview({ contentType, filename, proofUrl }: { contentType: string; filename: string; proofUrl: string }) {
  if (!proofUrl) {
    return (
      <div className="public-proof-preview public-proof-preview-empty">
        <FileText size={32} />
        <p>The proof file is not available.</p>
      </div>
    );
  }

  const isImage = contentType.toLowerCase().startsWith("image/");
  const isPdf = contentType.toLowerCase() === "application/pdf";

  return (
    <div className="public-proof-preview">
      {isImage ? <img alt={filename} src={proofUrl} /> : null}
      {isPdf ? <iframe src={proofUrl} title={filename} /> : null}
      {!isImage && !isPdf ? (
        <div className="public-proof-file">
          <FileText size={36} />
          <p>{filename}</p>
        </div>
      ) : null}
      <a href={proofUrl} rel="noreferrer" target="_blank">
        <Download size={17} />
        Open proof file
      </a>
    </div>
  );
}

function statusMessage(proofRequest: PublicProofRequest | null) {
  if (!proofRequest) {
    return { label: "Loading", body: "Loading proof request.", icon: <Loader2 size={18} /> };
  }
  if (proofRequest.status === "approved") {
    return {
      label: "Approved",
      body: "This proof has been approved for production.",
      icon: <CheckCircle2 size={18} />,
    };
  }
  if (proofRequest.status === "changes_requested") {
    const changeEvent = [...proofRequest.events].reverse().find((event) => event.type === "changes_requested");
    return {
      label: "Changes requested",
      body: changeEvent?.comment ? `Changes requested: ${changeEvent.comment}` : "Changes have been requested for this proof.",
      icon: <MessageSquareText size={18} />,
    };
  }
  return {
    label: "Pending review",
    body: "Review the proof, then approve it for production or request changes.",
    icon: <FileText size={18} />,
  };
}

function mergeRequestStatus(
  current: PublicProofRequest | null,
  update: CustomerActionRequest,
  eventType: string,
  comment: string | null = null,
): PublicProofRequest | null {
  if (!current) return null;
  return {
    ...current,
    ...update,
    events: [
      ...current.events,
      {
        id: `local-${eventType}-${Date.now()}`,
        type: eventType,
        comment,
        metadata: {},
        createdAt: new Date().toISOString(),
      },
    ],
  };
}
