import { useMemo, useState } from "react";
import { Channel, CustomerActionRequest, QuickResponse } from "../api";
import { QuickResponsesPanel } from "../messaging/QuickResponsesPanel";
import { CustomerActionRequestsPanel } from "./CustomerActionRequestsPanel";

type CustomerActionPanelTabsProps = {
  cancelingRequestId?: string;
  channel: Channel;
  onCancelRequest: (requestId: string) => void;
  onUseResponse: (body: string) => void;
  requests: CustomerActionRequest[];
  responses: QuickResponse[];
};

type ActionPanelTab = "quick_responses" | "requests";

export function CustomerActionPanelTabs({
  cancelingRequestId = "",
  channel,
  onCancelRequest,
  onUseResponse,
  requests,
  responses,
}: CustomerActionPanelTabsProps) {
  const [activeTab, setActiveTab] = useState<ActionPanelTab>("quick_responses");
  const pendingCount = useMemo(
    () => requests.filter((request) => request.status === "pending").length,
    [requests],
  );

  return (
    <section className="context-section customer-action-panel">
      <div className="context-tab-list" role="tablist" aria-label="Conversation tools">
        <button
          aria-selected={activeTab === "quick_responses"}
          className={activeTab === "quick_responses" ? "is-active" : ""}
          onClick={() => setActiveTab("quick_responses")}
          role="tab"
          type="button"
        >
          Quick Responses
        </button>
        <button
          aria-selected={activeTab === "requests"}
          className={activeTab === "requests" ? "is-active" : ""}
          onClick={() => setActiveTab("requests")}
          role="tab"
          type="button"
        >
          Requests
          {pendingCount > 0 && <span>{pendingCount}</span>}
        </button>
      </div>

      {activeTab === "quick_responses" ? (
        <QuickResponsesPanel channel={channel} onUseResponse={onUseResponse} responses={responses} variant="embedded" />
      ) : (
        <CustomerActionRequestsPanel
          cancelingRequestId={cancelingRequestId}
          onCancelRequest={onCancelRequest}
          requests={requests}
        />
      )}
    </section>
  );
}
