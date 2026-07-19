import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { login, register, user } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Redirect already-authenticated users away from the login page. Doing this
  // in an effect (not during render) avoids the React "cannot update while
  // rendering" crash that can blank the screen.
  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-card">
      <h1>{mode === "login" ? "Sign in" : "Create account"}</h1>
      <form onSubmit={onSubmit}>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn-primary" type="submit" disabled={busy}>
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Register"}
        </button>
      </form>
      <p className="toggle">
        {mode === "login" ? "No account yet?" : "Already have an account?"}{" "}
        <button
          className="btn-link"
          onClick={() => {
            setError("");
            setMode(mode === "login" ? "register" : "login");
          }}
        >
          {mode === "login" ? "Create one" : "Sign in"}
        </button>
      </p>
    </div>
  );
}
