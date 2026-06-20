import { Search, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError, ContactSearchItem, getContacts } from "../api";

export type CustomerContactSelection = {
  contact: ContactSearchItem | null;
  displayName: string;
  phoneNumber: string;
};

type CustomerContactPickerProps = {
  disabled?: boolean;
  onAuthExpired?: () => void;
  onChange: (selection: CustomerContactSelection) => void;
  selection: CustomerContactSelection;
};

function cleanPhone(phone: string | null | undefined) {
  return (phone || "").replace(/^whatsapp:/i, "");
}

function contactName(contact: ContactSearchItem) {
  return contact.name || cleanPhone(contact.phone);
}

export function CustomerContactPicker({
  disabled = false,
  onAuthExpired,
  onChange,
  selection,
}: CustomerContactPickerProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ContactSearchItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState("");
  const searchId = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    searchId.current += 1;
    const currentSearchId = searchId.current;

    if (trimmed.length < 2) {
      setResults([]);
      setIsSearching(false);
      setError("");
      return;
    }

    setIsSearching(true);
    const timer = window.setTimeout(() => {
      getContacts(trimmed, 0, 8)
        .then((payload) => {
          if (searchId.current !== currentSearchId) return;
          setResults(payload.items);
          setError("");
        })
        .catch((searchError) => {
          if (searchId.current !== currentSearchId) return;
          if (searchError instanceof ApiError && searchError.status === 401) {
            onAuthExpired?.();
            return;
          }
          setResults([]);
          setError(searchError instanceof Error ? searchError.message : "Could not search contacts.");
        })
        .finally(() => {
          if (searchId.current === currentSearchId) setIsSearching(false);
        });
    }, 250);

    return () => window.clearTimeout(timer);
  }, [onAuthExpired, query]);

  function selectContact(contact: ContactSearchItem) {
    onChange({
      contact,
      displayName: contact.displayName || contact.name || "",
      phoneNumber: cleanPhone(contact.phone),
    });
    setQuery(contactName(contact));
    setResults([]);
    setError("");
  }

  return (
    <div className="customer-contact-picker">
      <label>
        <span>Find customer</span>
        <div className="contact-picker-search">
          <Search size={17} />
          <input
            autoComplete="off"
            disabled={disabled}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name or phone"
            type="search"
            value={query}
          />
        </div>
      </label>

      {(isSearching || results.length > 0 || error) && (
        <div className="contact-picker-results" aria-live="polite">
          {isSearching && <p className="panel-note compact">Searching customers...</p>}
          {error && <p className="form-error">{error}</p>}
          {!isSearching && !error && results.map((contact) => (
            <button
              className="contact-picker-result"
              disabled={disabled}
              key={contact.id}
              onClick={() => selectContact(contact)}
              type="button"
            >
              <UserRound size={16} />
              <span>
                <strong>{contactName(contact)}</strong>
                <em>{cleanPhone(contact.phone)}</em>
              </span>
              <small>{contact.openConversationId ? "Open conversation" : "Saved contact"}</small>
            </button>
          ))}
          {!isSearching && !error && query.trim().length >= 2 && results.length === 0 && (
            <p className="panel-note compact">No saved customer found. Enter the phone number below.</p>
          )}
        </div>
      )}

      <div className="contact-picker-divider">
        <span>Or enter a new number</span>
      </div>

      <div className="contact-picker-manual-fields">
        <label>
          <span>Customer phone</span>
          <input
            disabled={disabled}
            inputMode="tel"
            onChange={(event) =>
              onChange({
                ...selection,
                contact: null,
                phoneNumber: event.target.value,
              })
            }
            placeholder="+1 555 000 0000"
            required
            type="tel"
            value={selection.phoneNumber}
          />
        </label>
        <label>
          <span>Customer name</span>
          <input
            disabled={disabled}
            onChange={(event) =>
              onChange({
                ...selection,
                contact: null,
                displayName: event.target.value,
              })
            }
            placeholder="Optional"
            type="text"
            value={selection.displayName}
          />
        </label>
      </div>
    </div>
  );
}
