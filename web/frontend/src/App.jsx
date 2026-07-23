import { Navigate, Route, Routes, Link, useNavigate } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Login from "./pages/Login.jsx";
import Upload from "./pages/Upload.jsx";
import Dashboard from "./pages/Dashboard.jsx";

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="text-center py-16 text-slate-400">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  return (
    <nav className="bg-sky-900 border-b border-sky-700 px-6 py-3 flex items-center justify-between">
      <span className="font-bold text-white text-base">💸 Personal Expense Tracker</span>
      <div className="flex items-center gap-5 text-sm">
        <Link to="/" className="text-sky-200 hover:text-white no-underline">Dashboard</Link>
        <Link to="/upload" className="text-sky-200 hover:text-white no-underline">Upload</Link>
        <span className="text-sky-400">{user.email}</span>
        <button
          className="text-sky-200 hover:text-white bg-transparent border-0 cursor-pointer p-0 text-sm"
          onClick={() => { logout(); navigate("/login"); }}
        >
          Logout
        </button>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <>
      <NavBar />
      <main className="max-w-5xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <Dashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/upload"
            element={
              <RequireAuth>
                <Upload />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
