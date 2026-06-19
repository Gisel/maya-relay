import { Loader2, Send, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { QuickResponse } from "../api";

type QuickResponseSendModalProps = {
  customerName: string;
  error: string;
  isSending: boolean;
  onClose: () => void;
  onSend: (variables: Record<string, string>) => void;
  response: QuickResponse | null;
};

export function QuickResponseSendModal({
  customerName,
  error,
  isSending,
  onClose,
  onSend,
  response,
}: QuickResponseSendModalProps) {
  const [variables, setVariables] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!response) {
      setVariables({});
      return;
    }
    const nextVariables: Record<string, string> = {};
    response.variables?.forEach((variable) => {
      const defaultValue = variable.defaultSource === "customer_name" ? customerName : variable.defaultValue;
      nextVariables[variable.key] = defaultValue || "";
    });
    setVariables(nextVariables);
  }, [customerName, response]);

  const preview = useMemo(() => {
    if (!response) return "";
    let body = response.bodyTemplate || response.body;
    response.variables?.forEach((variable) => {
      const value = variables[variable.key] || variable.defaultValue || "";
      body = body.split(`{${variable.key}}`).join(value);
    });
    return body;
  }, [response, variables]);

  if (!response) return null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSend(variables);
  }

  return (
    <div className="drawer-backdrop quick-response-modal-backdrop">
      <section aria-labelledby="quick-response-title" aria-modal="true" className="drawer-surface quick-response-modal" role="dialog">
        <div className="drawer-header">
          <div>
            <h2 id="quick-response-title">{response.label}</h2>
            <p>{customerName || "Selected customer"}</p>
          </div>
          <button aria-label="Close quick response" className="drawer-close" disabled={isSending} onClick={onClose} type="button">
            <X size={20} />
          </button>
        </div>

        <form className="quick-response-send-form" onSubmit={submit}>
          {response.variables && response.variables.length > 0 && (
            <div className="quick-response-fields">
              {response.variables.map((variable) => (
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
            <p>{preview}</p>
          </div>

          {error && <div className="drawer-error">{error}</div>}

          <button className="send-button quick-response-send-button" disabled={isSending} type="submit">
            {isSending ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
            {isSending ? "Sending" : "Send"}
          </button>
        </form>
      </section>
    </div>
  );
}
