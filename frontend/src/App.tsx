import {
  AlertTriangle,
  Archive,
  CheckCircle2,
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
  Sparkles,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  Channel,
  ConversationDetail,
  ConversationListItem,
  ConversationStatus,
  DeliveryStatus,
  Message,
  Metrics,
  QuickResponse,
  callConversationCustomer,
  getConversationDetail,
  getConversations,
  getMe,
  getQuickResponses,
  login,
  logout,
  sendReply,
  startNewCall,
  updateConversationStatus,
} from "./api";
import logoMaya from "./assets/logo-maya.jpg";

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
  return body
    .replace(/^From\s+.*?(?:\s+\[#?[A-Za-z0-9]+\])?:\s*/i, "")
    .replace(/\s+Reply with\s+#[A-Za-z0-9]+\s+your message(?:\s+---[\s\S]*)?$/i, "")
    .replace(/\s+---\s+AI note:[\s\S]*$/i, "")
    .trim();
}

function previewBody(conversation: ConversationListItem) {
  if (conversation.lastMessage?.body) return cleanRelayBody(conversation.lastMessage.body);
  if (conversation.lastMessage?.hasAttachments) return "Attachment received";
  return "No messages yet";
}

function deliveryStatus(conversation: ConversationListItem): DeliveryStatus {
  return conversation.lastMessage?.deliveryStatus || "pending";
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

function newClientRequestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function MetricCard({
  label,
  value,
  active,
  warning,
}: {
  label: string;
  value: number;
  active?: boolean;
  warning?: boolean;
}) {
  return (
    <button className={`metric-card ${active ? "is-active" : ""}`} type="button">
      <span>{label}</span>
      <strong className={warning ? "warning" : ""}>{value}</strong>
    </button>
  );
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

function MessageBubble({ message }: { message: Message }) {
  const isOutbound = message.direction === "employee_to_customer";
  const body = cleanRelayBody(message.body);

  return (
    <article className={`message-bubble ${isOutbound ? "outbound" : "inbound"}`}>
      {message.attachments.map((attachment) => (
        <a className="attachment-preview" href={attachment.url} key={attachment.url} rel="noreferrer" target="_blank">
          {attachment.kind === "image" ? (
            <img alt="Message attachment" src={attachment.url} />
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

function NewCallModal({
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

  if (!open) return null;

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
    <div className="modal-backdrop" role="presentation">
      <section aria-labelledby="new-call-title" aria-modal="true" className="modal-panel" role="dialog">
        <div className="modal-header">
          <div>
            <h2 id="new-call-title">New call</h2>
            <p>Francisco receives the first call, then Maya Relay connects the customer.</p>
          </div>
          <button aria-label="Close new call modal" className="modal-close" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>
        <form className="modal-form" onSubmit={handleSubmit}>
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
          <div className="modal-actions">
            <button className="ghost-button" disabled={isSubmitting} onClick={onClose} type="button">
              Cancel
            </button>
            <button className="send-button" disabled={!phoneNumber.trim() || isSubmitting} type="submit">
              <Phone size={17} />
              {isSubmitting ? "Calling..." : "Start call"}
            </button>
          </div>
        </form>
      </section>
    </div>
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
  const canSend = draft.trim().length > 0 || files.length > 0;

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

  return (
    <form className="composer" onSubmit={handleSubmit}>
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
            onChange={(event) => onFilesChange(Array.from(event.target.files ?? []))}
            type="file"
          />
        </label>
        <textarea
          aria-label="Reply message"
          disabled={disabled || isSending}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="Message"
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
  const [selectedId, setSelectedId] = useState("");
  const [selectedConversation, setSelectedConversation] = useState<ConversationDetail | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [quickResponses, setQuickResponses] = useState<QuickResponse[]>([]);
  const [suggestedReply, setSuggestedReply] = useState("");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [isCallingCustomer, setIsCallingCustomer] = useState(false);
  const [isNewCallOpen, setIsNewCallOpen] = useState(false);
  const [callStatus, setCallStatus] = useState("");
  const [appError, setAppError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [isContextOpen, setIsContextOpen] = useState(() => {
    if (typeof window === "undefined") return true;
    return !window.matchMedia("(max-width: 760px)").matches;
  });

  const selectedListItem = useMemo(
    () => conversations.find((conversation) => conversation.id === selectedId) || null,
    [conversations, selectedId],
  );

  const loadConversations = useCallback(
    async (query = search) => {
      setIsLoadingList(true);
      setAppError("");
      try {
        const payload = await getConversations(query);
        setConversations(payload.conversations);
        setMetrics(payload.metrics);
        setSelectedId((current) => {
          if (current && payload.conversations.some((conversation) => conversation.id === current)) return current;
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
    },
    [search],
  );

  const loadDetail = useCallback(async (conversationId: string) => {
    if (!conversationId) {
      setSelectedConversation(null);
      setMessages([]);
      setSuggestedReply("");
      setCallStatus("");
      return;
    }
    setIsLoadingDetail(true);
    setAppError("");
    setDetailError("");
    setSelectedConversation(null);
    setMessages([]);
    setSuggestedReply("");
    setCallStatus("");
    try {
      const payload = await getConversationDetail(conversationId);
      setSelectedConversation(payload.conversation);
      setMessages(payload.messages);
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
    loadConversations("");
    getQuickResponses()
      .then((payload) => setQuickResponses(payload.quickResponses))
      .catch((error) => setAppError(error instanceof Error ? error.message : "Could not load quick responses."));
  }, [isAuthenticated, loadConversations]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const timeoutId = window.setTimeout(() => {
      loadConversations(search);
    }, 250);
    return () => window.clearTimeout(timeoutId);
  }, [isAuthenticated, loadConversations, search]);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadDetail(selectedId);
  }, [isAuthenticated, loadDetail, selectedId]);

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
    setConversations([]);
    setSelectedConversation(null);
    setMessages([]);
    setSuggestedReply("");
    setCallStatus("");
  }

  async function handleSend(body: string, selectedFiles: File[]) {
    if (!selectedId) return;
    setSuggestedReply("");
    const response = await sendReply(selectedId, body, selectedFiles, newClientRequestId());
    setMessages((current) => {
      const withoutDuplicate = current.filter((message) => message.id !== response.message.id);
      return [...withoutDuplicate, response.message];
    });
    await loadConversations(search);
    await loadDetail(selectedId);
    setSuggestedReply("");
  }

  async function handleToggleConversationStatus() {
    if (!selectedId || !activeConversation) return;
    const nextStatus: ConversationStatus = activeConversation.status === "open" ? "closed" : "open";
    setIsUpdatingStatus(true);
    setAppError("");
    try {
      const response = await updateConversationStatus(selectedId, nextStatus);
      setSelectedConversation(response.conversation);
      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === selectedId ? { ...conversation, status: response.conversation.status } : conversation,
        ),
      );
      await loadConversations(search);
      await loadDetail(selectedId);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setIsAuthenticated(false);
      } else {
        setAppError(error instanceof Error ? error.message : "Could not update conversation.");
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
      setSuggestedReply("");
      setDraft("");
      setFiles([]);
      setCallStatus(`Calling Francisco first, then ${response.to}.`);
      await loadConversations(search);
      setSelectedId(response.conversation.id);
      await loadDetail(response.conversation.id);
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
          <button className="new-call-button" onClick={() => setIsNewCallOpen(true)} type="button">
            <Plus size={18} />
            New call
          </button>
          <button className="logout-button" onClick={handleLogout} type="button">
            <LogOut size={18} />
            Logout
          </button>
        </div>
      </header>

      <main className="workspace">
        <aside className="inbox-panel">
          <div className="metrics-row">
            <MetricCard active label="Open" value={metrics.open} />
            <MetricCard label="Failed" value={metrics.failed} warning />
            <MetricCard label="Recent" value={metrics.recent} />
          </div>

          <label className="search-box">
            <Search size={20} />
            <input
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search conversations..."
              type="search"
              value={search}
            />
          </label>

          <div className="conversation-list">
            {isLoadingList && <p className="panel-note">Loading conversations...</p>}
            {!isLoadingList && conversations.length === 0 && <p className="panel-note">No conversations found.</p>}
            {conversations.map((conversation) => (
              (() => {
                const listChannel = effectiveChannel(conversation.channel, conversation.customer.phone);
                return (
                  <button
                    className={[
                      "conversation-row",
                      `channel-${listChannel}`,
                      `delivery-${deliveryStatus(conversation)}`,
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
          </div>
        </aside>

        <section className={`conversation-panel channel-${channel}`}>
          <header className="conversation-header">
            <div className="conversation-title-block">
              <h1>{customerName}</h1>
              <div className="conversation-meta-row">
                <p>
                  <span className="desktop-channel-label">via {channelLabel(channel)} </span>
                  <span className="chat-phone">{displayPhone}</span>
                  <span className="mobile-channel-label">via {channelLabel(channel)}</span>
                </p>
                <div className="conversation-header-actions">
                  <StatusPill status={status} />
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
                    className="conversation-status-action"
                    disabled={!selectedId || isUpdatingStatus}
                    onClick={handleToggleConversationStatus}
                    type="button"
                  >
                    <Archive size={15} />
                    {status === "open" ? "Close" : "Reopen"}
                  </button>
                  <button className="context-toggle" onClick={() => setIsContextOpen((current) => !current)} type="button">
                    {isContextOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
                    <span>{isContextOpen ? "Hide details" : "Details"}</span>
                  </button>
                </div>
              </div>
            </div>
          </header>

          <div className="message-thread">
            {appError && <p className="app-error">{appError}</p>}
            {callStatus && <p className="app-success">{callStatus}</p>}
            {detailError && <p className="app-error">Could not load this conversation. Try selecting it again.</p>}
            {isLoadingDetail && <p className="panel-note">Loading messages...</p>}
            {!isLoadingDetail && !detailError && messages.length === 0 && <p className="panel-note">No messages yet.</p>}
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>

          <Composer
            disabled={!selectedId}
            draft={draft}
            files={files}
            onDraftChange={setDraft}
            onFilesChange={setFiles}
            onSend={handleSend}
          />
        </section>

        <aside className={`context-panel ${isContextOpen ? "is-open" : "is-collapsed"}`}>
          <div className="context-panel-header">
            <span>Details</span>
            <button aria-label="Close details panel" onClick={() => setIsContextOpen(false)} type="button">
              <X size={18} />
            </button>
          </div>

          <section className="context-section">
            <h2>Customer Profile</h2>
            <strong>{customerName}</strong>
            <p>{displayPhone}</p>
            {activeConversation?.code && <em>Conversation code: #{activeConversation.code}</em>}
          </section>

          <section className="context-section">
            <h2>
              <Sparkles size={18} />
              AI Suggested Reply
            </h2>
            <div className="intent-box">
              <span>{suggestedReply ? "Ready" : "No suggestion"}</span>
              <p>{suggestedReply || "No AI suggestion is available for this conversation yet."}</p>
              {suggestedReply && (
                <button
                  className="secondary-action"
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

          <section className="context-section">
            <h2>Quick Responses</h2>
            <div className="quick-responses">
              {quickResponses.map((response, index) => (
                <button key={response.id} onClick={() => setDraft(response.body)} type="button">
                  {index === 0 && "?"}
                  {index === 1 && <CheckCircle2 size={16} />}
                  {index === 2 && <Sparkles size={16} />}
                  <span>{response.label}</span>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </main>
      <NewCallModal
        onClose={() => setIsNewCallOpen(false)}
        onStartCall={handleStartNewCall}
        open={isNewCallOpen}
      />
    </div>
  );
}
