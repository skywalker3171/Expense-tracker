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
    <div className="max-w-sm mx-auto mt-16 bg-sky-900 border border-sky-700 rounded-xl p-8 shadow-lg">
      <h1 className="mt-0 mb-6 text-xl font-semibold text-white">
        {mode === "login" ? "Sign in" : "Create account"}
      </h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-sm text-slate-300">
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="px-3 py-2.5 bg-sky-800 border border-sky-600 rounded-lg text-sm text-white placeholder-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm text-slate-300">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="px-3 py-2.5 bg-sky-800 border border-sky-600 rounded-lg text-sm text-white placeholder-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400"
          />
        </label>
        {error && <p className="text-red-400 text-sm m-0">{error}</p>}
        <button
          className="mt-1 w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-default text-white border-0 rounded-lg py-2.5 text-sm font-medium cursor-pointer transition-colors"
          type="submit"
          disabled={busy}
        >
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Register"}
        </button>
      </form>
      <p className="mt-4 text-sm text-slate-400 text-center">
        {mode === "login" ? "No account yet?" : "Already have an account?"}{" "}
        <button
          className="text-indigo-400 hover:underline bg-transparent border-0 cursor-pointer p-0 text-sm"
          onClick={() => { setError(""); setMode(mode === "login" ? "register" : "login"); }}
        >
          {mode === "login" ? "Create one" : "Sign in"}
        </button>
      </p>
    </div>
  );
}
