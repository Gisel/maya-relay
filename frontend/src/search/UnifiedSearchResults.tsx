import { ContactSearchItem } from "../api";

type UnifiedSearchResultsProps = {
  query: string;
  contacts: ContactSearchItem[];
  isSearching: boolean;
  onSelectContact: (contact: ContactSearchItem) => void;
};

export function UnifiedSearchResults({ query, contacts, isSearching, onSelectContact }: UnifiedSearchResultsProps) {
  if (!query.trim()) return null;
  if (!isSearching && contacts.length === 0) return null;

  return (
    <div className="contact-search-results" aria-live="polite">
      <div className="search-result-heading">
        <span>Contacts</span>
        {isSearching && <em>Searching...</em>}
      </div>
      {contacts.map((contact) => (
        <button key={contact.id} className="contact-result-row" onClick={() => onSelectContact(contact)} type="button">
          <span>
            <strong>{contact.name || contact.phone}</strong>
            <em>{contact.phone.replace(/^whatsapp:/i, "")}</em>
          </span>
          {contact.openConversationId || contact.lastConversationId ? <small>Open conversation</small> : <small>No conversation yet</small>}
        </button>
      ))}
    </div>
  );
}
