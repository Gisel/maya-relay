import { MessageSquare, Send, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Channel, QuickResponse } from "../api";
import { CustomerContactPicker, CustomerContactSelection } from "../customers/CustomerContactPicker";

export type NewMessagePayload = {
  body: string;
  channel: Channel;
  clientRequestId: string;
  displayName: string;
  phoneNumber: string;
  templateKey: string | null;
  variables: Record<string, string>;
};

type NewMessageDrawerProps = {
  error: string;
  isSending: boolean;
  onAuthExpired?: () => void;
  onClose: () => void;
  onSend: (payload: NewMessagePayload) => Promise<void>;
  open: boolean;
  quickResponses: QuickResponse[];
};

const EMPTY_SELECTION: CustomerContactSelection = {
  contact: null,
  displayName: "",
  phoneNumber: "",
};

function defaultClientRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `new-message-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function templateResponses(responses: QuickResponse[]) {
  return responses.filter((response) => response.group === "template_response" && response.channels?.includes("whatsapp"));
}

function defaultTemplate(responses: QuickResponse[]) {
  return (
    responses.find((response) => response.id === "maya_new_customer_intro")
    || responses.find((response) => response.templateKey === "new_customer_intro")
    || responses[0]
    || null
  );
}

function defaultVariables(template: QuickResponse | null, customerName: string) {
  const variables: Record<string, string> = {};
  template?.variables?.forEach((variable) => {
    const defaultValue = variable.defaultSource === "customer_name" ? customerName : variable.defaultValue;
    variables[variable.key] = defaultValue || "";
  });
  return variables;
}

function renderTemplatePreview(template: QuickResponse | null, variables: Record<string, string>) {
  if (!template) return "";
  let body = template.bodyTemplate || template.body;
  template.variables?.forEach((variable) => {
    const value = variables[variable.key] || variable.defaultValue || "";
    body = body.split(`{${variable.key}}`).join(value);
  });
  return body;
}

export function NewMessageDrawer({
  error,
  isSending,
  onAuthExpired,
  onClose,
  onSend,
  open,
  quickResponses,
}: NewMessageDrawerProps) {
  const availableTemplates = useMemo(() => templateResponses(quickResponses), [quickResponses]);
  const [selection, setSelection] = useState<CustomerContactSelection>(EMPTY_SELECTION);
  const [channel, setChannel] = useState<Channel>("sms");
  const [body, setBody] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [clientRequestId, setClientRequestId] = useState(defaultClientRequestId);

  const selectedTemplate = useMemo(
    () => availableTemplates.find((template) => template.id === templateId) || null,
    [availableTemplates, templateId],
  );
  const customerName = selection.displayName || selection.contact?.name || "";
  const templatePreview = useMemo(() => renderTemplatePreview(selectedTemplate, variables), [selectedTemplate, variables]);

  useEffect(() => {
    if (!open) return;
    const template = defaultTemplate(availableTemplates);
    setTemplateId(template?.id || "");
    setVariables(defaultVariables(template, ""));
    setClientRequestId(defaultClientRequestId());
  }, [availableTemplates, open]);

  useEffect(() => {
    if (!selectedTemplate) {
      setVariables({});
      return;
    }
    setVariables((current) => {
      const nextDefaults = defaultVariables(selectedTemplate, customerName);
      const nextVariables: Record<string, string> = {};
      selectedTemplate.variables?.forEach((variable) => {
        nextVariables[variable.key] = current[variable.key]?.trim() ? current[variable.key] : nextDefaults[variable.key] || "";
      });
      return nextVariables;
    });
  }, [customerName, selectedTemplate]);

  function resetAndClose() {
    if (isSending) return;
    onClose();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await onSend({
        body: channel === "sms" ? body.trim() : "",
        channel,
        clientRequestId,
        displayName: selection.displayName,
        phoneNumber: selection.phoneNumber,
        templateKey: channel === "whatsapp" ? selectedTemplate?.templateKey || null : null,
        variables: channel === "whatsapp" ? variables : {},
      });
      setSelection(EMPTY_SELECTION);
      setBody("");
      setChannel("sms");
      setClientRequestId(defaultClientRequestId());
    } catch {
      // Parent owns the user-facing error state.
    }
  }

  const canSubmit = Boolean(selection.phoneNumber.trim()) && (
    channel === "sms"
      ? Boolean(body.trim())
      : Boolean(selectedTemplate) && (selectedTemplate?.variables || []).every((variable) => !variable.required || variables[variable.key]?.trim())
  );

  if (!open) return null;

  return (
    <div className="drawer-backdrop" role="presentation">
      <section aria-labelledby="new-message-title" aria-modal="true" className="drawer-surface mobile-drawer" role="dialog">
        <div className="drawer-header">
          <div>
            <h2 id="new-message-title">New message</h2>
            <p>Start an SMS conversation or use an approved WhatsApp template.</p>
          </div>
          <button aria-label="Close new message" className="drawer-close" disabled={isSending} onClick={resetAndClose} type="button">
            <X size={18} />
          </button>
        </div>

        <form className="drawer-form new-message-form" onSubmit={submit}>
          <CustomerContactPicker
            disabled={isSending}
            onAuthExpired={onAuthExpired}
            onChange={setSelection}
            selection={selection}
          />

          <fieldset className="channel-choice">
            <legend>Channel</legend>
            <label className={channel === "sms" ? "selected" : ""}>
              <input
                checked={channel === "sms"}
                disabled={isSending}
                onChange={() => setChannel("sms")}
                type="radio"
                value="sms"
              />
              SMS
            </label>
            <label className={channel === "whatsapp" ? "selected" : ""}>
              <input
                checked={channel === "whatsapp"}
                disabled={isSending}
                onChange={() => setChannel("whatsapp")}
                type="radio"
                value="whatsapp"
              />
              WhatsApp
            </label>
          </fieldset>

          {channel === "sms" ? (
            <label>
              <span>Message</span>
              <textarea
                disabled={isSending}
                onChange={(event) => setBody(event.target.value)}
                placeholder="Type the first message"
                required
                rows={4}
                value={body}
              />
            </label>
          ) : (
            <div className="new-message-template-section">
              <label>
                <span>Approved WhatsApp template</span>
                <select
                  disabled={isSending || availableTemplates.length === 0}
                  onChange={(event) => setTemplateId(event.target.value)}
                  required
                  value={templateId}
                >
                  {availableTemplates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.label}
                    </option>
                  ))}
                </select>
              </label>

              {selectedTemplate?.variables && selectedTemplate.variables.length > 0 && (
                <div className="quick-response-fields">
                  {selectedTemplate.variables.map((variable) => (
                    <label key={variable.key}>
                      <span>{variable.label}</span>
                      <input
                        disabled={isSending}
                        onChange={(event) =>
                          setVariables((current) => ({
                            ...current,
                            [variable.key]: event.target.value,
                          }))
                        }
                        placeholder={variable.placeholder || variable.label}
                        required={variable.required}
                        type="text"
                        value={variables[variable.key] || ""}
                      />
                    </label>
                  ))}
                </div>
              )}

              <div className="quick-response-preview">
                <p>{templatePreview || "Select an approved template to start WhatsApp."}</p>
              </div>
            </div>
          )}

          {error && <p className="form-error">{error}</p>}

          <div className="drawer-actions">
            <button className="ghost-button" disabled={isSending} onClick={resetAndClose} type="button">
              Cancel
            </button>
            <button className="send-button" disabled={!canSubmit || isSending} type="submit">
              {channel === "sms" ? <Send size={17} /> : <MessageSquare size={17} />}
              {isSending ? "Sending..." : "Send message"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
