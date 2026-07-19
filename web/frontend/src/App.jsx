import { Navigate, Route, Routes, Link, useNavigate } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import bgImage from "./Dollar2.jpg";
import Login from "./pages/Login.jsx";
import Upload from "./pages/Upload.jsx";
import Dashboard from "./pages/Dashboard.jsx";

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  return (
    <nav className="navbar">
      <span className="brand">💸 Personal Expense Tracker</span>
      <div className="nav-links">
        <Link to="/">Dashboard</Link>
        <Link to="/upload">Upload</Link>
        <span className="nav-user">{user.email}</span>
        <button
          className="btn-link"
          onClick={() => {
            logout();
            navigate("/login");
          }}
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
      <div
        className="bg-layer"
        style={{ backgroundImage: `url(${bgImage})` }}
        aria-hidden="true"
      />
      <NavBar />
      <main className="container">
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
