import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner, errMessage } from "../components/ui";

type Mode = "login" | "signup";

export default function Login() {
  const { login, signup } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup({
          email,
          password,
          workspace_name: workspace,
          name: name || undefined,
        });
      }
      navigate("/", { replace: true });
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="brand-mark">❄</span>
          <span className="brand-name">iceReach</span>
        </div>
        <h1 className="auth-title">
          {mode === "login" ? "Welcome back" : "Create your workspace"}
        </h1>
        <p className="auth-sub">
          {mode === "login"
            ? "Sign in to your email platform."
            : "Start sending smarter campaigns in minutes."}
        </p>

        <ErrorBanner message={error} />

        <form onSubmit={onSubmit} className="form">
          {mode === "signup" && (
            <>
              <label className="field">
                <span>Your name</span>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ada Lovelace"
                  autoComplete="name"
                />
              </label>
              <label className="field">
                <span>Workspace name</span>
                <input
                  type="text"
                  value={workspace}
                  onChange={(e) => setWorkspace(e.target.value)}
                  placeholder="Acme Inc"
                  required
                />
              </label>
            </>
          )}
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
            />
          </label>

          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create workspace"}
          </button>
        </form>

        <div className="auth-toggle">
          {mode === "login" ? (
            <span>
              No account?{" "}
              <button className="link" onClick={() => setMode("signup")}>
                Sign up
              </button>
            </span>
          ) : (
            <span>
              Already have an account?{" "}
              <button className="link" onClick={() => setMode("login")}>
                Sign in
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
