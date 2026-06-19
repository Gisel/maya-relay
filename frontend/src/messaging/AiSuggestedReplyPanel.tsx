import { Loader2, RefreshCw, Sparkles } from "lucide-react";

type AiSuggestedReplyPanelProps = {
  error?: string;
  isLoading: boolean;
  onRefresh: () => void;
  onUseReply: () => void;
  suggestedReply: string;
};

export function AiSuggestedReplyPanel({
  error = "",
  isLoading,
  onRefresh,
  onUseReply,
  suggestedReply,
}: AiSuggestedReplyPanelProps) {
  const hasSuggestion = Boolean(suggestedReply);

  return (
    <section className="context-section">
      <div className="ai-suggestion-heading">
        <h2>
          <Sparkles size={18} />
          AI Suggested Reply
        </h2>
        <span className={`suggestion-status-pill ${hasSuggestion ? "ready" : "empty"}`}>
          {isLoading ? "Thinking" : hasSuggestion ? "Ready" : "No suggestion"}
        </span>
      </div>
      <div className={`intent-box ${hasSuggestion ? "has-suggestion" : "is-empty"}`}>
        <p>
          {isLoading
            ? "Generating a fresh suggestion..."
            : suggestedReply || error || "No AI suggestion is available for this conversation yet."}
        </p>
        <div className="ai-suggestion-actions">
          {hasSuggestion && (
            <button className="secondary-action compact" onClick={onUseReply} type="button">
              Use suggested reply
            </button>
          )}
          <button className="ghost-button compact" disabled={isLoading} onClick={onRefresh} type="button">
            {isLoading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            Refresh
          </button>
        </div>
      </div>
    </section>
  );
}
