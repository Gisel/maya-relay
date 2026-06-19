import { FormEvent, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { FolderUp, Send, X } from "lucide-react";

import { Channel } from "../api";

type AssetsRequestPayload = {
  title: string;
  customerMessage: string;
  operatorNote: string;
};

type AssetsRequestModalProps = {
  channel: Channel;
  customerName: string;
  customerPhone: string;
  error: string;
  isSending: boolean;
  onClose: () => void;
  onSend: (payload: AssetsRequestPayload) => Promise<void>;
  open: boolean;
};

export function AssetsRequestModal({
  channel,
  customerName,
  customerPhone,
  error,
  isSending,
  onClose,
  onSend,
  open,
}: AssetsRequestModalProps) {
  const [title, setTitle] = useState("Upload assets");
  const [customerMessage, setCustomerMessage] = useState("");
  const [operatorNote, setOperatorNote] = useState("");
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    if (!open) return;
    setTitle("Upload assets");
    setCustomerMessage("");
    setOperatorNote("");
    setLocalError("");
  }, [open]);

  if (!open) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError("");
    if (!title.trim()) {
      setLocalError("Add a short title for this asset request.");
      return;
    }
    await onSend({
      title: title.trim(),
      customerMessage: customerMessage.trim(),
      operatorNote: operatorNote.trim(),
    });
  }

  return createPortal(
    <div className="drawer-backdrop" role="presentation">
      <section aria-labelledby="assets-request-title" aria-modal="true" className="drawer-surface proof-request-surface" role="dialog">
        <div className="drawer-header">
          <div>
            <h2 id="assets-request-title">Request assets</h2>
            <p>{customerName} receives a {channel === "whatsapp" ? "WhatsApp" : "text"} link to upload files for Maya.</p>
          </div>
          <button aria-label="Close assets request" className="drawer-close" disabled={isSending} onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>

        <form className="drawer-form proof-request-form" onSubmit={handleSubmit}>
          <div className="proof-recipient-card">
            <FolderUp size={18} />
            <div>
              <strong>{customerName}</strong>
              <span>{customerPhone}</span>
            </div>
          </div>

          <label>
            <span>Title</span>
            <input
              autoFocus
              disabled={isSending}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Upload assets"
              type="text"
              value={title}
            />
          </label>

          <label>
            <span>Customer message</span>
            <textarea
              disabled={isSending}
              onChange={(event) => setCustomerMessage(event.target.value)}
              placeholder="Optional note before the upload link"
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
            <button className="send-button" disabled={isSending} type="submit">
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
