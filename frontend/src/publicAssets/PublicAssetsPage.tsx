import { ChangeEvent, DragEvent, FormEvent, useEffect, useState } from "react";
import { CheckCircle2, FileText, FolderUp, Loader2, Upload, X, XCircle } from "lucide-react";

import { ApiError, PublicAssetRequest, getPublicAssetRequest, submitPublicAssets } from "../api";
import logoMaya from "../assets/logo-maya.jpg";

const ASSET_MAX_FILES = 8;
const ASSET_MAX_FILE_SIZE_BYTES = 32 * 1024 * 1024;
const ASSET_MAX_TOTAL_SIZE_BYTES = 100 * 1024 * 1024;
const ASSET_ALLOWED_EXTENSIONS = [
  ".ai",
  ".doc",
  ".docx",
  ".eps",
  ".gif",
  ".jpeg",
  ".jpg",
  ".pdf",
  ".png",
  ".psd",
  ".svg",
  ".tif",
  ".tiff",
  ".webp",
  ".zip",
];

type PublicAssetsPageProps = {
  token: string;
};

export function PublicAssetsPage({ token }: PublicAssetsPageProps) {
  const [assetRequest, setAssetRequest] = useState<PublicAssetRequest | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let ignore = false;
    setLoadError("");
    getPublicAssetRequest(token)
      .then((response) => {
        if (!ignore) setAssetRequest(response.assetRequest);
      })
      .catch((error) => {
        if (ignore) return;
        if (error instanceof ApiError && error.status === 404) {
          setLoadError("This asset upload link is unavailable.");
        } else {
          setLoadError(error instanceof Error ? error.message : "Could not load this asset request.");
        }
      });
    return () => {
      ignore = true;
    };
  }, [token]);

  const isPending = assetRequest?.status === "pending";
  const submittedEvent = [...(assetRequest?.events ?? [])].reverse().find((event) => event.type === "assets_submitted");

  function addFiles(files: FileList | File[]) {
    setActionError("");
    const nextFiles = [...selectedFiles, ...Array.from(files)];
    const validationError = assetValidationError(nextFiles);
    if (validationError) {
      setActionError(validationError);
      return;
    }
    setSelectedFiles(nextFiles);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (!isPending || isSubmitting) return;
    addFiles(event.dataTransfer.files);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    if (!event.target.files) return;
    addFiles(event.target.files);
    event.target.value = "";
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isPending || isSubmitting) return;
    const validationError = assetValidationError(selectedFiles);
    if (validationError) {
      setActionError(validationError);
      return;
    }
    setIsSubmitting(true);
    setActionError("");
    try {
      const response = await submitPublicAssets(token, selectedFiles, note.trim());
      setAssetRequest(response.assetRequest);
      setSelectedFiles([]);
      setNote("");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not upload your assets.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <main className="public-proof-shell">
        <section className="public-proof-card public-proof-message-card">
          <BrandHeader />
          <XCircle size={42} />
          <h1>Asset link unavailable</h1>
          <p>{loadError}</p>
        </section>
      </main>
    );
  }

  if (!assetRequest) {
    return (
      <main className="public-proof-shell">
        <section className="public-proof-card public-proof-message-card">
          <BrandHeader />
          <Loader2 className="public-proof-spinner" size={34} />
          <p>Loading asset request...</p>
        </section>
      </main>
    );
  }

  return (
    <main className="public-proof-shell">
      <section className="public-proof-card">
        <BrandHeader />

        <div className="public-proof-heading">
          <div>
            <p className="section-kicker">Asset upload</p>
            <h1>{assetRequest.title || "Upload assets"}</h1>
          </div>
          <span className={`public-proof-status status-${assetRequest.status}`}>
            {assetRequest.status === "submitted" ? "Submitted" : "Pending upload"}
          </span>
        </div>

        <div className="public-proof-status-note">
          {assetRequest.status === "submitted" ? <CheckCircle2 size={18} /> : <FileText size={18} />}
          <p>
            {assetRequest.status === "submitted"
              ? submittedEvent?.comment
                ? `Assets received. Note: ${submittedEvent.comment}`
                : "Assets received. Thank you."
              : "Upload the files Maya needs, then submit them with an optional note."}
          </p>
        </div>

        {isPending ? (
          <form className="public-proof-actions" onSubmit={handleSubmit}>
            {actionError && <p className="form-error">{actionError}</p>}

            <label
              className={`public-asset-dropzone ${isDragging ? "is-dragging-file" : ""}`}
              onDragLeave={(event) => {
                event.preventDefault();
                setIsDragging(false);
              }}
              onDragOver={(event) => {
                event.preventDefault();
                if (!isSubmitting) setIsDragging(true);
              }}
              onDrop={handleDrop}
            >
              <span className="public-asset-dropzone-main">
                <Upload size={22} />
                <strong>Choose files</strong>
                <span>or drag and drop them here</span>
              </span>
              <span className="public-asset-dropzone-hint">Up to 8 files, 32 MB each, 100 MB total.</span>
              <input
                accept={ASSET_ALLOWED_EXTENSIONS.join(",")}
                disabled={isSubmitting}
                multiple
                onChange={handleFileChange}
                type="file"
              />
            </label>

            {selectedFiles.length > 0 ? (
              <ul className="public-asset-file-list">
                {selectedFiles.map((file, index) => (
                  <li key={`${file.name}-${file.size}-${index}`}>
                    <span>
                      <FileText size={16} />
                      {file.name}
                    </span>
                    <button
                      aria-label={`Remove ${file.name}`}
                      disabled={isSubmitting}
                      onClick={() => setSelectedFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))}
                      type="button"
                    >
                      <X size={15} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            <label className="public-asset-note-field">
              <span>Note for Maya</span>
              <textarea
                disabled={isSubmitting}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Optional note about these files."
                rows={4}
                value={note}
              />
            </label>

            <button className="public-proof-approve" disabled={selectedFiles.length === 0 || isSubmitting} type="submit">
              <FolderUp size={18} />
              {isSubmitting ? "Uploading..." : "Submit assets"}
            </button>
          </form>
        ) : null}
      </section>
    </main>
  );
}

function BrandHeader() {
  return (
    <div className="public-proof-brand">
      <img alt="Maya Graphics and Signs" src={logoMaya} />
      <strong>MAYA <span>RELAY</span></strong>
    </div>
  );
}

function assetValidationError(files: File[]) {
  if (!files.length) {
    return "Choose or drop at least one file.";
  }
  if (files.length > ASSET_MAX_FILES) {
    return "Upload 8 files or fewer.";
  }
  const totalSize = files.reduce((total, file) => total + file.size, 0);
  if (totalSize > ASSET_MAX_TOTAL_SIZE_BYTES) {
    return "Asset upload total must be 100 MB or smaller.";
  }
  for (const file of files) {
    if (file.size > ASSET_MAX_FILE_SIZE_BYTES) {
      return "Each asset file must be 32 MB or smaller.";
    }
    const filename = file.name.toLowerCase();
    if (!ASSET_ALLOWED_EXTENSIONS.some((extension) => filename.endsWith(extension))) {
      return "Asset files must be PDF, image, design, document, or ZIP files.";
    }
  }
  return "";
}
