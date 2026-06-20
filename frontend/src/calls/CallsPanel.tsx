import { Clock, Phone, Search } from "lucide-react";
import { CallConversationListItem, CallDirectionFilter } from "../api";
import { callDirectionLabel, cleanPhone, relativeDate, workflowLabel } from "./callUtils";

function customerName(row: CallConversationListItem) {
  return row.customer.name || cleanPhone(row.customer.phone) || cleanPhone(row.latestCall.customerPhone) || "Unknown customer";
}

function compactWorkflowLabel(status: string | null | undefined) {
  if (status === "pending_follow_up" || !status) return "Pending";
  return workflowLabel(status);
}

export function CallsPanel({
  directionFilter,
  hasMore,
  isLoading,
  isLoadingMore,
  isSearching,
  onDirectionChange,
  onLoadMore,
  onSearchChange,
  onSelect,
  rows,
  search,
  selectedId,
}: {
  directionFilter: CallDirectionFilter;
  hasMore: boolean;
  isLoading: boolean;
  isLoadingMore: boolean;
  isSearching: boolean;
  onDirectionChange: (filter: CallDirectionFilter) => void;
  onLoadMore: () => void;
  onSearchChange: (value: string) => void;
  onSelect: (row: CallConversationListItem) => void;
  rows: CallConversationListItem[];
  search: string;
  selectedId: string;
}) {
  return (
    <>
      <label className="search-box">
        <Search size={20} />
        <input
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search calls..."
          type="search"
          value={search}
        />
      </label>

      <div className="conversation-filter call-filter" role="group" aria-label="Call direction filter">
        {(["outgoing", "incoming", "all"] as CallDirectionFilter[]).map((filter) => (
          <button
            className={directionFilter === filter ? "is-active" : ""}
            key={filter}
            onClick={() => onDirectionChange(filter)}
            type="button"
          >
            {filter}
          </button>
        ))}
      </div>

      <div className="conversation-list call-activity-list">
        {isLoading && <p className="panel-note">Loading calls...</p>}
        {!isLoading && rows.length === 0 && <p className="panel-note">No calls found.</p>}
        {rows.map((row) => (
          <button
            className={`call-activity-row ${row.id === selectedId ? "selected" : ""} direction-${row.latestCall.direction || "unknown"}`}
            key={row.id}
            onClick={() => onSelect(row)}
            type="button"
          >
            <span className="call-row-icon">
              <Phone size={16} />
            </span>
            <span className="call-row-content">
              <span className="conversation-row-heading">
                <span className="call-row-heading-main">
                  <strong>{customerName(row)}</strong>
                  <span className="call-row-phone">{cleanPhone(row.customer.phone || row.latestCall.customerPhone)}</span>
                </span>
                <em>{relativeDate(row.latestCall.startedAt || row.latestCall.createdAt)}</em>
              </span>
              <span className="call-row-meta">
                <span>{callDirectionLabel(row.latestCall.direction)}</span>
                <span className={`call-status-pill status-${row.latestCall.status || "unknown"}`}>
                  {row.latestCall.status || "unknown"}
                </span>
                <span className={`workflow-pill workflow-${row.workflowStatus || "pending_follow_up"}`}>
                  {compactWorkflowLabel(row.workflowStatus)}
                </span>
                {row.callCount > 1 && <span>{row.callCount} calls</span>}
                <span className="call-row-code">
                  <Clock size={12} />
                  {row.conversation?.code ? `#${row.conversation.code}` : "No conversation"}
                </span>
              </span>
            </span>
          </button>
        ))}
        {search.trim() && isSearching && <p className="panel-note">Searching calls...</p>}
        {!search.trim() && hasMore && (
          <button className="load-more-button" disabled={isLoadingMore} onClick={onLoadMore} type="button">
            {isLoadingMore ? "Loading..." : "Load more"}
          </button>
        )}
      </div>
    </>
  );
}
