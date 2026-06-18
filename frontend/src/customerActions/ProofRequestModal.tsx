import { FormEvent, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { FileCheck2, Send, X } from "lucide-react";

import { Channel } from "../api";

type ProofRequestPayload = {
  proofUrl: string;
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
  const [proofUrl, setProofUrl] = useState("");
  const [title, setTitle] = useState("Proof approval");
  const [customerMessage, setCustomerMessage] = useState("");
  const [operatorNote, setOperatorNote] = useState("");
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    if (!open) return;
    setProofUrl("");
    setTitle("Proof approval");
    setCustomerMessage("");
    setOperatorNote("");
    setLocalError("");
  }, [open]);

  if (!open) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError("");
    const cleanedProofUrl = proofUrl.trim();
    if (!/^https?:\/\/\S+$/i.test(cleanedProofUrl)) {
      setLocalError("Enter a valid proof URL that starts with http or https.");
      return;
    }
    await onSend({
      proofUrl: cleanedProofUrl,
      title: title.trim(),
      customerMessage: customerMessage.trim(),
      operatorNote: operatorNote.trim(),
    });
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

          <label>
            <span>Proof URL</span>
            <input
              autoFocus
              disabled={isSending}
              onChange={(event) => setProofUrl(event.target.value)}
              placeholder="https://..."
              required
              type="url"
              value={proofUrl}
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
            <button className="send-button" disabled={!proofUrl.trim() || isSending} type="submit">
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
