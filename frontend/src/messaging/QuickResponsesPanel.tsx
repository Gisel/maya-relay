import { CheckCircle2, CircleHelp, CreditCard, MessageSquareText, PackageCheck, Sparkles } from "lucide-react";
import { Channel, QuickResponse } from "../api";

type QuickResponsesPanelProps = {
  channel: Channel;
  responses: QuickResponse[];
  onUseResponse: (body: string) => void;
};

function channelAllows(response: QuickResponse, channel: Channel) {
  return !response.channels || response.channels.includes(channel);
}

function responseGroup(response: QuickResponse) {
  return response.group || "quick_response";
}

function responseIcon(response: QuickResponse, index: number) {
  if (response.id.includes("quote")) return <MessageSquareText size={16} />;
  if (response.id.includes("proof")) return <CheckCircle2 size={16} />;
  if (response.id.includes("pickup")) return <PackageCheck size={16} />;
  if (response.id.includes("payment")) return <CreditCard size={16} />;
  if (index === 0) return <CircleHelp size={16} />;
  if (index === 1) return <CheckCircle2 size={16} />;
  return <Sparkles size={16} />;
}

export function QuickResponsesPanel({ channel, responses, onUseResponse }: QuickResponsesPanelProps) {
  const availableResponses = responses.filter((response) => {
    const group = responseGroup(response);
    return (group === "quick_response" || group === "whatsapp_draft") && channelAllows(response, channel);
  });

  return (
    <section className="context-section">
      <h2>Quick Responses</h2>
      <div className="quick-responses">
        {availableResponses.map((response, index) => (
          <button key={response.id} onClick={() => onUseResponse(response.body)} type="button">
            {responseIcon(response, index)}
            <span>{response.label}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
