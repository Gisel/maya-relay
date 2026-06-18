import { DragEvent, FormEvent, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { FileCheck2, Send, Upload, X } from "lucide-react";

import { Channel } from "../api";

const PROOF_MAX_FILE_SIZE_BYTES = 32 * 1024 * 1024;
const PROOF_ALLOWED_CONTENT_TYPES = new Set([
  "application/pdf",
  "image/gif",
  "image/jpeg",
  "image/png",
  "image/tiff",
  "image/webp",
]);
const PROOF_ALLOWED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff"];

type ProofRequestPayload = {
  proofFile: File;
  title: string;
  customerMessage: string;
  operatorNote: string;
};

type ProofRequestModalProps = {
  channel: Channel;
  customerName: string;
  customerPhone: string;
  error: string;
  isSending: boolean;
  onClose: () => void;
  onSend: (payload: ProofRequestPayload) => Promise<void>;
  open: boolean;
};

export function ProofRequestModal({
  channel,
  customerName,
  customerPhone,
  error,
  isSending,
  onClose,
  onSend,
  open,
}: ProofRequestModalProps) {
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [isDraggingProofFile, setIsDraggingProofFile] = useState(false);
  const [title, setTitle] = useState("Proof approval");
  const [customerMessage, setCustomerMessage] = useState("");
  const [operatorNote, setOperatorNote] = useState("");
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    if (!open) return;
    setProofFile(null);
    setIsDraggingProofFile(false);
    setTitle("Proof approval");
    setCustomerMessage("");
    setOperatorNote("");
    setLocalError("");
  }, [open]);

  if (!open) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError("");
    if (!proofFile) {
      setLocalError("Choose or drop a proof file before sending.");
      return;
    }
    await onSend({
      proofFile,
      title: title.trim(),
      customerMessage: customerMessage.trim(),
      operatorNote: operatorNote.trim(),
    });
  }

  function handleDragOver(event: DragEvent<HTMLSpanElement>) {
    event.preventDefault();
    if (isSending) return;
    setIsDraggingProofFile(true);
  }

  function handleDragLeave(event: DragEvent<HTMLSpanElement>) {
    event.preventDefault();
    setIsDraggingProofFile(false);
  }

  function handleDrop(event: DragEvent<HTMLSpanElement>) {
    event.preventDefault();
    setIsDraggingProofFile(false);
    if (isSending) return;
    const file = event.dataTransfer.files.item(0);
    if (file) {
      selectProofFile(file);
    }
  }

  function selectProofFile(file: File | null) {
    if (!file) {
      setProofFile(null);
      return;
    }
    const validationError = proofFileValidationError(file);
    if (validationError) {
      setProofFile(null);
      setLocalError(validationError);
      return;
    }
    setProofFile(file);
    setLocalError("");
  }

  return createPortal(
    <div className="drawer-backdrop" role="presentation">
      <section aria-labelledby="proof-request-title" aria-modal="true" className="drawer-surface proof-request-surface" role="dialog">
        <div className="drawer-header">
          <div>
            <h2 id="proof-request-title">Send proof request</h2>
            <p>{customerName} receives a {channel === "whatsapp" ? "WhatsApp" : "text"} link to approve or request changes.</p>
          </div>
          <button aria-label="Close proof request" className="drawer-close" disabled={isSending} onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>

        <form className="drawer-form proof-request-form" onSubmit={handleSubmit}>
          <div className="proof-recipient-card">
            <FileCheck2 size={18} />
            <div>
              <strong>{customerName}</strong>
              <span>{customerPhone}</span>
            </div>
          </div>

          <label className={`file-picker-label ${isDraggingProofFile ? "is-dragging-file" : ""}`}>
            <span>Proof file</span>
            <span className="file-picker-control" onDragLeave={handleDragLeave} onDragOver={handleDragOver} onDrop={handleDrop}>
              <span className="file-picker-button">
                <Upload size={16} />
                Choose file
              </span>
              <span className={`file-picker-name ${proofFile ? "has-file" : ""}`}>
                {proofFile ? proofFile.name : "Drop a proof here or choose a file"}
              </span>
            </span>
            <input
              autoFocus
              accept="image/*,.pdf"
              className="file-picker-input"
              disabled={isSending}
              onChange={(event) => {
                selectProofFile(event.target.files?.[0] ?? null);
              }}
              type="file"
            />
          </label>

          <label>
            <span>Title</span>
            <input
              disabled={isSending}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Proof approval"
              type="text"
              value={title}
            />
          </label>

          <label>
            <span>Customer message</span>
            <textarea
              disabled={isSending}
              onChange={(event) => setCustomerMessage(event.target.value)}
              placeholder="Optional note before the review link"
              rows={3}
              value={customerMessage}
            />
          </label>

          <label>
            <span>Internal note</span>
            <textarea
              disabled={isSending}
              onChange={(event) => setOperatorNote(event.target.value)}
              placeholder="Optional note for Maya Relay"
              rows={2}
              value={operatorNote}
            />
          </label>

          {(localError || error) && <p className="form-error">{localError || error}</p>}

          <div className="drawer-actions">
            <button className="ghost-button" disabled={isSending} onClick={onClose} type="button">
              Cancel
            </button>
            <button className="send-button" disabled={!proofFile || isSending} type="submit">
              <Send size={17} />
              {isSending ? "Sending..." : "Send request"}
            </button>
          </div>
        </form>
      </section>
    </div>,
    document.body,
  );
}

function proofFileValidationError(file: File) {
  if (file.size > PROOF_MAX_FILE_SIZE_BYTES) {
    return "Proof file must be 32 MB or smaller.";
  }
  const contentType = file.type.toLowerCase();
  const filename = file.name.toLowerCase();
  const hasAllowedExtension = PROOF_ALLOWED_EXTENSIONS.some((extension) => filename.endsWith(extension));
  if ((contentType && !PROOF_ALLOWED_CONTENT_TYPES.has(contentType)) || (!contentType && !hasAllowedExtension)) {
    return "Proof file must be a PDF or image file: PDF, JPG, PNG, GIF, WebP, or TIFF.";
  }
  return "";
}
