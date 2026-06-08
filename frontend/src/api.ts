export type Channel = "sms" | "whatsapp";
export type ConversationStatus = "open" | "closed";
export type ConversationStatusFilter = ConversationStatus | "all";
export type DeliveryStatus = "delivered" | "failed" | "pending" | "queued" | "undelivered" | string;
export type MessageDirection = "customer_to_employee" | "employee_to_customer" | "system" | string;

export type Metrics = {
  open: number;
  failed: number;
  recent: number;
  withAttachments?: number;
};

export type Customer = {
  phone: string;
  displayName: string | null;
  lookupName: string | null;
  name: string | null;
};

export type ConversationListItem = {
  id: string;
  code: string | null;
  status: ConversationStatus;
  channel: Channel;
  customer: Customer;
  lastMessage: {
    body: string;
    direction: MessageDirection;
    deliveryStatus: DeliveryStatus;
    deliveryErrorCode: string | null;
    createdAt: string | null;
    hasAttachments: boolean;
  } | null;
  updatedAt: string | null;
};

export type ConversationDetail = {
  id: string;
  code: string;
  status: ConversationStatus;
  channel: Channel;
  customer: Customer;
  assignedEmployee: string;
  createdAt: string | null;
  updatedAt: string | null;
};

export type CallRecord = {
  id: string;
  conversationId: string | null;
  direction: "outbound" | "inbound" | string;
  callType: "conversation_call" | "manual_outbound" | "inbound" | string;
  customerPhone: string;
  employeePhone: string | null;
  twilioCallSid: string | null;
  status: string;
  outcome: string | null;
  notes: string | null;
  followUpStatus: "none" | "needed" | "scheduled" | "done";
  recap: string | null;
  transcription: string | null;
  startedAt: string | null;
  answeredAt: string | null;
  completedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
};

export type CallOutcome = "connected" | "voicemail" | "no_answer" | "follow_up_needed" | "wrong_number" | "cancelled";
export type FollowUpStatus = "none" | "needed" | "scheduled" | "done";

export type Attachment = {
  url: string;
  contentType: string;
  kind: "image" | "file";
};

export type Message = {
  id: string;
  conversationId: string;
  direction: MessageDirection;
  body: string;
  fromPhone: string;
  toPhone: string;
  twilioMessageSid: string | null;
  deliveryStatus: DeliveryStatus;
  deliveryErrorCode: string | null;
  deliveryErrorMessage: string | null;
  clientRequestId: string | null;
  createdAt: string | null;
  attachments: Attachment[];
};

export type QuickResponse = {
  id: string;
  label: string;
  body: string;
};

export type ConversationsResponse = {
  metrics: Metrics;
  conversations: ConversationListItem[];
  pagination?: {
    limit: number;
    offset: number;
    nextOffset: number | null;
    hasMore: boolean;
  };
};

export type ConversationDetailResponse = {
  conversation: ConversationDetail;
  messages: Message[];
  calls: CallRecord[];
  suggestedReply: string;
};

export type ReplyResponse = {
  status: "sent" | "duplicate";
  message: Message;
};

export type UpdateConversationResponse = {
  conversation: ConversationDetail;
};

export type CallConversationResponse = {
  status: "calling";
  callSid: string;
  to: string;
  employeePhone: string;
};

export type StartNewCallResponse = CallConversationResponse & {
  conversation: ConversationDetail;
};

export type UpdateCallDetailsResponse = {
  call: CallRecord;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });

  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail || message;
    } catch {
      // Keep the status text when the response is not JSON.
    }
    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
}

export function getMe() {
  return request<{ authenticated: true; app: { name: string; environment: string } }>("/api/me");
}

export function login(password: string) {
  return request<{ authenticated: true }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export function logout() {
  return request<{ authenticated: false }>("/api/auth/logout", { method: "POST" });
}

export function getConversations(query = "", offset = 0, limit = 50, status: ConversationStatusFilter = "all") {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (offset > 0) params.set("offset", String(offset));
  if (limit !== 50) params.set("limit", String(limit));
  if (status !== "all") params.set("status", status);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<ConversationsResponse>(`/api/conversations${suffix}`);
}

export function getConversationDetail(conversationId: string) {
  return request<ConversationDetailResponse>(`/api/conversations/${conversationId}`);
}

export function getQuickResponses() {
  return request<{ quickResponses: QuickResponse[] }>("/api/quick-responses");
}

export function sendReply(conversationId: string, body: string, files: File[], clientRequestId: string) {
  const form = new FormData();
  form.set("body", body);
  form.set("client_request_id", clientRequestId);
  files.forEach((file) => form.append("reply_files", file));

  return request<ReplyResponse>(`/api/conversations/${conversationId}/reply`, {
    method: "POST",
    body: form,
  });
}

export function updateConversationStatus(conversationId: string, status: ConversationStatus) {
  return request<UpdateConversationResponse>(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function callConversationCustomer(conversationId: string) {
  return request<CallConversationResponse>(`/api/conversations/${conversationId}/call`, {
    method: "POST",
  });
}

export function startNewCall(phoneNumber: string, displayName: string) {
  return request<StartNewCallResponse>("/api/calls", {
    method: "POST",
    body: JSON.stringify({
      phone_number: phoneNumber,
      display_name: displayName.trim() || null,
    }),
  });
}

export function updateCallDetails(
  callId: string,
  payload: {
    outcome: CallOutcome | null;
    follow_up_status: FollowUpStatus;
    notes: string | null;
    recap: string | null;
    transcription: string | null;
  },
) {
  return request<UpdateCallDetailsResponse>(`/api/calls/${callId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
