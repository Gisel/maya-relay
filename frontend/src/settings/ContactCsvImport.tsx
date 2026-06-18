import { FormEvent, useState } from "react";
import { Upload } from "lucide-react";
import { ContactImportResponse } from "../api";

type ContactCsvImportProps = {
  onImport: (file: File, overwrite: boolean) => Promise<ContactImportResponse>;
};

export function ContactCsvImport({ onImport }: ContactCsvImportProps) {
  const [file, setFile] = useState<File | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [result, setResult] = useState<ContactImportResponse | null>(null);
  const [error, setError] = useState("");

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
        <label>
          Contact CSV
          <input
            accept=".csv,text/csv"
            disabled={isImporting}
            onChange={(event) => setFile(event.target.files?.[0] || null)}
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
