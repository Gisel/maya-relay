import {
  AlertTriangle,
  CheckCircle2,
  Image,
  LogOut,
  Paperclip,
  Search,
  Send,
  Sparkles,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import logoMaya from "./assets/logo-maya.jpg";

type Channel = "sms" | "whatsapp";
type ConversationStatus = "open" | "closed";
type DeliveryStatus = "delivered" | "failed" | "pending" | "queued";
type MessageDirection = "customer_to_employee" | "employee_to_customer" | "system";

type Attachment = {
  id: string;
  fileName: string;
  contentType: string;
  url: string;
};

type Message = {
  id: string;
  direction: MessageDirection;
  body: string;
  createdAt: string;
  deliveryStatus: DeliveryStatus;
  attachments?: Attachment[];
};

type Conversation = {
  id: string;
  code: string;
  customerName: string;
  customerPhone: string;
  channel: Channel;
  status: ConversationStatus;
  lastMessagePreview: string;
  updatedLabel: string;
  deliveryStatus: DeliveryStatus;
  messages: Message[];
  intent: {
    label: string;
    missing: string[];
  };
};

const initialConversations: Conversation[] = [
  {
    id: "conv-1",
    code: "#1B976390",
    customerName: "Gomez, Gisel",
    customerPhone: "+1 801 200 9467",
    channel: "whatsapp",
    status: "open",
    lastMessagePreview: "Need a quote for some presentation cards",
    updatedLabel: "5m ago",
    deliveryStatus: "delivered",
    intent: {
      label: "Quote Request",
      missing: ["Quantity", "Size", "Paper/Finish", "Artwork/Design Ready"],
    },
    messages: [
      {
        id: "msg-1",
        direction: "customer_to_employee",
        body: "Hello Francisco I need a quote for some presentation cards",
        createdAt: "Jun 5, 04:27 PM UTC",
        deliveryStatus: "delivered",
      },
      {
        id: "msg-2",
        direction: "employee_to_customer",
        body: 'Thanks-can you confirm if "50" is quantity or a size, exact dimensions/material/finish?',
        createdAt: "Jun 5, 04:28 PM UTC",
        deliveryStatus: "delivered",
      },
    ],
  },
  {
    id: "conv-2",
    code: "#8447A2CA",
    customerName: "+52 1844 326 1219",
    customerPhone: "+52 1844 326 1219",
    channel: "sms",
    status: "open",
    lastMessagePreview: 'Thanks-can you confirm if "50" is quantity or size...',
    updatedLabel: "1h ago",
    deliveryStatus: "failed",
    intent: {
      label: "Needs Follow-up",
      missing: ["Delivery address", "Deadline"],
    },
    messages: [
      {
        id: "msg-3",
        direction: "customer_to_employee",
        body: "I need 50 large blue signs. Can you send me the estimate?",
        createdAt: "Jun 5, 03:41 PM UTC",
        deliveryStatus: "delivered",
        attachments: [
          {
            id: "att-1",
            fileName: "reference-photo.jpg",
            contentType: "image/jpeg",
            url: "https://images.unsplash.com/photo-1618005198919-d3d4b5a92ead?w=900&auto=format&fit=crop",
          },
        ],
      },
      {
        id: "msg-4",
        direction: "employee_to_customer",
        body: "Could you send exact dimensions, material preference, and pickup or install location?",
        createdAt: "Jun 5, 03:43 PM UTC",
        deliveryStatus: "failed",
      },
    ],
  },
];

const quickResponses = [
  "Request missing job dimensions",
  "Send standard print proof review",
  "Provide shop hours & pickup info",
];

function channelLabel(channel: Channel) {
  return channel === "whatsapp" ? "WhatsApp" : "SMS";
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
      {status === "failed" && <AlertTriangle size={14} />}
      {status}
    </span>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isOutbound = message.direction === "employee_to_customer";

  return (
    <article className={`message-bubble ${isOutbound ? "outbound" : "inbound"}`}>
      {message.attachments?.map((attachment) => (
        <a className="attachment-preview" href={attachment.url} key={attachment.id}>
          {attachment.contentType.startsWith("image/") ? (
            <img alt={attachment.fileName} src={attachment.url} />
          ) : (
            <span>
              <Image size={18} />
              {attachment.fileName}
            </span>
          )}
        </a>
      ))}
      <p>{message.body}</p>
      <footer>
        <span>{message.createdAt}</span>
        <span>{message.deliveryStatus}</span>
      </footer>
    </article>
  );
}

function Composer({
  onSend,
}: {
  onSend: (body: string, files: File[]) => Promise<void>;
}) {
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isSending, setIsSending] = useState(false);
  const canSend = body.trim().length > 0 || files.length > 0;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSend || isSending) return;
    setIsSending(true);
    await onSend(body.trim(), files);
    setBody("");
    setFiles([]);
    setIsSending(false);
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <textarea
        aria-label="Reply message"
        onChange={(event) => setBody(event.target.value)}
        placeholder="Type your response directly to the customer here..."
        value={body}
      />
      <div className="composer-actions">
        <label className="attach-control">
          <Paperclip size={20} />
          <span>Attach files or imagery</span>
          <input
            multiple
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            type="file"
          />
        </label>
        <button className="send-button" disabled={!canSend || isSending} type="submit">
          <Send size={18} />
          {isSending ? "Sending..." : "Send Message"}
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
  const [conversations, setConversations] = useState(initialConversations);
  const [selectedId, setSelectedId] = useState(initialConversations[0].id);
  const [search, setSearch] = useState("");
  const selected = conversations.find((conversation) => conversation.id === selectedId) ?? conversations[0];

  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return conversations;
    return conversations.filter((conversation) =>
      [
        conversation.customerName,
        conversation.customerPhone,
        conversation.code,
        conversation.lastMessagePreview,
        conversation.channel,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [conversations, search]);

  const metrics = useMemo(
    () => ({
      open: conversations.filter((conversation) => conversation.status === "open").length,
      failed: conversations.filter((conversation) => conversation.deliveryStatus === "failed").length,
      recent: conversations.length,
    }),
    [conversations],
  );

  async function handleSend(body: string, files: File[]) {
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    const now = new Date();
    const createdAt = now.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    });

    setConversations((current) =>
      current.map((conversation) =>
        conversation.id === selected.id
          ? {
              ...conversation,
              lastMessagePreview: body || `${files.length} attachment${files.length === 1 ? "" : "s"}`,
              deliveryStatus: "pending",
              updatedLabel: "now",
              messages: [
                ...conversation.messages,
                {
                  id: `local-${Date.now()}`,
                  direction: "employee_to_customer",
                  body,
                  createdAt,
                  deliveryStatus: "pending",
                  attachments: files.map((file, index) => ({
                    id: `local-file-${index}`,
                    fileName: file.name,
                    contentType: file.type || "application/octet-stream",
                    url: URL.createObjectURL(file),
                  })),
                },
              ],
            }
          : conversation,
      ),
    );
  }

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
        <button className="logout-button" type="button">
          <LogOut size={18} />
          Logout
        </button>
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
            {filteredConversations.map((conversation) => (
              <button
                className={`conversation-row ${conversation.id === selected.id ? "selected" : ""}`}
                key={conversation.id}
                onClick={() => setSelectedId(conversation.id)}
                type="button"
              >
                <span>
                  <strong>{conversation.customerName}</strong>
                  <em>{conversation.updatedLabel}</em>
                </span>
                <p>{conversation.lastMessagePreview}</p>
                <footer>
                  <span className={`channel-pill ${conversation.channel}`}>
                    {channelLabel(conversation.channel)}
                  </span>
                  {conversation.deliveryStatus === "failed" && <DeliveryPill status="failed" />}
                </footer>
              </button>
            ))}
          </div>
        </aside>

        <section className="conversation-panel">
          <header className="conversation-header">
            <div>
              <h1>{selected.customerName}</h1>
              <p>
                via {channelLabel(selected.channel)} {selected.customerPhone}
              </p>
            </div>
            <StatusPill status={selected.status} />
          </header>

          <div className="message-thread">
            {selected.messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>

          <Composer onSend={handleSend} />
        </section>

        <aside className="context-panel">
          <section className="context-section">
            <h2>Customer Profile</h2>
            <strong>{selected.customerName}</strong>
            <p>{selected.customerPhone}</p>
            <em>Account Status: Active Client</em>
          </section>

          <section className="context-section">
            <h2>
              <Sparkles size={18} />
              AI Intent Checklist
            </h2>
            <div className="intent-box">
              <span>{selected.intent.label}</span>
              <p>Missing info parsed from chat:</p>
              {selected.intent.missing.map((item) => (
                <label key={item}>
                  <input type="checkbox" />
                  {item}
                </label>
              ))}
            </div>
          </section>

          <section className="context-section">
            <h2>Quick Responses</h2>
            <div className="quick-responses">
              {quickResponses.map((response, index) => (
                <button key={response} type="button">
                  {index === 0 && "?"}
                  {index === 1 && <CheckCircle2 size={16} />}
                  {index === 2 && <Sparkles size={16} />}
                  <span>{response}</span>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </main>
    </div>
  );
}
