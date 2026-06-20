export type Channel = "sms" | "whatsapp";
export type ConversationStatus = "open" | "closed";
export type ConversationStatusFilter = ConversationStatus | "all";
export type CallDirectionFilter = "outgoing" | "incoming" | "all";
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

export type ContactProfile = {
  id: string;
  phone: string;
  displayName: string | null;
  lookupName: string | null;
  name: string | null;
  notes: string | null;
};

export type ContactSearchItem = ContactProfile & {
  lastActivityAt: string | null;
  openConversationId: string | null;
  lastConversationId: string | null;
  latestCallId: string | null;
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
  recordingSid: string | null;
  recordingUrl: string | null;
  recordingStatus: string | null;
  recordingDurationSeconds: number | null;
  recordingChannels: number | null;
  startedAt: string | null;
  answeredAt: string | null;
  completedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
};

export type CallOutcome = "connected" | "voicemail" | "no_answer" | "follow_up_needed" | "wrong_number" | "cancelled";
export type FollowUpStatus = "none" | "needed" | "scheduled" | "done";

export type CallConversationListItem = {
  id: string;
  conversation: {
    id: string;
    code: string | null;
    status: ConversationStatus;
    channel: Channel;
    assignedEmployee: string | null;
    createdAt: string | null;
    updatedAt: string | null;
  } | null;
  customer: Customer;
  latestCall: CallRecord;
  callCount: number;
  workflowStatus: "pending_follow_up" | "done" | string;
};

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
  bodyTemplate?: string;
  group?: "quick_response" | "template_response" | "whatsapp_draft" | string;
  channels?: Channel[];
  requiresActiveWindow?: boolean;
  templateKey?: string;
  variables?: QuickResponseVariable[];
};

export type QuickResponseVariable = {
  key: string;
  label: string;
  placeholder?: string;
  required?: boolean;
  defaultValue?: string;
  defaultSource?: "customer_name" | string;
};

export type CustomerActionRequest = {
  id: string;
  conversationId: string;
  contactId: string | null;
  type: "proof" | "assets" | string;
  status: "pending" | "approved" | "changes_requested" | "submitted" | "expired" | "canceled" | string;
  title: string | null;
  operatorNote: string | null;
  expiresAt: string | null;
  completedAt: string | null;
  canceledAt: string | null;
  createdBy: string | null;
  createdAt: string | null;
  updatedAt: string | null;
};

export type CustomerActionFile = {
  id: string;
  role: string;
  publicUrl: string | null;
  externalUrl: string | null;
  originalFilename: string | null;
  contentType: string | null;
  sizeBytes: number | null;
  createdAt: string | null;
};

export type CustomerActionEvent = {
  id: string;
  type: string;
  comment: string | null;
  metadata: Record<string, unknown>;
  createdAt: string | null;
};

export type PublicProofRequest = CustomerActionRequest & {
  files: CustomerActionFile[];
  events: CustomerActionEvent[];
};

export type PublicAssetRequest = CustomerActionRequest & {
  files: CustomerActionFile[];
  events: CustomerActionEvent[];
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
  customerActions: CustomerActionRequest[];
  suggestedReply: string;
};

export type CallsResponse = {
  calls: CallConversationListItem[];
  pagination?: {
    limit: number;
    offset: number;
    nextOffset: number | null;
    hasMore: boolean;
  };
};

export type ContactsResponse = {
  items: ContactSearchItem[];
  pagination?: {
    limit: number;
    offset: number;
    nextOffset: number | null;
    hasMore: boolean;
  };
};

export type UpdateContactResponse = {
  contact: ContactProfile;
};

export type ContactImportResponse = {
  created: number;
  updated: number;
  skipped: number;
  invalidRows: {
    row: number;
    code: string;
    message: string;
  }[];
};

export type OperationalMessageFailure = {
  id: string;
  conversationId: string | null;
  conversationCode: string | null;
  customerName: string | null;
  customerPhone: string | null;
  channel: string;
  direction: string | null;
  bodyPreview: string;
  twilioMessageSid: string | null;
  deliveryStatus: string | null;
  deliveryErrorCode: string | null;
  deliveryErrorMessage: string | null;
  createdAt: string | null;
  hint: string;
};

export type OperationalCallAttention = {
  id: string;
  kind: "recording_failed" | "recording_missing" | "transcription_missing" | "recap_missing" | string;
  conversationId: string | null;
  conversationCode: string | null;
  customerName: string | null;
  customerPhone: string | null;
  direction: string | null;
  callType: string | null;
  twilioCallSid: string | null;
  status: string | null;
  recordingStatus: string | null;
  recordingSid: string | null;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string | null;
  hint: string;
};

export type OperationalStatusResponse = {
  summary: {
    messageFailures: number;
    callAttention: number;
    total: number;
  };
  messageFailures: OperationalMessageFailure[];
  callAttention: OperationalCallAttention[];
};

export type ReplyResponse = {
  status: "sent" | "duplicate";
  message: Message;
};

export type ProofRequestResponse = {
  proofRequest: CustomerActionRequest;
  publicUrl: string;
  message: Message;
};

export type AssetRequestResponse = {
  assetRequest: CustomerActionRequest;
  publicUrl: string;
  message: Message;
};

export type PublicProofRequestResponse = {
  proofRequest: PublicProofRequest;
};

export type PublicAssetRequestResponse = {
  assetRequest: PublicAssetRequest;
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

export type StartConversationResponse = {
  status: "sent" | "duplicate";
  sendMode: "free_form" | "template" | "duplicate";
  templateKey: string | null;
  contentSid: string | null;
  conversation: ConversationDetail;
  message: Message;
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

export function getCalls(query = "", offset = 0, limit = 50, direction: CallDirectionFilter = "all") {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (offset > 0) params.set("offset", String(offset));
  if (limit !== 50) params.set("limit", String(limit));
  if (direction !== "all") params.set("direction", direction);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<CallsResponse>(`/api/calls${suffix}`);
}

export function getContacts(query = "", offset = 0, limit = 25) {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (offset > 0) params.set("offset", String(offset));
  if (limit !== 25) params.set("limit", String(limit));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<ContactsResponse>(`/api/contacts${suffix}`);
}

export function updateContact(contactId: string, payload: { displayName?: string | null; notes?: string | null }) {
  return request<UpdateContactResponse>(`/api/contacts/${contactId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function importContactsCsv(file: File, overwrite = false) {
  const form = new FormData();
  form.set("file", file);
  form.set("overwrite", String(overwrite));
  return request<ContactImportResponse>("/api/contacts/import", {
    method: "POST",
    body: form,
  });
}

export function getConversationDetail(conversationId: string) {
  return request<ConversationDetailResponse>(`/api/conversations/${conversationId}`);
}

export function generateSuggestedReply(conversationId: string) {
  return request<{ suggestedReply: string }>(`/api/conversations/${conversationId}/suggested-reply`, {
    method: "POST",
  });
}

export function getQuickResponses() {
  return request<{ quickResponses: QuickResponse[] }>("/api/quick-responses");
}

export function getOperationalStatus(limit = 10) {
  const params = new URLSearchParams();
  if (limit !== 10) params.set("limit", String(limit));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<OperationalStatusResponse>(`/api/operations/status${suffix}`);
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

export function sendQuickResponse(
  conversationId: string,
  quickResponseId: string,
  payload: {
    variables?: Record<string, string>;
    clientRequestId: string;
  },
) {
  return request<ReplyResponse & { sendMode?: string; templateKey?: string | null; contentSid?: string | null }>(
    `/api/conversations/${conversationId}/quick-responses/${quickResponseId}/send`,
    {
      method: "POST",
      body: JSON.stringify({
        variables: payload.variables || {},
        client_request_id: payload.clientRequestId,
      }),
    },
  );
}

export function createProofRequest(
  conversationId: string,
  payload: {
    proofFile: File;
    title?: string | null;
    operatorNote?: string | null;
    customerMessage?: string | null;
  },
) {
  const form = new FormData();
  form.set("proof_file", payload.proofFile);
  form.set("title", payload.title ?? "");
  form.set("operator_note", payload.operatorNote ?? "");
  form.set("customer_message", payload.customerMessage ?? "");

  return request<ProofRequestResponse>(`/api/conversations/${conversationId}/proof-requests`, {
    method: "POST",
    body: form,
  });
}

export function createAssetRequest(
  conversationId: string,
  payload: {
    title?: string | null;
    operatorNote?: string | null;
    customerMessage?: string | null;
  },
) {
  const form = new FormData();
  form.set("title", payload.title ?? "");
  form.set("operator_note", payload.operatorNote ?? "");
  form.set("customer_message", payload.customerMessage ?? "");

  return request<AssetRequestResponse>(`/api/conversations/${conversationId}/asset-requests`, {
    method: "POST",
    body: form,
  });
}

export function cancelCustomerActionRequest(requestId: string) {
  return request<{ customerAction: CustomerActionRequest }>(`/api/customer-actions/${requestId}/cancel`, {
    method: "POST",
  });
}

export function getPublicProofRequest(token: string) {
  return request<PublicProofRequestResponse>(`/api/proof/${encodeURIComponent(token)}`);
}

export function getPublicAssetRequest(token: string) {
  return request<PublicAssetRequestResponse>(`/api/assets/${encodeURIComponent(token)}`);
}

export function submitPublicAssets(token: string, files: File[], note: string) {
  const form = new FormData();
  form.set("note", note);
  files.forEach((file) => form.append("asset_files", file));

  return request<PublicAssetRequestResponse>(`/api/assets/${encodeURIComponent(token)}/submit`, {
    method: "POST",
    body: form,
  });
}

export function approvePublicProofRequest(token: string, comment?: string) {
  return request<{ proofRequest: CustomerActionRequest }>(`/api/proof/${encodeURIComponent(token)}/approve`, {
    method: "POST",
    body: JSON.stringify({ comment: comment || null }),
  });
}

export function requestPublicProofChanges(token: string, comment: string) {
  return request<{ proofRequest: CustomerActionRequest }>(`/api/proof/${encodeURIComponent(token)}/changes`, {
    method: "POST",
    body: JSON.stringify({ comment }),
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

export function startConversation(payload: {
  phoneNumber: string;
  displayName?: string;
  channel: Channel;
  body?: string;
  templateKey?: string | null;
  variables?: Record<string, string>;
  clientRequestId: string;
}) {
  return request<StartConversationResponse>("/api/conversations/start", {
    method: "POST",
    body: JSON.stringify({
      phone_number: payload.phoneNumber,
      display_name: payload.displayName?.trim() || null,
      channel: payload.channel,
      body: payload.body || null,
      template_key: payload.templateKey || null,
      variables: payload.variables || {},
      client_request_id: payload.clientRequestId,
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

export function getCallRecordingUrl(callId: string) {
  return `/api/calls/${callId}/recording`;
}

export function transcribeCall(callId: string) {
  return request<UpdateCallDetailsResponse>(`/api/calls/${callId}/transcribe`, {
    method: "POST",
  });
}

export function generateCallRecap(callId: string) {
  return request<UpdateCallDetailsResponse>(`/api/calls/${callId}/recap`, {
    method: "POST",
  });
}
