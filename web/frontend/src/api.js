// api.js — thin fetch wrapper that attaches the JWT bearer token.

const TOKEN_KEY = "expense_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let payload = body;
  if (body && !isForm) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(`/api${path}`, { method, headers, body: payload });

  if (res.status === 401) {
    setToken(null);
    throw new Error("Session expired. Please log in again.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}

export const api = {
  register: (email, password) =>
    request("/auth/register", { method: "POST", body: { email, password } }),
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request("/auth/me"),
  listExpenses: () => request("/expenses"),
  summary: () => request("/summary"),
  getCategories: () => request("/categories"),
  setCategories: (categories) =>
    request("/categories", { method: "PUT", body: { categories } }),
  resetDb: () => request("/reset", { method: "POST" }),
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/upload", { method: "POST", body: form, isForm: true });
  },
};
