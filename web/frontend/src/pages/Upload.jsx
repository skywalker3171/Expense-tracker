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
    <div>
      <h1 className="mt-0 mb-6 text-xl font-semibold text-white">Upload a receipt</h1>
      <form onSubmit={(e) => e.preventDefault()}>
        <div
          className={
            "border-2 border-dashed rounded-xl px-6 py-12 text-center cursor-pointer transition-colors " +
            (dragOver
              ? "border-sky-400 bg-sky-800/60"
              : "border-sky-600 bg-sky-900/50 hover:border-sky-400")
          }
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
          onClick={() => inputRef.current?.click()}
        >
          <p className="m-0 text-slate-200">
            {busy ? "Processing…" : "Drag & drop a receipt here, or click to browse"}
          </p>
          <p className="mt-2 mb-0 text-slate-500 text-sm">CSV, PNG, JPG, or PDF</p>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.png,.jpg,.jpeg,.gif,.webp,.tiff,.tif,.pdf,image/*,application/pdf,text/csv"
            className="hidden"
            onChange={(e) => handleFile(e.target.files[0])}
          />
        </div>
      </form>

      {error && <p className="mt-4 text-red-400 text-sm">{error}</p>}

      {result && (
        <div className="mt-6">
          <h2 className="text-base font-semibold text-white mb-3">
            Extracted {result.count} expense{result.count === 1 ? "" : "s"}
          </h2>
          {result.count > 0 && (
            <div className="rounded-xl overflow-hidden border border-slate-700">
              <table className="w-full border-collapse bg-sky-900 text-sm">
                <thead>
                  <tr>
                    <th className="px-4 py-2.5 text-left text-xs text-sky-300 font-medium border-b border-sky-700 bg-sky-950">Date</th>
                    <th className="px-4 py-2.5 text-left text-xs text-sky-300 font-medium border-b border-sky-700 bg-sky-950">Merchant</th>
                    <th className="px-4 py-2.5 text-left text-xs text-sky-300 font-medium border-b border-sky-700 bg-sky-950">Category</th>
                    <th className="px-4 py-2.5 text-right text-xs text-sky-300 font-medium border-b border-sky-700 bg-sky-950">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {result.expenses.map((e) => (
                    <tr key={e.id} className="border-b border-slate-700 last:border-0 hover:bg-slate-700/40">
                      <td className="px-4 py-2.5 text-slate-200">{e.date}</td>
                      <td className="px-4 py-2.5 text-slate-200">{e.merchant}</td>
                      <td className="px-4 py-2.5 text-slate-200">{e.category}</td>
                      <td className="px-4 py-2.5 text-right text-slate-200">
                        {Number(e.amount).toFixed(2)} {e.currency}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
