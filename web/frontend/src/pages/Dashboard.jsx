import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LabelList, ResponsiveContainer, Cell,
} from "recharts";
import { api } from "../api";

const COLORS = [
  "#4f46e5", "#059669", "#d97706", "#dc2626", "#7c3aed",
  "#0891b2", "#db2777", "#65a30d", "#ea580c", "#64748b",
];

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [deposits, setDeposits] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState([]);
  const [catInput, setCatInput] = useState("");
  const [catMsg, setCatMsg] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [queryText, setQueryText] = useState("");
  const [queryResult, setQueryResult] = useState(null);
  const [querying, setQuerying] = useState(false);

  useEffect(() => {
    Promise.all([api.summary(), api.listExpenses(), api.getCategories()])
      .then(([s, e, c]) => {
        setSummary(s);
        setExpenses(e.expenses || []);
        setDeposits(e.deposits || []);
        setCategories(c.categories || []);
      })
      .catch((err) => setError(err.message || "Failed to load data"))
      .finally(() => setLoading(false));
  }, []);

  async function saveCategories(next) {
    setCatMsg("");
    try {
      const res = await api.setCategories(next);
      setCategories(res.categories || next);
      setCatMsg("Saved.");
    } catch (err) {
      setCatMsg(err.message || "Failed to save categories");
    }
  }

  function addCategory() {
    const v = catInput.trim();
    if (!v || categories.includes(v)) {
      setCatInput("");
      return;
    }
    const next = [...categories, v];
    setCatInput("");
    saveCategories(next);
  }

  function removeCategory(name) {
    saveCategories(categories.filter((c) => c !== name));
  }

  async function changeExpenseCategory(expense, newCategory) {
    if (!newCategory || newCategory === expense.category) return;
    setSavingId(expense.id);
    setCatMsg("");
    try {
      await api.recategorize(expense.id, newCategory);
      const [s, e] = await Promise.all([api.summary(), api.listExpenses()]);
      setSummary(s);
      setExpenses(e.expenses || []);
      setDeposits(e.deposits || []);
      setCatMsg(`Category learned — future "${expense.merchant}" will use ${newCategory}.`);
    } catch (err) {
      setCatMsg(err.message || "Failed to update category");
    } finally {
      setSavingId(null);
      setEditingId(null);
    }
  }

  async function runQuery() {
    const q = queryText.trim();
    if (!q) {
      setQueryResult(null);
      return;
    }
    setQuerying(true);
    setError("");
    try {
      const res = await api.query(q);
      setQueryResult(res);
    } catch (err) {
      setError(err.message || "Query failed");
    } finally {
      setQuerying(false);
    }
  }

  function clearQuery() {
    setQueryText("");
    setQueryResult(null);
  }

  async function resetDb() {
    if (!window.confirm("Flush all your expense data? This cannot be undone.")) return;
    try {
      const res = await api.resetDb();
      const [s, e] = await Promise.all([api.summary(), api.listExpenses()]);
      setSummary(s);
      setExpenses(e.expenses || []);
      setDeposits(e.deposits || []);
      setCatMsg(`Reset complete — ${res.deleted} expense(s) deleted.`);
    } catch (err) {
      setError(err.message || "Failed to reset");
    }
  }

  if (loading) return <div className="text-center py-16 text-slate-400">Loading…</div>;
  if (error) return <p className="text-red-400">{error}</p>;

  const activeSummary = queryResult || summary;
  const pieData = activeSummary
    ? Object.entries(activeSummary.by_category).map(([name, value]) => ({ name, value }))
    : [];
  const displayExpenses = queryResult ? queryResult.expenses || [] : expenses;

  const depositTotal = deposits.reduce((sum, d) => sum + Number(d.amount || 0), 0);

  return (
    <div className="flex gap-6 items-start">

      {/* ── Main card ───────────────────────────────────────────────── */}
      <div className="flex-1 bg-slate-100 border border-slate-300 rounded-2xl overflow-hidden">

        {/* Card header: title + Reset DB */}
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-slate-300 bg-white">
          <h1 className="m-0 text-lg font-semibold text-slate-800">Expense Dashboard</h1>
          <button
            type="button"
            className="bg-red-600 hover:bg-red-700 text-white border-0 rounded-lg px-3.5 py-2 text-sm cursor-pointer transition-colors"
            onClick={resetDb}
          >
            Reset DB
          </button>
        </div>

        {/* Summary stat tiles — inside the card, below the header */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-slate-300">
          {[
            { label: "Total spent",    value: `$${summary ? summary.total.toFixed(2) : "0.00"}` },
            { label: "Total received", value: `$${depositTotal.toFixed(2)}` },
            { label: "Expenses",       value: summary ? summary.count : 0 },
            { label: "Categories",     value: pieData.length },
          ].map(({ label, value }) => (
            <div key={label} className="bg-white px-5 py-4 flex flex-col gap-1">
              <span className="text-xs text-slate-500 uppercase tracking-wide">{label}</span>
              <span className="text-2xl font-bold text-slate-800">{value}</span>
            </div>
          ))}
        </div>

        <div className="p-6 space-y-8">

        {/* Chart — bar chart, amount on top of each bar */}
        {pieData.length > 0 ? (
          <div>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart
                data={pieData}
                margin={{ top: 28, right: 16, left: 8, bottom: pieData.length > 5 ? 60 : 24 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 12, fill: "#64748b" }}
                  interval={0}
                  angle={pieData.length > 5 ? -40 : 0}
                  textAnchor={pieData.length > 5 ? "end" : "middle"}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis hide />
                <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} cursor={{ fill: "#f1f5f9" }} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]} maxBarSize={64}>
                  {pieData.map((entry, i) => (
                    <Cell key={entry.name} fill={COLORS[i % COLORS.length]} />
                  ))}
                  <LabelList
                    dataKey="value"
                    position="top"
                    formatter={(v) => `$${Number(v).toFixed(0)}`}
                    style={{ fontSize: 11, fill: "#475569", fontWeight: 600 }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-center text-slate-400 py-4 m-0">
            No expenses yet. Upload a receipt to get started.
          </p>
        )}

        {/* Divider */}
        <hr className="border-slate-300 m-0" />

        {/* Query bar */}
        <div>
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">Search</h2>
          <form
            className="flex gap-2 items-center"
            onSubmit={(e) => { e.preventDefault(); runQuery(); }}
          >
            <input
              type="text"
              value={queryText}
              placeholder='Ask in plain English, e.g. "credit card and transport from 1st to 15th of July"'
              onChange={(ev) => setQueryText(ev.target.value)}
              className="flex-1 px-3 py-2.5 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <button
              type="submit"
              disabled={querying}
              className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-default text-white border-0 rounded-lg px-4 py-2.5 text-sm cursor-pointer transition-colors"
            >
              {querying ? "Searching…" : "Search"}
            </button>
            {queryResult && (
              <button
                type="button"
                className="text-indigo-600 hover:underline bg-transparent border-0 cursor-pointer p-0 text-sm"
                onClick={clearQuery}
              >
                Clear
              </button>
            )}
          </form>
          {queryResult && (
            <p className="text-slate-500 text-xs mt-2 mb-0">
              Showing {queryResult.count} expense(s)
              {queryResult.filter?.categories?.length
                ? ` in ${queryResult.filter.categories.join(", ")}`
                : ""}
              {queryResult.filter?.date_from || queryResult.filter?.date_to
                ? ` from ${queryResult.filter.date_from || "…"} to ${queryResult.filter.date_to || "…"}`
                : ""}
              {" "}(total ${Number(queryResult.total || 0).toFixed(2)}).
            </p>
          )}
        </div>

        {/* Divider */}
        <hr className="border-slate-300 m-0" />

        {/* Category editor */}
        <div>
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">Categories</h2>
          <div className="flex flex-wrap gap-2 mb-3">
            {categories.map((c) => (
              <span
                key={c}
                className="inline-flex items-center gap-1.5 bg-indigo-50 text-indigo-700 border border-indigo-200 px-3 py-1 rounded-full text-xs font-medium"
              >
                {c}
                <button
                  type="button"
                  className="border-0 bg-transparent text-indigo-400 hover:text-red-500 cursor-pointer text-base leading-none p-0"
                  onClick={() => removeCategory(c)}
                  aria-label={`Remove ${c}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <form
            className="flex gap-2 max-w-sm"
            onSubmit={(e) => { e.preventDefault(); addCategory(); }}
          >
            <input
              type="text"
              value={catInput}
              placeholder="Add a category…"
              onChange={(ev) => setCatInput(ev.target.value)}
              className="flex-1 px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <button
              type="submit"
              className="bg-indigo-600 hover:bg-indigo-700 text-white border-0 rounded-lg px-3.5 py-2 text-sm cursor-pointer transition-colors"
            >
              Add
            </button>
          </form>
          {catMsg && <p className="mt-2 text-xs text-emerald-600">{catMsg}</p>}
        </div>

        {/* Divider */}
        <hr className="border-slate-300 m-0" />

        {/* Expenses table */}
        <div>
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">Recent expenses</h2>
          <div className="rounded-xl overflow-hidden border border-slate-300">
            <table className="w-full border-collapse bg-white text-sm">
              <thead>
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs text-slate-500 font-semibold border-b border-slate-200 bg-slate-50">Date</th>
                  <th className="px-4 py-2.5 text-left text-xs text-slate-500 font-semibold border-b border-slate-200 bg-slate-50">Merchant</th>
                  <th className="px-4 py-2.5 text-left text-xs text-slate-500 font-semibold border-b border-slate-200 bg-slate-50">Category</th>
                  <th className="px-4 py-2.5 text-right text-xs text-slate-500 font-semibold border-b border-slate-200 bg-slate-50">Amount</th>
                </tr>
              </thead>
              <tbody>
                {displayExpenses.map((e) => (
                  <tr key={e.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                    <td className="px-4 py-2.5 text-slate-700">{e.date}</td>
                    <td className="px-4 py-2.5 text-slate-700">{e.merchant}</td>
                    <td className="px-4 py-2.5">
                      {editingId === e.id ? (
                        <select
                          autoFocus
                          value={categories.includes(e.category) ? e.category : ""}
                          disabled={savingId === e.id}
                          onChange={(ev) => changeExpenseCategory(e, ev.target.value)}
                          onBlur={() => setEditingId(null)}
                          className="px-2 py-1 bg-white border border-slate-300 rounded text-xs text-slate-800 cursor-pointer disabled:opacity-60"
                        >
                          {!categories.includes(e.category) && (
                            <option value="">{e.category || "—"}</option>
                          )}
                          {categories.map((c) => (
                            <option key={c} value={c}>{c}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-slate-700">
                          {e.category}
                          <button
                            type="button"
                            title="Change category"
                            aria-label="Change category"
                            onClick={() => setEditingId(e.id)}
                            className="border-0 bg-transparent text-slate-400 hover:text-indigo-600 cursor-pointer text-xs p-0.5 rounded opacity-70 hover:opacity-100"
                          >
                            ✎
                          </button>
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-700">
                      {Number(e.amount).toFixed(2)} {e.currency}
                    </td>
                  </tr>
                ))}
                {displayExpenses.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                      {queryResult ? "No expenses match your query." : "No expenses yet."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Divider */}
        <hr className="border-slate-300 m-0" />

        {/* Deposits table */}
        <div>
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">Deposits</h2>
          <div className="rounded-xl overflow-hidden border border-slate-300">
            <table className="w-full border-collapse bg-white text-sm">
              <thead>
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs text-slate-500 font-semibold border-b border-slate-200 bg-slate-50">Date</th>
                  <th className="px-4 py-2.5 text-left text-xs text-slate-500 font-semibold border-b border-slate-200 bg-slate-50">Merchant</th>
                  <th className="px-4 py-2.5 text-right text-xs text-slate-500 font-semibold border-b border-slate-200 bg-slate-50">Amount</th>
                </tr>
              </thead>
              <tbody>
                {deposits.map((d) => (
                  <tr key={d.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                    <td className="px-4 py-2.5 text-slate-700">{d.date}</td>
                    <td className="px-4 py-2.5 text-slate-700">{d.merchant}</td>
                    <td className="px-4 py-2.5 text-right text-slate-700">
                      {Number(d.amount).toFixed(2)} {d.currency}
                    </td>
                  </tr>
                ))}
                {deposits.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-4 py-6 text-center text-slate-400">
                      No deposits yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        </div>{/* end inner padding */}
      </div>{/* end main card */}

      {/* Privacy note — floats to the right of the card */}
      <div className="hidden lg:block flex-shrink-0 bg-sky-900 border border-sky-700 rounded-xl px-4 py-3 text-xs text-sky-300 text-center leading-relaxed mt-1">
        Deposit values<br />are obfuscated<br />for privacy reasons
      </div>

    </div>
  );
}
