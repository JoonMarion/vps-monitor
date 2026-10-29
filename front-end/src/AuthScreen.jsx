import { useState } from "react";
import { apiRequest } from "./api";

export default function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "", confirmPassword: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const registering = mode === "register";

  function switchMode(next) {
    setMode(next);
    setForm((current) => ({ ...current, password: "", confirmPassword: "" }));
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (registering && form.password !== form.confirmPassword) {
      setError("As senhas não coincidem.");
      return;
    }
    setBusy(true);
    try {
      const { user } = await apiRequest(`/api/auth/${mode}`, {
        method: "POST", body: { name: form.name, email: form.email, password: form.password },
      });
      onAuthenticated(user);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-intro">
        <div className="brand"><span>VPS</span> Monitor</div>
        <div className="auth-eyebrow"><span className="live-dot" /> SEUS SERVIDORES, EM UM SÓ LUGAR</div>
        <h1>O controle da sua<br />infraestrutura.</h1>
        <p>Acompanhe CPU, memória, disco e rede das suas VPS em um painel pessoal.</p>
        <div className="auth-features">
          <span>01 <strong>Crie sua conta</strong></span>
          <span>02 <strong>Adicione suas VPS</strong></span>
          <span>03 <strong>Acompanhe as métricas</strong></span>
        </div>
        <div className="auth-privacy">Suas VPS ficam salvas na sua conta e visíveis apenas para você.</div>
      </section>

      <section className="auth-card" aria-labelledby="auth-title">
        <div className="auth-tabs" aria-label="Acesso à conta">
          <button type="button" className={!registering ? "active" : ""} disabled={busy} onClick={() => switchMode("login")}>Entrar</button>
          <button type="button" className={registering ? "active" : ""} disabled={busy} onClick={() => switchMode("register")}>Criar conta</button>
        </div>
        <h2 id="auth-title">{registering ? "Crie sua conta" : "Acesse seu painel"}</h2>
        <p>{registering ? "Comece a organizar seus servidores." : "Entre para acompanhar suas VPS."}</p>
        <form onSubmit={submit} className="auth-form">
          {registering && (
            <label htmlFor="account-name">Nome
              <input id="account-name" autoComplete="name" required maxLength={100} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} disabled={busy} />
            </label>
          )}
          <label htmlFor="account-email">E-mail
            <input id="account-email" type="email" autoComplete="email" required maxLength={254} placeholder="voce@exemplo.com" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} disabled={busy} />
          </label>
          <label htmlFor="account-password">Senha
            <input id="account-password" type="password" autoComplete={registering ? "new-password" : "current-password"} aria-describedby={registering ? "account-password-hint" : undefined} required minLength={registering ? 8 : undefined} maxLength={128} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} disabled={busy} />
          </label>
          {registering && <small id="account-password-hint" style={{ marginTop: -12 }}>Use pelo menos 8 caracteres.</small>}
          {registering && (
            <label htmlFor="account-confirm-password">Confirmar senha
              <input id="account-confirm-password" type="password" autoComplete="new-password" required maxLength={128} value={form.confirmPassword} onChange={(e) => setForm({ ...form, confirmPassword: e.target.value })} disabled={busy} />
            </label>
          )}
          {error && <div className="error-message" role="alert">{error}</div>}
          <button type="submit" className="primary-button" disabled={busy}>{busy ? "Aguarde..." : registering ? "CRIAR CONTA" : "ENTRAR"} <span aria-hidden="true">→</span></button>
        </form>
      </section>
    </main>
  );
}
