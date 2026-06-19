import { FolderUp } from "lucide-react";

type AssetActionButtonProps = {
  disabled?: boolean;
  onClick: () => void;
};

export function AssetActionButton({ disabled = false, onClick }: AssetActionButtonProps) {
  return (
    <button
      aria-label="Request customer assets"
      className="conversation-proof-action conversation-asset-action"
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      <FolderUp size={15} />
      Assets
    </button>
  );
}
