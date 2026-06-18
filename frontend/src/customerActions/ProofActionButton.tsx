import { FileCheck2 } from "lucide-react";

type ProofActionButtonProps = {
  disabled?: boolean;
  onClick: () => void;
};

export function ProofActionButton({ disabled = false, onClick }: ProofActionButtonProps) {
  return (
    <button
      aria-label="Send proof approval request"
      className="conversation-proof-action"
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      <FileCheck2 size={15} />
      Proof
    </button>
  );
}
