import { useRef, useState } from "react";
import { api } from "../api";

export default function Upload() {
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const inputRef = useRef(null);

  async function handleFile(file) {
    if (!file) return;
    setError("");
    setResult(null);
    setBusy(true);
    try {
      const res = await api.upload(file);
      setResult(res);
    } catch (err) {
      setError(err.message || "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <h1>Upload a receipt</h1>
      <div
        className={"dropzone" + (dragOver ? " over" : "")}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFile(e.dataTransfer.files[0]);
        }}
        onClick={() => inputRef.current?.click()}
      >
        <p>
          {busy
            ? "Processing…"
            : "Drag & drop a receipt here, or click to browse"}
        </p>
        <p className="hint">CSV, PNG, JPG, or PDF</p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.png,.jpg,.jpeg,.gif,.webp,.tiff,.tif,.pdf,image/*,application/pdf,text/csv"
          style={{ display: "none" }}
          onChange={(e) => handleFile(e.target.files[0])}
        />
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="upload-result">
          <h2>Extracted {result.count} expense{result.count === 1 ? "" : "s"}</h2>
          {result.count > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Merchant</th>
                  <th>Category</th>
                  <th className="num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {result.expenses.map((e) => (
                  <tr key={e.id}>
                    <td>{e.date}</td>
                    <td>{e.merchant}</td>
                    <td>{e.category}</td>
                    <td className="num">
                      {Number(e.amount).toFixed(2)} {e.currency}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
