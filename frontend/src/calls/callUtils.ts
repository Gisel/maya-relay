import { CallOutcome, CallRecord, FollowUpStatus } from "../api";

export const CALL_OUTCOMES: { value: CallOutcome; label: string }[] = [
  { value: "connected", label: "Connected" },
  { value: "voicemail", label: "Voicemail" },
  { value: "no_answer", label: "No answer" },
  { value: "follow_up_needed", label: "Follow-up" },
  { value: "wrong_number", label: "Wrong number" },
  { value: "cancelled", label: "Cancelled" },
];

export const FOLLOW_UP_STATUSES: { value: FollowUpStatus; label: string }[] = [
  { value: "none", label: "None" },
  { value: "needed", label: "Pending follow-up" },
  { value: "scheduled", label: "Scheduled" },
  { value: "done", label: "Done" },
];

export function cleanPhone(phone: string | null | undefined) {
  return (phone || "").replace(/^whatsapp:/i, "");
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export function relativeDate(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.max(0, Math.round(diffMs / 60000));
  if (diffMinutes < 1) return "now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const hours = Math.round(diffMinutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function callTypeLabel(call: CallRecord) {
  if (call.callType === "manual_outbound") return "New outbound call";
  if (call.callType === "conversation_call") return "Conversation call";
  if (call.direction === "inbound") return "Incoming call";
  return "Call";
}

export function callDirectionLabel(direction: string | null | undefined) {
  if (direction === "inbound") return "Incoming";
  if (direction === "outbound") return "Outgoing";
  return "Call";
}

export function callDuration(call: CallRecord) {
  if (!call.answeredAt || !call.completedAt) return "";
  const answeredAt = new Date(call.answeredAt);
  const completedAt = new Date(call.completedAt);
  if (Number.isNaN(answeredAt.getTime()) || Number.isNaN(completedAt.getTime())) return "";
  const durationSeconds = Math.max(0, Math.round((completedAt.getTime() - answeredAt.getTime()) / 1000));
  if (durationSeconds < 60) return `${durationSeconds}s`;
  const minutes = Math.floor(durationSeconds / 60);
  const seconds = durationSeconds % 60;
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

export function outcomeLabel(outcome: string | null | undefined) {
  if (!outcome) return "No outcome";
  return CALL_OUTCOMES.find((item) => item.value === outcome)?.label || outcome;
}

export function followUpLabel(status: FollowUpStatus | string | null | undefined) {
  if (!status || status === "none") return "None";
  return FOLLOW_UP_STATUSES.find((item) => item.value === status)?.label || status;
}

export function workflowLabel(status: string | null | undefined) {
  if (status === "pending_follow_up") return "Pending follow-up";
  if (status === "done") return "Done";
  return status || "Pending follow-up";
}
