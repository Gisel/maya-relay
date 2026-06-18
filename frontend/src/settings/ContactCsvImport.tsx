import { DragEvent, FormEvent, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { ContactImportResponse } from "../api";

type ContactCsvImportProps = {
  onImport: (file: File, overwrite: boolean) => Promise<ContactImportResponse>;
};

export function ContactCsvImport({ onImport }: ContactCsvImportProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [result, setResult] = useState<ContactImportResponse | null>(null);
  const [error, setError] = useState("");

  function selectFile(nextFile: File | undefined) {
    if (!nextFile) return;
    setFile(nextFile);
    setResult(null);
    setError("");
  }

  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (!isImporting) setIsDraggingFile(true);
  }

  function handleDragLeave(event: DragEvent<HTMLLabelElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setIsDraggingFile(false);
    }
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDraggingFile(false);
    if (isImporting) return;
    selectFile(event.dataTransfer.files[0]);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || isImporting) return;
    setIsImporting(true);
    setError("");
    setResult(null);
    try {
      const response = await onImport(file, overwrite);
      setResult(response);
      setFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not import contacts.");
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <section className="settings-section">
      <h3>CSV Import</h3>
      <p>Upload a contact CSV with columns named phone_number and display_name.</p>
      <form className="drawer-form" onSubmit={handleSubmit}>
        <label
          className={`file-picker-label ${isDraggingFile ? "is-dragging-file" : ""}`}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          <span>Contact CSV</span>
          <span className="file-picker-control">
            <span className="file-picker-button">
              <Upload size={15} />
              Choose CSV
            </span>
            <span className={`file-picker-name ${file ? "has-file" : ""}`}>
              {file?.name || "Drop a CSV here or choose a file"}
            </span>
          </span>
          <input
            accept=".csv,text/csv"
            className="file-picker-input"
            disabled={isImporting}
            onChange={(event) => selectFile(event.target.files?.[0])}
            ref={fileInputRef}
            type="file"
          />
        </label>
        <label className="checkbox-row">
          <input checked={overwrite} disabled={isImporting} onChange={(event) => setOverwrite(event.target.checked)} type="checkbox" />
          <span>Overwrite existing manual names when the CSV has a real name</span>
        </label>
        {error && <p className="form-error">{error}</p>}
        {result && (
          <div className="import-summary" role="status">
            <div className="import-counts">
              <span>Created {result.created}</span>
              <span>Updated {result.updated}</span>
              <span>Skipped {result.skipped}</span>
            </div>
            {result.invalidRows.length > 0 && (
              <div className="invalid-row-list">
                <strong>{result.invalidRows.length} row issue{result.invalidRows.length === 1 ? "" : "s"}</strong>
                {result.invalidRows.slice(0, 8).map((row) => (
                  <p key={`${row.row}-${row.code}`}>
                    Row {row.row}: {row.message}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
        <button className="send-button settings-submit-button" disabled={!file || isImporting} type="submit">
          <Upload size={17} />
          {isImporting ? "Importing..." : "Import contacts"}
        </button>
      </form>
    </section>
  );
}
