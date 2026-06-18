import { ReactNode } from "react";
import { X } from "lucide-react";

type SettingsModalProps = {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
};

export function SettingsModal({ open, onClose, children }: SettingsModalProps) {
  if (!open) return null;

  return (
    <div className="drawer-backdrop" role="presentation">
      <section aria-labelledby="settings-title" aria-modal="true" className="drawer-surface settings-surface" role="dialog">
        <div className="drawer-header">
          <div>
            <h2 id="settings-title">Settings</h2>
            <p>Manage operator tools and contact imports.</p>
          </div>
          <button aria-label="Close settings" className="drawer-close" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
