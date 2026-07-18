import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
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

  if (loading) return <div className="center">Loading…</div>;
  if (error) return <p className="error">{error}</p>;

  const pieData = summary
    ? Object.entries(summary.by_category).map(([name, value]) => ({ name, value }))
    : [];

  const depositTotal = deposits.reduce((sum, d) => sum + Number(d.amount || 0), 0);

  return (
    <div className="page">
      <div className="info-note">
        Deposit values are obfuscated<br />for privacy reasons
      </div>
      <div className="page-head">
        <h1>Dashboard</h1>
        <button type="button" className="btn-danger" onClick={resetDb}>
          Reset DB
        </button>
      </div>

      <div className="cards">
        <div className="card">
          <span className="card-label">Total spent</span>
          <span className="card-value">
            ${summary ? summary.total.toFixed(2) : "0.00"}
          </span>
        </div>
        <div className="card">
          <span className="card-label">Total received</span>
          <span className="card-value">${depositTotal.toFixed(2)}</span>
        </div>
        <div className="card">
          <span className="card-label">Expenses</span>
          <span className="card-value">{summary ? summary.count : 0}</span>
        </div>
        <div className="card">
          <span className="card-label">Categories</span>
          <span className="card-value">{pieData.length}</span>
        </div>
      </div>

      {pieData.length > 0 ? (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height={320}>
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={110}
                label={(d) => `${d.name}: $${d.value.toFixed(2)}`}
              >
                {pieData.map((entry, i) => (
                  <Cell key={entry.name} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="empty">
          No expenses yet. Upload a receipt to get started.
        </p>
      )}

      <div className="cat-editor">
        <h2>Categories</h2>
        <div className="cat-tags">
          {categories.map((c) => (
            <span key={c} className="cat-tag">
              {c}
              <button
                type="button"
                className="cat-remove"
                onClick={() => removeCategory(c)}
                aria-label={`Remove ${c}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="cat-add">
          <input
            type="text"
            value={catInput}
            placeholder="Add a category…"
            onChange={(ev) => setCatInput(ev.target.value)}
            onKeyDown={(ev) => ev.key === "Enter" && addCategory()}
          />
          <button type="button" onClick={addCategory}>Add</button>
        </div>
        {catMsg && <p className="cat-msg">{catMsg}</p>}
      </div>

      <h2>Recent expenses</h2>
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
          {expenses.map((e) => (
            <tr key={e.id}>
              <td>{e.date}</td>
              <td>{e.merchant}</td>
              <td>{e.category}</td>
              <td className="num">
                {Number(e.amount).toFixed(2)} {e.currency}
              </td>
            </tr>
          ))}
          {expenses.length === 0 && (
            <tr>
              <td colSpan={4} className="empty">
                No expenses yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2>Deposits</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Merchant</th>
            <th className="num">Amount</th>
          </tr>
        </thead>
        <tbody>
          {deposits.map((d) => (
            <tr key={d.id}>
              <td>{d.date}</td>
              <td>{d.merchant}</td>
              <td className="num">
                {Number(d.amount).toFixed(2)} {d.currency}
              </td>
            </tr>
          ))}
          {deposits.length === 0 && (
            <tr>
              <td colSpan={3} className="empty">
                No deposits yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
