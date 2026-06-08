import { MessageSquareText, Phone } from "lucide-react";

export type WorkspaceMode = "text" | "calls";

export function WorkspaceTabs({
  mode,
  onModeChange,
}: {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
}) {
  return (
    <div className="workspace-tabs" role="tablist" aria-label="Maya Relay workspace">
      <button
        aria-selected={mode === "text"}
        className={mode === "text" ? "is-active" : ""}
        onClick={() => onModeChange("text")}
        role="tab"
        type="button"
      >
        <MessageSquareText size={17} />
        Text
      </button>
      <button
        aria-selected={mode === "calls"}
        className={mode === "calls" ? "is-active" : ""}
        onClick={() => onModeChange("calls")}
        role="tab"
        type="button"
      >
        <Phone size={17} />
        Calls
      </button>
    </div>
  );
}
