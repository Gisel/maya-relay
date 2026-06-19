import {
  AlertTriangle,
  Archive,
  FileText,
  LogOut,
  PanelRightClose,
  PanelRightOpen,
  Paperclip,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings as SettingsIcon,
  Sparkles,
  X,
} from "lucide-react";
import { DragEvent, FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ApiError,
  CallConversationListItem,
  CallDirectionFilter,
  CallOutcome,
  CallRecord,
  Channel,
  ConversationDetail,
  ConversationListItem,
  ConversationStatus,
  ConversationStatusFilter,
  ContactImportResponse,
  ContactProfile,
  ContactSearchItem,
  CustomerActionRequest,
  cancelCustomerActionRequest,
  createAssetRequest,
  createProofRequest,
  DeliveryStatus,
  FollowUpStatus,
  Message,
  Metrics,
  QuickResponse,
  callConversationCustomer,
  generateCallRecap,
  getCalls,
  getContacts,
  getConversationDetail,
  getConversations,
  getMe,
  getQuickResponses,
  importContactsCsv,
  login,
  logout,
  sendQuickResponse,
  sendReply,
  startNewCall,
  transcribeCall,
  updateContact,
  updateCallDetails,
  updateConversationStatus,
} from "./api";
import logoMaya from "./assets/logo-maya.jpg";
import { CallDetailsForm, CallDetailsPayload } from "./calls/CallDetailsForm";
import { CallsPanel } from "./calls/CallsPanel";
import { CallWorkspace } from "./calls/CallWorkspace";
import { WorkspaceMode, WorkspaceTabs } from "./calls/WorkspaceTabs";
import { CustomerProfileSummary } from "./customers/CustomerProfileSummary";
import { EditCustomerProfileModal } from "./customers/EditCustomerProfileModal";
import { AssetActionButton } from "./customerActions/AssetActionButton";
import { AssetsRequestModal } from "./customerActions/AssetsRequestModal";
import { CustomerActionPanelTabs } from "./customerActions/CustomerActionPanelTabs";
import { ProofActionButton } from "./customerActions/ProofActionButton";
import { ProofRequestModal } from "./customerActions/ProofRequestModal";
import { QuickResponseSendModal } from "./messaging/QuickResponseSendModal";
import { UnifiedSearchResults } from "./search/UnifiedSearchResults";
import { ContactCsvImport } from "./settings/ContactCsvImport";
import { OperationalStatusView } from "./settings/OperationalStatusView";
import { SettingsModal } from "./settings/SettingsModal";

const INBOX_REFRESH_INTERVAL_MS = 15000;
const CLOSE_AUDIT_LOG_PREFIX = "[Maya Relay Close Audit]";

function closeAuditLog(event: string, details: Record<string, unknown> = {}) {
  console.info(CLOSE_AUDIT_LOG_PREFIX, event, {
    at: new Date().toISOString(),
    ...details,
  });
}

function channelLabel(channel: Channel) {
  return channel === "whatsapp" ? "WhatsApp" : "SMS";
}

function phoneIsWhatsapp(phone: string | null | undefined) {
  return (phone || "").toLowerCase().startsWith("whatsapp:");
}

function cleanPhone(phone: string | null | undefined) {
  return (phone || "").replace(/^whatsapp:/i, "");
}

function effectiveChannel(channel: Channel, phone: string | null | undefined): Channel {
  return phoneIsWhatsapp(phone) ? "whatsapp" : channel;
}

function displayCustomerName(conversation: ConversationListItem | ConversationDetail) {
  return conversation.customer.name || cleanPhone(conversation.customer.phone) || "Unknown customer";
}

function cleanRelayBody(body: string) {
  const codePattern = "[A-Za-z0-9]+";

  return body
    .replace(new RegExp(`^From\\s+[\\s\\S]*?\\s+\\[#?${codePattern}\\]:\\s*`, "i"), "")
    .replace(/^From\s+[^:]+:\s*/i, "")
    .replace(new RegExp(`^#${codePattern}\\s+`, "i"), "")
    .replace(new RegExp(`\\s+Reply with\\s+#${codePattern}\\s+your message(?:\\s+---[\\s\\S]*)?$`, "i"), "")
    .replace(/\s+---\s+AI note:[\s\S]*$/i, "")
    .trim();
}

function cleanAttachmentUrls(body: string) {
  return body
    .split(/\r?\n/)
    .filter((line) => !/^Attachment\s+\d+\s+\([^)]+\):\s+https?:\/\//i.test(line.trim()))
    .filter((line) => !/^https?:\/\/\S+$/i.test(line.trim()))
    .join("\n")
    .trim();
}

function displayMessageBody(message: Message) {
  const body = cleanRelayBody(message.body);
  return message.attachments.length > 0 ? cleanAttachmentUrls(body) : body;
}

function previewBody(conversation: ConversationListItem) {
  if (conversation.lastMessage?.body) return cleanRelayBody(conversation.lastMessage.body);
  if (conversation.lastMessage?.hasAttachments) return "Attachment received";
  return "No messages yet";
}

function conversationSearchText(conversation: ConversationListItem) {
  return [
    conversation.code || "",
    displayCustomerName(conversation),
    conversation.customer.displayName || "",
    conversation.customer.lookupName || "",
    cleanPhone(conversation.customer.phone),
    previewBody(conversation),
  ]
    .join(" ")
    .toLowerCase();
}

function conversationMatchesSearch(conversation: ConversationListItem, query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;
  return conversationSearchText(conversation).includes(normalizedQuery);
}

function mergeConversationLists(...lists: (ConversationListItem[] | null | undefined)[]) {
  const seen = new Set<string>();
  const merged: ConversationListItem[] = [];
  lists.flat().forEach((conversation) => {
    if (!conversation || seen.has(conversation.id)) return;
    seen.add(conversation.id);
    merged.push(conversation);
  });
  return merged;
}

function deliveryStatus(conversation: ConversationListItem): DeliveryStatus {
  return conversation.lastMessage?.deliveryStatus || "pending";
}

function needsReply(conversation: ConversationListItem) {
  return conversation.status === "open" && conversation.lastMessage?.direction === "customer_to_employee";
}

function isCustomerVisibleMessage(message: Message) {
  return message.direction !== "system" || isCustomerActionSystemMessage(message);
}

function isCustomerActionSystemMessage(message: Message) {
  const body = message.body.trim();
  return (
    body.startsWith("Proof approved by customer.")
    || body.startsWith("Proof changes requested by customer:")
    || body.startsWith("Assets uploaded by customer:")
  );
}

function formatDate(value: string | null | undefined) {
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

function relativeDate(value: string | null | undefined) {
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

function callTypeLabel(call: CallRecord) {
  if (call.callType === "manual_outbound") return "New outbound call";
  if (call.callType === "conversation_call") return "Conversation call";
  if (call.direction === "inbound") return "Incoming call";
  return "Call";
}

function newClientRequestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function StatusPill({ status }: { status: ConversationStatus }) {
  return <span className={`status-pill ${status}`}>{status}</span>;
}

function DeliveryPill({ status }: { status: DeliveryStatus }) {
  return (
    <span className={`delivery-pill ${status}`}>
      {(status === "failed" || status === "undelivered") && <AlertTriangle size={14} />}
      {status}
    </span>
  );
}

function proofDecisionClass(message: Message) {
  const normalizedBody = message.body.toLowerCase();
  if (normalizedBody.startsWith("proof approved by customer")) {
    return "is-approved";
  }
  if (normalizedBody.startsWith("proof changes requested by customer")) {
    return "is-changes-requested";
  }
  if (normalizedBody.startsWith("assets uploaded by customer")) {
    return "is-assets-submitted";
  }
  return "";
}

function MessageBubble({ message, onMediaLoad }: { message: Message; onMediaLoad: () => void }) {
  if (message.direction === "system") {
    return (
      <article className={`message-bubble system-event ${proofDecisionClass(message)}`}>
        {message.attachments.map((attachment) => (
          <a className="attachment-preview" href={attachment.url} key={attachment.url} rel="noreferrer" target="_blank">
            {attachment.kind === "image" ? (
              <img alt="Message attachment" onLoad={onMediaLoad} src={attachment.url} />
            ) : (
              <span>
                <FileText size={18} />
                Message attachment
              </span>
            )}
          </a>
        ))}
        <p>{message.body}</p>
        <footer>
          <span>{formatDate(message.createdAt)}</span>
        </footer>
      </article>
    );
  }
  const isOutbound = message.direction === "employee_to_customer";
  const body = displayMessageBody(message);

  return (
    <article className={`message-bubble ${isOutbound ? "outbound" : "inbound"}`}>
      {message.attachments.map((attachment) => (
        <a className="attachment-preview" href={attachment.url} key={attachment.url} rel="noreferrer" target="_blank">
          {attachment.kind === "image" ? (
            <img alt="Message attachment" onLoad={onMediaLoad} src={attachment.url} />
          ) : (
            <span>
              <FileText size={18} />
              {attachment.contentType}
            </span>
          )}
        </a>
      ))}
      {body && <p>{body}</p>}
      <footer>
        <span>{formatDate(message.createdAt)}</span>
        <span>{message.deliveryStatus}</span>
      </footer>
    </article>
  );
}

function LoginScreen({
  error,
  onLogin,
}: {
  error: string;
  onLogin: (password: string) => Promise<void>;
}) {
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await onLogin(password);
      setPassword("");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="login-screen">
      <form className="login-panel" onSubmit={handleSubmit}>
        <div className="brand login-brand">
          <img alt="Maya Graphics and Signs" src={logoMaya} />
          <div>
            <strong>MAYA</strong>
            <span>RELAY</span>
          </div>
        </div>
        <label>
          <span>Password</span>
          <input
            autoComplete="current-password"
            autoFocus
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            value={password}
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button className="send-button" disabled={!password || isSubmitting} type="submit">
          {isSubmitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}

function Drawer({
  children,
  description,
  labelledBy,
  onClose,
  open,
  title,
}: {
  children: ReactNode;
  description?: string;
  labelledBy: string;
  onClose: () => void;
  open: boolean;
  title: string;
}) {
  if (!open) return null;

  return (
    <div className="drawer-backdrop" role="presentation">
      <section aria-labelledby={labelledBy} aria-modal="true" className="drawer-surface mobile-drawer" role="dialog">
        <div className="drawer-header">
          <div>
            <h2 id={labelledBy}>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <button aria-label={`Close ${title}`} className="drawer-close" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function NewCallDrawer({
  open,
  onClose,
  onStartCall,
}: {
  open: boolean;
  onClose: () => void;
  onStartCall: (phoneNumber: string, displayName: string) => Promise<void>;
}) {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await onStartCall(phoneNumber, displayName);
      setPhoneNumber("");
      setDisplayName("");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not start the call.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Drawer
      description="Francisco receives the first call, then Maya Relay connects the customer."
      labelledBy="new-call-title"
      onClose={onClose}
      open={open}
      title="New call"
    >
      <form className="drawer-form" onSubmit={handleSubmit}>
        <label>
          <span>Customer phone</span>
          <input
            autoFocus
            inputMode="tel"
            onChange={(event) => setPhoneNumber(event.target.value)}
            placeholder="+1 555 000 0000"
            required
            type="tel"
            value={phoneNumber}
          />
        </label>
        <label>
          <span>Customer name</span>
          <input
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder="Optional"
            type="text"
            value={displayName}
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <div className="drawer-actions">
          <button className="ghost-button" disabled={isSubmitting} onClick={onClose} type="button">
            Cancel
          </button>
          <button className="send-button" disabled={!phoneNumber.trim() || isSubmitting} type="submit">
            <Phone size={17} />
            {isSubmitting ? "Calling..." : "Start call"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

function CloseConversationModal({
  customerName,
  isSubmitting,
  onCancel,
  onConfirm,
  open,
}: {
  customerName: string;
  isSubmitting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  open: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    closeAuditLog("close confirmation modal mounted", { customerName, isSubmitting });

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCancel();
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCancel, open]);

  if (!open) return null;

  return createPortal(
    <div className="confirmation-backdrop" role="presentation">
      <section
        aria-describedby="close-conversation-description"
        aria-labelledby="close-conversation-title"
        aria-modal="true"
        className="confirmation-dialog"
        role="dialog"
      >
        <h2 id="close-conversation-title">Are you sure you want to close this conversation?</h2>
        <p id="close-conversation-description">
          {customerName} will move to Closed. You can reopen it later if you need to reply again.
        </p>
        <div className="confirmation-actions">
          <button className="ghost-button" disabled={isSubmitting} onClick={onCancel} type="button">
            Cancel
          </button>
          <button className="danger-button" disabled={isSubmitting} onClick={onConfirm} type="button">
            {isSubmitting ? "Closing..." : "Close conversation"}
          </button>
        </div>
      </section>
    </div>,
    document.body,
  );
}

function CallDetailsDrawer({
  call,
  open,
  onClose,
  onGenerateRecap,
  onSave,
  onTranscribe,
}: {
  call: CallRecord | null;
  open: boolean;
  onClose: () => void;
  onGenerateRecap: (callId: string) => Promise<void>;
  onSave: (
    callId: string,
    payload: {
      outcome: CallOutcome | null;
      followUpStatus: FollowUpStatus;
      notes: string;
      recap: string;
      transcription: string;
    },
  ) => Promise<void>;
  onTranscribe: (callId: string) => Promise<void>;
}) {
  return (
    <Drawer
      description={call ? `${callTypeLabel(call)} - ${cleanPhone(call.customerPhone)}` : undefined}
      labelledBy="call-details-title"
      onClose={onClose}
      open={open && Boolean(call)}
      title="Call details"
    >
      <CallDetailsForm
        call={call}
        onCancel={onClose}
        onGenerateRecap={onGenerateRecap}
        onSave={async (callId, payload) => {
          await onSave(callId, payload);
          onClose();
        }}
        onTranscribe={onTranscribe}
      />
    </Drawer>
  );
}

function Composer({
  disabled,
  draft,
  files,
  onDraftChange,
  onFilesChange,
  onSend,
}: {
  disabled: boolean;
  draft: string;
  files: File[];
  onDraftChange: (value: string) => void;
  onFilesChange: (files: File[]) => void;
  onSend: (body: string, files: File[]) => Promise<void>;
}) {
  const [isSending, setIsSending] = useState(false);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const canSend = draft.trim().length > 0 || files.length > 0;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 132)}px`;
  }, [draft]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSend || isSending || disabled) return;
    setIsSending(true);
    try {
      await onSend(draft.trim(), files);
      onDraftChange("");
      onFilesChange([]);
    } finally {
      setIsSending(false);
    }
  }

  function appendFiles(nextFiles: File[]) {
    if (disabled || isSending || nextFiles.length === 0) return;
    onFilesChange([...files, ...nextFiles]);
  }

  function handleDragOver(event: DragEvent<HTMLFormElement>) {
    if (disabled || isSending) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsDraggingFiles(true);
  }

  function handleDragLeave(event: DragEvent<HTMLFormElement>) {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    setIsDraggingFiles(false);
  }

  function handleDrop(event: DragEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsDraggingFiles(false);
    appendFiles(Array.from(event.dataTransfer.files ?? []));
  }

  return (
    <form
      className={`composer ${isDraggingFiles ? "is-dragging-files" : ""}`}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onSubmit={handleSubmit}
    >
      <div className="composer-actions">
        <label
          aria-label="Attach files or imagery"
          className={`attach-control ${disabled || isSending ? "is-disabled" : ""}`}
          title="Attach files or imagery"
        >
          <Paperclip size={22} />
          <input
            disabled={disabled || isSending}
            multiple
            onChange={(event) => {
              appendFiles(Array.from(event.target.files ?? []));
              event.currentTarget.value = "";
            }}
            type="file"
          />
        </label>
        <textarea
          aria-label="Reply message"
          disabled={disabled || isSending}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="Message"
          ref={textareaRef}
          rows={1}
          value={draft}
        />
        <button
          aria-label={isSending ? "Sending message" : "Send message"}
          className="send-button composer-send-button"
          disabled={!canSend || isSending || disabled}
          title={isSending ? "Sending..." : "Send message"}
          type="submit"
        >
          <Send size={20} />
        </button>
      </div>
      {files.length > 0 && (
        <div className="file-list">
          {files.map((file) => (
            <span key={`${file.name}-${file.size}`}>{file.name}</span>
          ))}
        </div>
      )}
    </form>
  );
}

export function App() {
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authError, setAuthError] = useState("");
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [metrics, setMetrics] = useState<Metrics>({ open: 0, failed: 0, recent: 0 });
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("text");
  const [callRows, setCallRows] = useState<CallConversationListItem[]>([]);
  const [selectedCallRowId, setSelectedCallRowId] = useState("");
  const [callSearch, setCallSearch] = useState("");
  const [callDirectionFilter, setCallDirectionFilter] = useState<CallDirectionFilter>("all");
  const [isLoadingCalls, setIsLoadingCalls] = useState(false);
  const [isSearchingCalls, setIsSearchingCalls] = useState(false);
  const [isLoadingMoreCalls, setIsLoadingMoreCalls] = useState(false);
  const [nextCallOffset, setNextCallOffset] = useState<number | null>(null);
  const [hasMoreCalls, setHasMoreCalls] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [selectedConversation, setSelectedConversation] = useState<ConversationDetail | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [customerActions, setCustomerActions] = useState<CustomerActionRequest[]>([]);
  const [selectedCallId, setSelectedCallId] = useState("");
  const [quickResponses, setQuickResponses] = useState<QuickResponse[]>([]);
  const [suggestedReply, setSuggestedReply] = useState("");
  const [activeContact, setActiveContact] = useState<ContactProfile | null>(null);
  const [contactSearchResults, setContactSearchResults] = useState<ContactSearchItem[]>([]);
  const [isSearchingContacts, setIsSearchingContacts] = useState(false);
  const [isLoadingContact, setIsLoadingContact] = useState(false);
  const [isProfileEditorOpen, setIsProfileEditorOpen] = useState(false);
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileStatus, setProfileStatus] = useState("");
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isProofRequestOpen, setIsProofRequestOpen] = useState(false);
  const [isSendingProofRequest, setIsSendingProofRequest] = useState(false);
  const [proofRequestError, setProofRequestError] = useState("");
  const [isAssetsRequestOpen, setIsAssetsRequestOpen] = useState(false);
  const [isSendingAssetsRequest, setIsSendingAssetsRequest] = useState(false);
  const [assetsRequestError, setAssetsRequestError] = useState("");
  const [cancelingCustomerActionId, setCancelingCustomerActionId] = useState("");
  const [selectedQuickResponse, setSelectedQuickResponse] = useState<QuickResponse | null>(null);
  const [isSendingQuickResponse, setIsSendingQuickResponse] = useState(false);
  const [quickResponseError, setQuickResponseError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ConversationStatusFilter>("open");
  const [draft, setDraft] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isSearchingConversations, setIsSearchingConversations] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isRefreshingInbox, setIsRefreshingInbox] = useState(false);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [isCallingCustomer, setIsCallingCustomer] = useState(false);
  const [isNewCallOpen, setIsNewCallOpen] = useState(false);
  const [isCloseConfirmationOpen, setIsCloseConfirmationOpen] = useState(false);
  const [closedConversationUndo, setClosedConversationUndo] = useState<{ id: string; name: string } | null>(null);
  const [callStatus, setCallStatus] = useState("");
  const [appError, setAppError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [nextConversationOffset, setNextConversationOffset] = useState<number | null>(null);
  const [hasMoreConversations, setHasMoreConversations] = useState(false);
  const [searchResults, setSearchResults] = useState<ConversationListItem[] | null>(null);
  const [isContextOpen, setIsContextOpen] = useState(() => {
    if (typeof window === "undefined") return true;
    return !window.matchMedia("(max-width: 760px)").matches;
  });
  const didRunInitialSearchEffect = useRef(false);
  const searchRequestId = useRef(0);
  const callSearchRequestId = useRef(0);
  const isRefreshingList = useRef(false);
  const isRefreshingCalls = useRef(false);
  const isRefreshingDetail = useRef(false);
  const messageThreadRef = useRef<HTMLDivElement | null>(null);
  const messageThreadEndRef = useRef<HTMLDivElement | null>(null);

  const allKnownConversations = useMemo(
    () => mergeConversationLists(conversations, searchResults),
    [conversations, searchResults],
  );

  const visibleConversations = useMemo(() => {
    const query = search.trim();
    if (!query) return conversations;
    const localMatches = conversations.filter((conversation) => conversationMatchesSearch(conversation, query));
    return mergeConversationLists(localMatches, searchResults);
  }, [conversations, search, searchResults]);

  const selectedListItem = useMemo(
    () => allKnownConversations.find((conversation) => conversation.id === selectedId) || null,
    [allKnownConversations, selectedId],
  );
  const selectedCallRow = useMemo(
    () => callRows.find((row) => row.id === selectedCallRowId) || null,
    [callRows, selectedCallRowId],
  );
  const selectedCall = useMemo(
    () => calls.find((call) => call.id === selectedCallId) || null,
    [calls, selectedCallId],
  );
  const activeContactPhone = useMemo(() => {
    if (workspaceMode === "calls" && selectedCallRow) {
      return cleanPhone(selectedCallRow.customer.phone || selectedCallRow.latestCall.customerPhone);
    }
    return cleanPhone((selectedConversation || selectedListItem)?.customer.phone);
  }, [selectedCallRow, selectedConversation, selectedListItem, workspaceMode]);

  const visibleMessages = useMemo(
    () => messages.filter(isCustomerVisibleMessage),
    [messages],
  );
  const latestVisibleMessageId = visibleMessages[visibleMessages.length - 1]?.id || "";
  const pendingProofRequest = useMemo(
    () => customerActions.find((request) => request.type === "proof" && request.status === "pending") || null,
    [customerActions],
  );
  const pendingAssetsRequest = useMemo(
    () => customerActions.find((request) => request.type === "assets" && request.status === "pending") || null,
    [customerActions],
  );

  const scrollMessagesToLatest = useCallback(() => {
    const messageThread = messageThreadRef.current;
    const messageThreadEnd = messageThreadEndRef.current;
    if (!messageThread || !messageThreadEnd) return;
    requestAnimationFrame(() => {
      messageThreadEnd.scrollIntoView({ block: "end" });
      messageThread.scrollTop = messageThread.scrollHeight;
    });
  }, []);

  const loadConversations = useCallback(async (fallbackSelectedId = "") => {
    setIsLoadingList(true);
    setAppError("");
    try {
      const payload = await getConversations("", 0, 50, statusFilter);
      setConversations(payload.conversations);
      setMetrics(payload.metrics);
      setNextConversationOffset(payload.pagination?.nextOffset ?? null);
      setHasMoreConversations(payload.pagination?.hasMore ?? false);
      setSelectedId((current) => {
        if (current && payload.conversations.some((conversation) => conversation.id === current)) return current;
        if (fallbackSelectedId) return fallbackSelectedId;
        return payload.conversations[0]?.id || "";
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not load conversations.");
      }
    } finally {
      setIsLoadingList(false);
    }
  }, [statusFilter]);

  const loadMoreConversations = useCallback(async () => {
    if (nextConversationOffset === null || search.trim()) return;
    setIsLoadingMore(true);
    setAppError("");
    try {
      const payload = await getConversations("", nextConversationOffset, 50, statusFilter);
      setConversations((current) => {
        const seen = new Set(current.map((conversation) => conversation.id));
        return [
          ...current,
          ...payload.conversations.filter((conversation) => !seen.has(conversation.id)),
        ];
      });
      setNextConversationOffset(payload.pagination?.nextOffset ?? null);
      setHasMoreConversations(payload.pagination?.hasMore ?? false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not load more conversations.");
      }
    } finally {
      setIsLoadingMore(false);
    }
  }, [nextConversationOffset, search, statusFilter]);

  const loadDetail = useCallback(async (conversationId: string) => {
    if (!conversationId) {
      setSelectedConversation(null);
      setMessages([]);
      setCalls([]);
      setCustomerActions([]);
      setSelectedCallId("");
      setSuggestedReply("");
      setCallStatus("");
      return;
    }
    setIsLoadingDetail(true);
    setAppError("");
    setDetailError("");
    setSelectedConversation(null);
    setMessages([]);
    setCalls([]);
    setCustomerActions([]);
    setSelectedCallId("");
    setSuggestedReply("");
    setCallStatus("");
    try {
      const payload = await getConversationDetail(conversationId);
      setSelectedConversation(payload.conversation);
      setMessages(payload.messages);
      setCalls(payload.calls || []);
      setCustomerActions(payload.customerActions || []);
      setSuggestedReply(payload.suggestedReply || "");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setDetailError(error instanceof Error ? error.message : "Could not load this conversation.");
      }
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  const refreshConversationList = useCallback(async ({ force = false }: { force?: boolean } = {}) => {
    if (isRefreshingList.current && !force) return;
    isRefreshingList.current = true;
    try {
      const payload = await getConversations("", 0, 50, statusFilter);
      setConversations((current) => mergeConversationLists(payload.conversations, current));
      setMetrics(payload.metrics);
      setNextConversationOffset(payload.pagination?.nextOffset ?? null);
      setHasMoreConversations(payload.pagination?.hasMore ?? false);
      setSelectedId((current) => current || payload.conversations[0]?.id || "");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      }
    } finally {
      isRefreshingList.current = false;
    }
  }, [statusFilter]);

  const loadCalls = useCallback(async (fallbackSelectedRowId = "") => {
    setIsLoadingCalls(true);
    setAppError("");
    try {
      const payload = await getCalls("", 0, 50, callDirectionFilter);
      setCallRows(payload.calls);
      setNextCallOffset(payload.pagination?.nextOffset ?? null);
      setHasMoreCalls(payload.pagination?.hasMore ?? false);
      setSelectedCallRowId((current) => {
        if (current && payload.calls.some((row) => row.id === current)) return current;
        if (fallbackSelectedRowId) return fallbackSelectedRowId;
        return payload.calls[0]?.id || "";
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not load calls.");
      }
    } finally {
      setIsLoadingCalls(false);
    }
  }, [callDirectionFilter]);

  const refreshCalls = useCallback(async ({ force = false }: { force?: boolean } = {}) => {
    if (isRefreshingCalls.current && !force) return;
    isRefreshingCalls.current = true;
    try {
      const payload = await getCalls("", 0, 50, callDirectionFilter);
      setCallRows((current) => {
        const seen = new Set(payload.calls.map((row) => row.id));
        return [...payload.calls, ...current.filter((row) => !seen.has(row.id))];
      });
      setNextCallOffset(payload.pagination?.nextOffset ?? null);
      setHasMoreCalls(payload.pagination?.hasMore ?? false);
      setSelectedCallRowId((current) => current || payload.calls[0]?.id || "");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      }
    } finally {
      isRefreshingCalls.current = false;
    }
  }, [callDirectionFilter]);

  const loadMoreCalls = useCallback(async () => {
    if (nextCallOffset === null || callSearch.trim()) return;
    setIsLoadingMoreCalls(true);
    setAppError("");
    try {
      const payload = await getCalls("", nextCallOffset, 50, callDirectionFilter);
      setCallRows((current) => {
        const seen = new Set(current.map((row) => row.id));
        return [...current, ...payload.calls.filter((row) => !seen.has(row.id))];
      });
      setNextCallOffset(payload.pagination?.nextOffset ?? null);
      setHasMoreCalls(payload.pagination?.hasMore ?? false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not load more calls.");
      }
    } finally {
      setIsLoadingMoreCalls(false);
    }
  }, [callDirectionFilter, callSearch, nextCallOffset]);

  const refreshDetail = useCallback(async (conversationId: string, { force = false }: { force?: boolean } = {}) => {
    if (!conversationId || (isRefreshingDetail.current && !force)) return;
    isRefreshingDetail.current = true;
    try {
      const payload = await getConversationDetail(conversationId);
      setSelectedConversation(payload.conversation);
      setMessages(payload.messages);
      setCalls(payload.calls || []);
      setCustomerActions(payload.customerActions || []);
      setSuggestedReply(payload.suggestedReply || "");
      setDetailError("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      }
    } finally {
      isRefreshingDetail.current = false;
    }
  }, []);

  useEffect(() => {
    getMe()
      .then(() => {
        setIsAuthenticated(true);
      })
      .catch((error) => {
        if (error instanceof ApiError && error.status === 401) {
          setIsAuthenticated(false);
        } else {
          setAuthError(error instanceof Error ? error.message : "Could not check session.");
        }
      })
      .finally(() => setIsCheckingSession(false));
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadConversations();
    getQuickResponses()
      .then((payload) => setQuickResponses(payload.quickResponses))
      .catch((error) => setAppError(error instanceof Error ? error.message : "Could not load quick responses."));
  }, [isAuthenticated, loadConversations]);

  useEffect(() => {
    if (!isAuthenticated || workspaceMode !== "calls") return;
    loadCalls();
  }, [isAuthenticated, loadCalls, workspaceMode]);

  useEffect(() => {
    if (!isAuthenticated) return;
    if (!didRunInitialSearchEffect.current) {
      didRunInitialSearchEffect.current = true;
      return;
    }
    const query = search.trim();
    if (!query) {
      searchRequestId.current += 1;
      setSearchResults(null);
      setContactSearchResults([]);
      setIsSearchingContacts(false);
      setIsSearchingConversations(false);
      return;
    }
    const timeoutId = window.setTimeout(() => {
      const requestId = searchRequestId.current + 1;
      searchRequestId.current = requestId;
      setIsSearchingConversations(true);
      setIsSearchingContacts(true);
      getConversations(query, 0, 50, statusFilter)
        .then((payload) => {
          if (searchRequestId.current === requestId) {
            setSearchResults(payload.conversations);
          }
        })
        .catch((error) => {
          if (searchRequestId.current !== requestId) return;
          if (error instanceof ApiError && error.status === 401) {
            setIsAuthenticated(false);
          } else {
            setAppError(error instanceof Error ? error.message : "Could not search conversations.");
          }
        })
        .finally(() => {
          if (searchRequestId.current === requestId) {
            setIsSearchingConversations(false);
          }
        });
      getContacts(query, 0, 8)
        .then((payload) => {
          if (searchRequestId.current === requestId) {
            setContactSearchResults(payload.items);
          }
        })
        .catch((error) => {
          if (searchRequestId.current !== requestId) return;
          if (error instanceof ApiError && error.status === 401) {
            setIsAuthenticated(false);
          } else {
            setAppError(error instanceof Error ? error.message : "Could not search contacts.");
          }
        })
        .finally(() => {
          if (searchRequestId.current === requestId) {
            setIsSearchingContacts(false);
          }
        });
    }, 250);
    return () => window.clearTimeout(timeoutId);
  }, [isAuthenticated, search, statusFilter]);

  useEffect(() => {
    if (!isAuthenticated || workspaceMode !== "calls") return;
    const query = callSearch.trim();
    if (!query) {
      callSearchRequestId.current += 1;
      setIsSearchingCalls(false);
      void loadCalls();
      return;
    }
    const timeoutId = window.setTimeout(() => {
      const requestId = callSearchRequestId.current + 1;
      callSearchRequestId.current = requestId;
      setIsSearchingCalls(true);
      getCalls(query, 0, 50, callDirectionFilter)
        .then((payload) => {
          if (callSearchRequestId.current !== requestId) return;
          setCallRows(payload.calls);
          setNextCallOffset(payload.pagination?.nextOffset ?? null);
          setHasMoreCalls(payload.pagination?.hasMore ?? false);
          setSelectedCallRowId((current) => {
            if (current && payload.calls.some((row) => row.id === current)) return current;
            return payload.calls[0]?.id || "";
          });
        })
        .catch((error) => {
          if (callSearchRequestId.current !== requestId) return;
          if (error instanceof ApiError && error.status === 401) {
            setIsAuthenticated(false);
          } else {
            setAppError(error instanceof Error ? error.message : "Could not search calls.");
          }
        })
        .finally(() => {
          if (callSearchRequestId.current === requestId) {
            setIsSearchingCalls(false);
          }
        });
    }, 250);
    return () => window.clearTimeout(timeoutId);
  }, [callDirectionFilter, callSearch, isAuthenticated, loadCalls, workspaceMode]);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadDetail(selectedId);
  }, [isAuthenticated, loadDetail, selectedId]);

  useEffect(() => {
    if (!isAuthenticated || !activeContactPhone) {
      setActiveContact(null);
      setProfileError("");
      setProfileStatus("");
      return;
    }
    let isCancelled = false;
    setIsLoadingContact(true);
    setProfileError("");
    getContacts(activeContactPhone, 0, 5)
      .then((payload) => {
        if (isCancelled) return;
        const contact = payload.items.find((item) => cleanPhone(item.phone) === activeContactPhone) || payload.items[0] || null;
        setActiveContact(contact);
      })
      .catch((error) => {
        if (isCancelled) return;
        if (error instanceof ApiError && error.status === 401) {
          setIsAuthenticated(false);
        } else {
          setProfileError(error instanceof Error ? error.message : "Could not load customer profile.");
        }
      })
      .finally(() => {
        if (!isCancelled) setIsLoadingContact(false);
      });
    return () => {
      isCancelled = true;
    };
  }, [activeContactPhone, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated || workspaceMode !== "calls") return;
    if (!selectedCallRow) return;
    const conversationId = selectedCallRow.conversation?.id;
    if (!conversationId) {
      setSelectedId("");
      setSelectedConversation(null);
      setMessages([]);
      setCalls([selectedCallRow.latestCall]);
      setSelectedCallId(selectedCallRow.latestCall.id);
      setSuggestedReply("");
      return;
    }
    if (selectedId !== conversationId) {
      setSelectedId(conversationId);
    }
    setSelectedCallId((current) => current || selectedCallRow.latestCall.id);
  }, [isAuthenticated, selectedCallRow, selectedId, workspaceMode]);

  useEffect(() => {
    scrollMessagesToLatest();
    const timeoutId = window.setTimeout(scrollMessagesToLatest, 120);
    return () => window.clearTimeout(timeoutId);
  }, [latestVisibleMessageId, scrollMessagesToLatest, selectedId]);

  useEffect(() => {
    if (!isAuthenticated) return;
    function auditDocumentClick(event: MouseEvent) {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      if (!button) return;
      closeAuditLog("document button click captured", {
        targetTag: target?.tagName,
        targetClass: target?.getAttribute("class"),
        buttonClass: button.getAttribute("class"),
        buttonText: button.textContent?.trim(),
        buttonAriaLabel: button.getAttribute("aria-label"),
        buttonDisabled: button.hasAttribute("disabled"),
        selectedId,
        selectedConversationStatus: selectedConversation?.status,
        selectedListItemStatus: selectedListItem?.status,
        isCloseConfirmationOpen,
      });
    }
    document.addEventListener("click", auditDocumentClick, true);
    return () => document.removeEventListener("click", auditDocumentClick, true);
  }, [isAuthenticated, isCloseConfirmationOpen, selectedConversation?.status, selectedId, selectedListItem?.status]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      closeAuditLog("auto-refresh interval fired", {
        selectedId,
        search: search.trim(),
        hasDraft: Boolean(draft.trim()),
        fileCount: files.length,
        isCloseConfirmationOpen,
      });
      if (!search.trim()) {
        void refreshConversationList();
      }
      if (workspaceMode === "calls" && !callSearch.trim()) {
        void refreshCalls();
      }
      if (selectedId && !draft.trim() && files.length === 0) {
        void refreshDetail(selectedId);
      }
    }, INBOX_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [callSearch, draft, files.length, isAuthenticated, isCloseConfirmationOpen, refreshCalls, refreshConversationList, refreshDetail, search, selectedId, workspaceMode]);

  useEffect(() => {
    if (!isAuthenticated) return;
    function refreshWhenVisible() {
      if (document.visibilityState !== "visible") return;
      closeAuditLog("focus/visibility refresh fired", {
        selectedId,
        search: search.trim(),
        hasDraft: Boolean(draft.trim()),
        fileCount: files.length,
        isCloseConfirmationOpen,
      });
      if (!search.trim()) {
        void refreshConversationList();
      }
      if (workspaceMode === "calls" && !callSearch.trim()) {
        void refreshCalls();
      }
      if (selectedId && !draft.trim() && files.length === 0) {
        void refreshDetail(selectedId);
      }
    }
    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [callSearch, draft, files.length, isAuthenticated, isCloseConfirmationOpen, refreshCalls, refreshConversationList, refreshDetail, search, selectedId, workspaceMode]);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(max-width: 760px)");
    setIsContextOpen(!mediaQuery.matches);
  }, []);

  async function handleLogin(password: string) {
    setAuthError("");
    try {
      await login(password);
      setIsAuthenticated(true);
    } catch (error) {
      setAuthError(error instanceof ApiError && error.status === 401 ? "Invalid password." : "Could not sign in.");
    }
  }

  async function handleLogout() {
    await logout().catch(() => undefined);
    setIsAuthenticated(false);
    didRunInitialSearchEffect.current = false;
    setConversations([]);
    setWorkspaceMode("text");
    setCallRows([]);
    setSelectedCallRowId("");
    setCallSearch("");
    setCallDirectionFilter("outgoing");
    setNextCallOffset(null);
    setHasMoreCalls(false);
    setSearchResults(null);
    setNextConversationOffset(null);
    setHasMoreConversations(false);
    setSelectedConversation(null);
    setMessages([]);
    setCalls([]);
    setSelectedCallId("");
    setSuggestedReply("");
    setCallStatus("");
    setClosedConversationUndo(null);
  }

  async function handleRefreshInbox() {
    setIsRefreshingInbox(true);
    setAppError("");
    try {
      await Promise.all([
        workspaceMode === "calls"
          ? (callSearch.trim() ? Promise.resolve() : refreshCalls({ force: true }))
          : (search.trim() ? Promise.resolve() : refreshConversationList({ force: true })),
        selectedId ? refreshDetail(selectedId, { force: true }) : Promise.resolve(),
      ]);
    } finally {
      setIsRefreshingInbox(false);
    }
  }

  function handleWorkspaceModeChange(nextMode: WorkspaceMode) {
    setWorkspaceMode(nextMode);
    setAppError("");
    if (nextMode === "calls") {
      setDraft("");
      setFiles([]);
      setClosedConversationUndo(null);
      if (callRows.length === 0) {
        void loadCalls();
      }
    } else {
      setSelectedCallId("");
    }
  }

  function handleSelectCallRow(row: CallConversationListItem) {
    setSelectedCallRowId(row.id);
    setSelectedCallId(row.latestCall.id);
    setDraft("");
    setFiles([]);
    setDetailError("");
    setSuggestedReply("");
    setCallStatus("");
    if (row.conversation?.id) {
      setSelectedId(row.conversation.id);
    }
    if (window.matchMedia("(max-width: 760px)").matches) {
      setIsContextOpen(false);
    }
  }

  function applyContactProfile(contact: ContactProfile) {
    const phone = cleanPhone(contact.phone);
    const customer = {
      phone: contact.phone,
      displayName: contact.displayName,
      lookupName: contact.lookupName,
      name: contact.name,
    };
    setConversations((current) =>
      current.map((conversation) =>
        cleanPhone(conversation.customer.phone) === phone ? { ...conversation, customer } : conversation,
      ),
    );
    setSearchResults((current) =>
      current
        ? current.map((conversation) =>
          cleanPhone(conversation.customer.phone) === phone ? { ...conversation, customer } : conversation,
        )
        : current,
    );
    setSelectedConversation((current) =>
      current && cleanPhone(current.customer.phone) === phone ? { ...current, customer } : current,
    );
    setCallRows((current) =>
      current.map((row) =>
        cleanPhone(row.customer.phone || row.latestCall.customerPhone) === phone ? { ...row, customer } : row,
      ),
    );
  }

  async function handleSaveContactProfile(payload: { displayName: string; notes: string }) {
    if (!activeContact) return;
    setIsSavingProfile(true);
    setProfileError("");
    setProfileStatus("");
    setAppError("");
    try {
      const response = await updateContact(activeContact.id, {
        displayName: payload.displayName,
        notes: payload.notes,
      });
      setActiveContact(response.contact);
      applyContactProfile(response.contact);
      setProfileStatus("Saved customer profile.");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setProfileError(error instanceof Error ? error.message : "Could not save customer profile.");
      }
      throw error;
    } finally {
      setIsSavingProfile(false);
    }
  }

  function handleSelectContactResult(contact: ContactSearchItem) {
    const targetConversationId = contact.openConversationId || contact.lastConversationId;
    if (!targetConversationId) {
      setActiveContact(contact);
      setIsProfileEditorOpen(true);
      return;
    }
    setWorkspaceMode("text");
    setSelectedId(targetConversationId);
    setDraft("");
    setFiles([]);
    setDetailError("");
    setSuggestedReply("");
    setCallStatus("");
    if (window.matchMedia("(max-width: 760px)").matches) {
      setIsContextOpen(false);
    }
  }

  async function handleImportContacts(file: File, overwrite: boolean): Promise<ContactImportResponse> {
    setAppError("");
    try {
      const result = await importContactsCsv(file, overwrite);
      await loadConversations(selectedId);
      if (workspaceMode === "calls") {
        await refreshCalls({ force: true });
      }
      return result;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      }
      throw error;
    }
  }

  async function handleSend(body: string, selectedFiles: File[]) {
    if (!selectedId) return;
    setSuggestedReply("");
    setAppError("");
    try {
      const response = await sendReply(selectedId, body, selectedFiles, newClientRequestId());
      setMessages((current) => {
        const withoutDuplicate = current.filter((message) => message.id !== response.message.id);
        return [...withoutDuplicate, response.message];
      });
      await loadConversations(selectedId);
      setSuggestedReply("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not send the message. Please try again.");
      }
      throw error;
    }
  }

  function handleUseQuickResponse(response: QuickResponse) {
    setQuickResponseError("");
    if (response.templateKey) {
      setSelectedQuickResponse(response);
      return;
    }
    setDraft(response.body);
  }

  async function handleSendQuickResponse(variables: Record<string, string>) {
    if (!selectedId || !selectedQuickResponse) return;
    setIsSendingQuickResponse(true);
    setQuickResponseError("");
    setAppError("");
    try {
      const response = await sendQuickResponse(selectedId, selectedQuickResponse.id, {
        variables,
        clientRequestId: newClientRequestId(),
      });
      setMessages((current) => {
        const withoutDuplicate = current.filter((message) => message.id !== response.message.id);
        return [...withoutDuplicate, response.message];
      });
      setCallStatus("Quick response sent.");
      setSelectedQuickResponse(null);
      await refreshDetail(selectedId, { force: true });
      await loadConversations(selectedId);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setQuickResponseError(error instanceof Error ? error.message : "Could not send the quick response.");
      }
    } finally {
      setIsSendingQuickResponse(false);
    }
  }

  async function handleSendProofRequest(payload: {
    proofFile: File;
    title: string;
    customerMessage: string;
    operatorNote: string;
  }) {
    if (!selectedId) return;
    if (pendingProofRequest) {
      setProofRequestError("Cancel the pending proof request before sending another one.");
      return;
    }
    setIsSendingProofRequest(true);
    setProofRequestError("");
    setAppError("");
    setCallStatus("");
    try {
      const response = await createProofRequest(selectedId, {
        proofFile: payload.proofFile,
        title: payload.title || null,
        customerMessage: payload.customerMessage || null,
        operatorNote: payload.operatorNote || null,
      });
      setMessages((current) => {
        const withoutDuplicate = current.filter((message) => message.id !== response.message.id);
        return [...withoutDuplicate, response.message];
      });
      setCallStatus("Proof request sent.");
      setIsProofRequestOpen(false);
      await refreshDetail(selectedId, { force: true });
      await loadConversations(selectedId);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setProofRequestError(error instanceof Error ? error.message : "Could not send the proof request.");
      }
    } finally {
      setIsSendingProofRequest(false);
    }
  }

  async function handleSendAssetsRequest(payload: {
    title: string;
    customerMessage: string;
    operatorNote: string;
  }) {
    if (!selectedId) return;
    if (pendingAssetsRequest) {
      setAssetsRequestError("Cancel the pending asset request before sending another one.");
      return;
    }
    setIsSendingAssetsRequest(true);
    setAssetsRequestError("");
    setAppError("");
    setCallStatus("");
    try {
      const response = await createAssetRequest(selectedId, {
        title: payload.title || null,
        customerMessage: payload.customerMessage || null,
        operatorNote: payload.operatorNote || null,
      });
      setMessages((current) => {
        const withoutDuplicate = current.filter((message) => message.id !== response.message.id);
        return [...withoutDuplicate, response.message];
      });
      setCallStatus("Asset request sent.");
      setIsAssetsRequestOpen(false);
      await refreshDetail(selectedId, { force: true });
      await loadConversations(selectedId);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAssetsRequestError(error instanceof Error ? error.message : "Could not send the asset request.");
      }
    } finally {
      setIsSendingAssetsRequest(false);
    }
  }

  async function handleCancelCustomerAction(requestId: string) {
    if (!selectedId || !requestId) return;
    setCancelingCustomerActionId(requestId);
    setAppError("");
    setCallStatus("");
    try {
      const response = await cancelCustomerActionRequest(requestId);
      setCustomerActions((current) =>
        current.map((request) => (request.id === requestId ? response.customerAction : request)),
      );
      setCallStatus("Request canceled.");
      await refreshDetail(selectedId, { force: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not cancel the request.");
      }
    } finally {
      setCancelingCustomerActionId("");
    }
  }

  async function updateActiveConversationStatus(nextStatus: ConversationStatus) {
    if (!selectedId || !activeConversation) {
      closeAuditLog("status update aborted", {
        nextStatus,
        selectedId,
        hasActiveConversation: Boolean(activeConversation),
      });
      return;
    }
    closeAuditLog("status update starting", {
      selectedId,
      currentStatus: activeConversation.status,
      nextStatus,
      isCloseConfirmationOpen,
    });
    setIsUpdatingStatus(true);
    setAppError("");
    try {
      const response = await updateConversationStatus(selectedId, nextStatus);
      closeAuditLog("status update succeeded", {
        selectedId,
        nextStatus,
        responseStatus: response.conversation.status,
      });
      setSelectedConversation(response.conversation);
      setIsCloseConfirmationOpen(false);
      if (nextStatus === "closed") {
        setClosedConversationUndo({ id: selectedId, name: displayCustomerName(activeConversation) });
      } else {
        setClosedConversationUndo(null);
      }
      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === selectedId ? { ...conversation, status: response.conversation.status } : conversation,
        ),
      );
      await loadConversations(selectedId);
    } catch (error) {
      closeAuditLog("status update failed", {
        selectedId,
        nextStatus,
        error: error instanceof Error ? error.message : String(error),
      });
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not update conversation.");
      }
    } finally {
      setIsUpdatingStatus(false);
    }
  }

  function handleRequestCloseConversation() {
    closeAuditLog("close requested", {
      selectedId,
      status: activeConversation?.status,
      hasActiveConversation: Boolean(activeConversation),
      isUpdatingStatus,
      isCloseConfirmationOpen,
    });
    setIsCloseConfirmationOpen(true);
  }

  function handleCancelCloseConversation() {
    closeAuditLog("close confirmation cancel clicked", {
      selectedId,
      isUpdatingStatus,
      isCloseConfirmationOpen,
    });
    if (isUpdatingStatus) return;
    setIsCloseConfirmationOpen(false);
  }

  async function handleConfirmCloseConversation() {
    closeAuditLog("close confirmation confirm clicked", {
      selectedId,
      status: activeConversation?.status,
      hasActiveConversation: Boolean(activeConversation),
      isUpdatingStatus,
      isCloseConfirmationOpen,
    });
    await updateActiveConversationStatus("closed");
  }

  async function handleReopenConversation() {
    await updateActiveConversationStatus("open");
  }

  async function handleUndoCloseConversation() {
    if (!closedConversationUndo) return;
    setIsUpdatingStatus(true);
    setAppError("");
    try {
      const response = await updateConversationStatus(closedConversationUndo.id, "open");
      setSelectedConversation(response.conversation);
      setSelectedId(response.conversation.id);
      setClosedConversationUndo(null);
      setStatusFilter("open");
      await loadConversations(response.conversation.id);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not reopen conversation.");
      }
    } finally {
      setIsUpdatingStatus(false);
    }
  }

  async function handleCallCustomer() {
    if (!selectedId) return;
    setIsCallingCustomer(true);
    setAppError("");
    setCallStatus("");
    try {
      const response = await callConversationCustomer(selectedId);
      setCallStatus(`Calling Francisco first, then ${response.to}.`);
      await refreshDetail(selectedId, { force: true });
      if (workspaceMode === "calls") {
        await refreshCalls({ force: true });
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not start the call.");
      }
    } finally {
      setIsCallingCustomer(false);
    }
  }

  async function handleStartNewCall(phoneNumber: string, displayName: string) {
    setIsCallingCustomer(true);
    setAppError("");
    setCallStatus("");
    try {
      const response = await startNewCall(phoneNumber, displayName);
      setIsNewCallOpen(false);
      setSelectedConversation(response.conversation);
      setSelectedId(response.conversation.id);
      setMessages([]);
      setCalls([]);
      setSelectedCallId("");
      setSuggestedReply("");
      setDraft("");
      setFiles([]);
      setCallStatus(`Calling Francisco first, then ${response.to}.`);
      await loadConversations(response.conversation.id);
      await refreshDetail(response.conversation.id, { force: true });
      if (workspaceMode === "calls") {
        await refreshCalls({ force: true });
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not start the call.");
      }
      throw error;
    } finally {
      setIsCallingCustomer(false);
    }
  }

  async function handleSaveCallDetails(
    callId: string,
    payload: {
      outcome: CallOutcome | null;
      followUpStatus: FollowUpStatus;
      notes: string;
      recap: string;
      transcription: string;
    },
  ) {
    setAppError("");
    const response = await updateCallDetails(callId, {
      outcome: payload.outcome,
      follow_up_status: payload.followUpStatus,
      notes: payload.notes.trim() || null,
      recap: payload.recap.trim() || null,
      transcription: payload.transcription.trim() || null,
    });
    setCalls((current) => current.map((call) => (call.id === callId ? response.call : call)));
    setCallRows((current) =>
      current.map((row) => (
        row.latestCall.id === callId
          ? {
            ...row,
            latestCall: response.call,
            workflowStatus: !response.call.outcome || ["needed", "scheduled"].includes(response.call.followUpStatus)
              ? "pending_follow_up"
              : "done",
          }
          : row
      )),
    );
  }

  async function handleTranscribeCall(callId: string) {
    setAppError("");
    try {
      const response = await transcribeCall(callId);
      setCalls((current) => current.map((call) => (call.id === callId ? response.call : call)));
      setCallRows((current) =>
        current.map((row) => (
          row.latestCall.id === callId
            ? {
              ...row,
              latestCall: response.call,
              workflowStatus: !response.call.outcome || ["needed", "scheduled"].includes(response.call.followUpStatus)
                ? "pending_follow_up"
                : "done",
            }
            : row
        )),
      );
    } catch (error) {
      setAppError(error instanceof Error ? error.message : "Could not transcribe the call recording.");
      throw error;
    }
  }

  async function handleGenerateCallRecap(callId: string) {
    setAppError("");
    try {
      const response = await generateCallRecap(callId);
      setCalls((current) => current.map((call) => (call.id === callId ? response.call : call)));
      setCallRows((current) =>
        current.map((row) => (
          row.latestCall.id === callId
            ? {
              ...row,
              latestCall: response.call,
              workflowStatus: !response.call.outcome || ["needed", "scheduled"].includes(response.call.followUpStatus)
                ? "pending_follow_up"
                : "done",
            }
            : row
        )),
      );
    } catch (error) {
      setAppError(error instanceof Error ? error.message : "Could not generate the call recap.");
      throw error;
    }
  }

  if (isCheckingSession) {
    return (
      <main className="loading-screen">
        <RefreshCw size={28} />
      </main>
    );
  }

  if (!isAuthenticated) {
    return <LoginScreen error={authError} onLogin={handleLogin} />;
  }

  const activeConversation = selectedConversation || selectedListItem;
  const customerName = activeConversation ? displayCustomerName(activeConversation) : "No conversation selected";
  const customerPhone = activeConversation?.customer.phone || "";
  const displayPhone = cleanPhone(customerPhone);
  const channel = effectiveChannel(activeConversation?.channel || "sms", customerPhone);
  const status = activeConversation?.status || "open";
  const contextCustomerName =
    workspaceMode === "calls" && selectedCallRow
      ? selectedCallRow.customer.name || cleanPhone(selectedCallRow.customer.phone) || cleanPhone(selectedCallRow.latestCall.customerPhone) || "Unknown customer"
      : customerName;
  const contextDisplayPhone =
    workspaceMode === "calls" && selectedCallRow
      ? cleanPhone(selectedCallRow.customer.phone || selectedCallRow.latestCall.customerPhone)
      : displayPhone;
  const contextCode = workspaceMode === "calls" ? selectedCallRow?.conversation?.code : activeConversation?.code;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <img alt="Maya Graphics and Signs" src={logoMaya} />
          <div>
            <strong>MAYA</strong>
            <span>RELAY</span>
          </div>
        </div>
        <div className="topbar-actions">
          <button
            aria-label="Refresh inbox"
            className="refresh-button"
            disabled={isRefreshingInbox}
            onClick={handleRefreshInbox}
            type="button"
          >
            <RefreshCw size={18} />
            Refresh
          </button>
          <button className="new-call-button" onClick={() => setIsNewCallOpen(true)} type="button">
            <Plus size={18} />
            New call
          </button>
          <button className="settings-button" onClick={() => setIsSettingsOpen(true)} type="button">
            <SettingsIcon size={18} />
            Settings
          </button>
          <button className="logout-button" onClick={handleLogout} type="button">
            <LogOut size={18} />
            Logout
          </button>
        </div>
      </header>

      <main className="workspace">
        <aside className="inbox-panel">
          <WorkspaceTabs mode={workspaceMode} onModeChange={handleWorkspaceModeChange} />

          {workspaceMode === "text" ? (
            <>
              <label className="search-box">
                <Search size={20} />
                <input
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search conversations or contacts..."
                  type="search"
                  value={search}
                />
              </label>

              <div className="conversation-filter" role="group" aria-label="Conversation status filter">
                {(["open", "closed", "all"] as ConversationStatusFilter[]).map((filter) => (
                  <button
                    className={statusFilter === filter ? "is-active" : ""}
                    key={filter}
                    onClick={() => {
                      setStatusFilter(filter);
                      setSearchResults(null);
                      setContactSearchResults([]);
                      setNextConversationOffset(null);
                      setHasMoreConversations(false);
                      setClosedConversationUndo(null);
                    }}
                    type="button"
                  >
                    {filter === "all" ? "All" : filter}
                  </button>
                ))}
              </div>

              <div className="conversation-list">
                <UnifiedSearchResults
                  contacts={contactSearchResults}
                  isSearching={isSearchingContacts}
                  onSelectContact={handleSelectContactResult}
                  query={search}
                />
                {isLoadingList && <p className="panel-note">Loading conversations...</p>}
                {!isLoadingList && visibleConversations.length === 0 && <p className="panel-note">No conversations found.</p>}
                {visibleConversations.map((conversation) => (
                  (() => {
                    const listChannel = effectiveChannel(conversation.channel, conversation.customer.phone);
                    const requiresReply = needsReply(conversation);
                    return (
                      <button
                        className={[
                          "conversation-row",
                          `channel-${listChannel}`,
                          `delivery-${deliveryStatus(conversation)}`,
                          `status-${conversation.status}`,
                          requiresReply ? "needs-reply" : "",
                          conversation.id === selectedId ? "selected" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        key={conversation.id}
                        onClick={() => {
                          setSelectedId(conversation.id);
                          setDraft("");
                          setFiles([]);
                          setDetailError("");
                          setSuggestedReply("");
                          setCallStatus("");
                          if (window.matchMedia("(max-width: 760px)").matches) {
                            setIsContextOpen(false);
                          }
                        }}
                        type="button"
                      >
                        <span className="conversation-row-heading">
                          <span className="conversation-identity">
                            <strong>{displayCustomerName(conversation)}</strong>
                            <span className={`channel-pill ${listChannel}`}>{channelLabel(listChannel)}</span>
                            {conversation.status === "closed" && <span className="closed-pill">Closed</span>}
                            {requiresReply && <span className="attention-pill">Needs reply</span>}
                            {(deliveryStatus(conversation) === "failed" || deliveryStatus(conversation) === "undelivered") && (
                              <DeliveryPill status={deliveryStatus(conversation)} />
                            )}
                          </span>
                          <em>{relativeDate(conversation.updatedAt)}</em>
                        </span>
                        <p>{previewBody(conversation)}</p>
                      </button>
                    );
                  })()
                ))}
                {search.trim() && isSearchingConversations && (
                  <p className="panel-note">Searching older conversations...</p>
                )}
                {!search.trim() && hasMoreConversations && (
                  <button
                    className="load-more-button"
                    disabled={isLoadingMore}
                    onClick={loadMoreConversations}
                    type="button"
                  >
                    {isLoadingMore ? "Loading..." : "Load more"}
                  </button>
                )}
              </div>
            </>
          ) : (
            <CallsPanel
              directionFilter={callDirectionFilter}
              hasMore={hasMoreCalls}
              isLoading={isLoadingCalls}
              isLoadingMore={isLoadingMoreCalls}
              isSearching={isSearchingCalls}
              onDirectionChange={(filter) => {
                setCallDirectionFilter(filter);
                setNextCallOffset(null);
                setHasMoreCalls(false);
                setSelectedCallRowId("");
              }}
              onLoadMore={loadMoreCalls}
              onSearchChange={setCallSearch}
              onSelect={handleSelectCallRow}
              rows={callRows}
              search={callSearch}
              selectedId={selectedCallRowId}
            />
          )}
        </aside>

        {workspaceMode === "text" ? (
        <section className={`conversation-panel channel-${channel}`}>
          <header className="conversation-header">
            <div className="conversation-title-block">
              <h1>{customerName}</h1>
              {activeConversation?.code && <span className="session-id">Session ID: #{activeConversation.code}</span>}
              <div className="conversation-meta-row">
                <p>
                  <span className="desktop-channel-label">via {channelLabel(channel)} </span>
                  <span className="chat-phone">{displayPhone}</span>
                  <span className="mobile-channel-label">via {channelLabel(channel)}</span>
                </p>
                <div className="conversation-header-actions">
                  <StatusPill status={status} />
                  <ProofActionButton
                    disabled={!selectedId || status !== "open" || isSendingProofRequest || Boolean(pendingProofRequest)}
                    onClick={() => {
                      setProofRequestError("");
                      setIsProofRequestOpen(true);
                    }}
                  />
                  <AssetActionButton
                    disabled={!selectedId || status !== "open" || isSendingAssetsRequest || Boolean(pendingAssetsRequest)}
                    onClick={() => {
                      setAssetsRequestError("");
                      setIsAssetsRequestOpen(true);
                    }}
                  />
                  <button
                    className="conversation-call-action"
                    disabled={!selectedId || isCallingCustomer}
                    onClick={handleCallCustomer}
                    type="button"
                  >
                    <Phone size={15} />
                    {isCallingCustomer ? "Calling" : "Call"}
                  </button>
                  <button
                    aria-label={status === "open" ? "Close conversation" : "Reopen conversation"}
                    className={`conversation-status-action ${status === "open" ? "is-close-action" : "is-reopen-action"}`}
                    disabled={!selectedId || isUpdatingStatus}
                    onClick={() => {
                      closeAuditLog("status action button clicked", {
                        selectedId,
                        status,
                        isUpdatingStatus,
                        isCloseConfirmationOpen,
                      });
                      if (status === "open") {
                        handleRequestCloseConversation();
                      } else {
                        void handleReopenConversation();
                      }
                    }}
                    type="button"
                  >
                    <Archive size={15} />
                    {status === "open" ? "Close" : "Reopen"}
                  </button>
                  <button
                    aria-label={isContextOpen ? "Hide details" : "Details"}
                    className="context-toggle"
                    onClick={() => setIsContextOpen((current) => !current)}
                    type="button"
                  >
                    {isContextOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
                    <span>{isContextOpen ? "Hide details" : "Details"}</span>
                  </button>
                </div>
              </div>
            </div>
          </header>

          <div className="message-thread" ref={messageThreadRef}>
            {appError && <p className="app-error">{appError}</p>}
            {callStatus && <p className="app-success">{callStatus}</p>}
            {closedConversationUndo && (
              <div className="app-success action-notice">
                <span>{closedConversationUndo.name} was closed.</span>
                <button disabled={isUpdatingStatus} onClick={handleUndoCloseConversation} type="button">
                  Undo
                </button>
              </div>
            )}
            {status === "closed" && (
              <p className="panel-note closed-note">This conversation is closed. Reopen it to send a reply.</p>
            )}
            {detailError && <p className="app-error">Could not load this conversation. Try selecting it again.</p>}
            {isLoadingDetail && <p className="panel-note">Loading messages...</p>}
            {!isLoadingDetail && !detailError && visibleMessages.length === 0 && <p className="panel-note">No messages yet.</p>}
            {visibleMessages.map((message) => (
              <MessageBubble key={message.id} message={message} onMediaLoad={scrollMessagesToLatest} />
            ))}
            <div aria-hidden="true" className="message-thread-end" ref={messageThreadEndRef} />
          </div>

          <Composer
            disabled={!selectedId || status === "closed"}
            draft={draft}
            files={files}
            onDraftChange={setDraft}
            onFilesChange={setFiles}
            onSend={handleSend}
          />
        </section>
        ) : (
          <CallWorkspace
            calls={calls}
            isLoadingDetail={isLoadingDetail}
            onGenerateCallRecap={handleGenerateCallRecap}
            onSaveCallDetails={handleSaveCallDetails}
            onSelectCall={setSelectedCallId}
            onTranscribeCall={handleTranscribeCall}
            selectedCall={selectedCall}
            selectedRow={selectedCallRow}
          />
        )}

        <aside className={`context-panel mobile-drawer ${isContextOpen ? "is-open" : "is-collapsed"}`}>
          <div className="context-panel-header">
            <span>Details</span>
            <button aria-label="Close details panel" onClick={() => setIsContextOpen(false)} type="button">
              <X size={18} />
            </button>
          </div>

          <CustomerProfileSummary
            canEdit={Boolean(activeContact)}
            isLoading={isLoadingContact}
            name={activeContact?.name || contextCustomerName}
            notes={activeContact?.notes}
            onEdit={() => {
              setProfileError("");
              setProfileStatus("");
              setIsProfileEditorOpen(true);
            }}
            phone={contextDisplayPhone}
            sessionCode={contextCode}
          />

          <section className="context-section">
            <div className="ai-suggestion-heading">
              <h2>
                <Sparkles size={18} />
                AI Suggested Reply
              </h2>
              <span className={`suggestion-status-pill ${suggestedReply ? "ready" : "empty"}`}>
                {suggestedReply ? "Ready" : "No suggestion"}
              </span>
            </div>
            <div className={`intent-box ${suggestedReply ? "has-suggestion" : "is-empty"}`}>
              <p>{suggestedReply || "No AI suggestion is available for this conversation yet."}</p>
              {suggestedReply && (
                <button
                  className="secondary-action compact"
                  onClick={() => {
                    setDraft(suggestedReply);
                    setSuggestedReply("");
                  }}
                  type="button"
                >
                  Use suggested reply
                </button>
              )}
            </div>
          </section>

          <CustomerActionPanelTabs
            cancelingRequestId={cancelingCustomerActionId}
            channel={channel}
            onCancelRequest={handleCancelCustomerAction}
            onUseResponse={handleUseQuickResponse}
            requests={customerActions}
            responses={quickResponses}
          />
        </aside>
      </main>
      <NewCallDrawer
        onClose={() => setIsNewCallOpen(false)}
        onStartCall={handleStartNewCall}
        open={isNewCallOpen}
      />
      <EditCustomerProfileModal
        contact={activeContact}
        error={profileError}
        fallbackName={contextCustomerName}
        isSaving={isSavingProfile}
        onClose={() => setIsProfileEditorOpen(false)}
        onSave={handleSaveContactProfile}
        open={isProfileEditorOpen}
        phone={contextDisplayPhone}
        status={profileStatus}
      />
      <ProofRequestModal
        channel={channel}
        customerName={customerName}
        customerPhone={displayPhone}
        error={proofRequestError}
        isSending={isSendingProofRequest}
        onClose={() => {
          if (isSendingProofRequest) return;
          setProofRequestError("");
          setIsProofRequestOpen(false);
        }}
        onSend={handleSendProofRequest}
        open={isProofRequestOpen}
      />
      <AssetsRequestModal
        channel={channel}
        customerName={customerName}
        customerPhone={displayPhone}
        error={assetsRequestError}
        isSending={isSendingAssetsRequest}
        onClose={() => {
          if (isSendingAssetsRequest) return;
          setAssetsRequestError("");
          setIsAssetsRequestOpen(false);
        }}
        onSend={handleSendAssetsRequest}
        open={isAssetsRequestOpen}
      />
      <QuickResponseSendModal
        customerName={contextCustomerName}
        error={quickResponseError}
        isSending={isSendingQuickResponse}
        onClose={() => {
          if (isSendingQuickResponse) return;
          setQuickResponseError("");
          setSelectedQuickResponse(null);
        }}
        onSend={handleSendQuickResponse}
        response={selectedQuickResponse}
      />
      <SettingsModal onClose={() => setIsSettingsOpen(false)} open={isSettingsOpen}>
        <OperationalStatusView />
        <ContactCsvImport onImport={handleImportContacts} />
      </SettingsModal>
      <CloseConversationModal
        customerName={activeConversation ? displayCustomerName(activeConversation) : "This conversation"}
        isSubmitting={isUpdatingStatus}
        onCancel={handleCancelCloseConversation}
        onConfirm={() => {
          void handleConfirmCloseConversation();
        }}
        open={isCloseConfirmationOpen}
      />
      <CallDetailsDrawer
        call={selectedCall}
        onClose={() => setSelectedCallId("")}
        onGenerateRecap={handleGenerateCallRecap}
        onSave={handleSaveCallDetails}
        onTranscribe={handleTranscribeCall}
        open={workspaceMode === "text" && Boolean(selectedCall)}
      />
    </div>
  );
}
