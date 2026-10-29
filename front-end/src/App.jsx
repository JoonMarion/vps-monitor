import { useState, useEffect, useCallback, useRef } from "react";
import AuthScreen from "./AuthScreen";
import { apiRequest } from "./api";

// ─── Helpers ──────────────────────────────────────────────────────────────
const pct = (used, total) => total > 0 ? Math.round((used / total) * 100) : 0;

function statusColor(status, cpu, disk) {
  if (status === "connecting") return "#78a7ff";
  if (status === "offline") return "#ff3b3b";
  const diskPct = typeof disk === "object" ? pct(disk.used, disk.total) : disk;
  if (cpu > 85 || diskPct > 90) return "#ffaa00";
  if (status === "warning" || cpu > 65 || diskPct > 75) return "#ffaa00";
  return "#00e5a0";
}

function Bar({ value, max = 100, warn = 65, danger = 85 }) {
  const p = Math.min(100, Math.round((value / max) * 100));
  const color =
    p >= danger ? "#ff3b3b" : p >= warn ? "#ffaa00" : "var(--accent)";
  return (
    <div style={{ position: "relative", height: 6, background: "#1a1a2e", borderRadius: 3 }}>
      <div
        style={{
          width: `${p}%`,
          height: "100%",
          background: color,
          borderRadius: 3,
          transition: "width 0.6s ease",
          boxShadow: `0 0 8px ${color}88`,
        }}
      />
    </div>
  );
}

function Gauge({ value, label }) {
  const color =
    value >= 85 ? "#ff3b3b" : value >= 65 ? "#ffaa00" : "var(--accent)";
  const r = 28;
  const circ = 2 * Math.PI * r;
  const dash = circ - (value / 100) * circ;
  return (
    <div style={{ textAlign: "center" }}>
      <svg width={70} height={70} viewBox="0 0 70 70">
        <circle cx={35} cy={35} r={r} fill="none" stroke="#1a1a2e" strokeWidth={6} />
        <circle
          cx={35} cy={35} r={r}
          fill="none"
          stroke={color}
          strokeWidth={6}
          strokeDasharray={circ}
          strokeDashoffset={dash}
          strokeLinecap="round"
          transform="rotate(-90 35 35)"
          style={{ transition: "stroke-dashoffset 0.8s ease, stroke 0.4s" }}
          filter={`drop-shadow(0 0 4px ${color})`}
        />
        <text x={35} y={39} textAnchor="middle" fill={color} fontSize={12} fontFamily="'JetBrains Mono', monospace" fontWeight="700">
          {Math.round(value)}%
        </text>
      </svg>
      <div style={{ fontSize: 10, color: "#666", letterSpacing: 1, marginTop: -4 }}>{label}</div>
    </div>
  );
}

function StatusDot({ status, cpu, disk }) {
  const color = statusColor(status, cpu, disk);
  return (
    <span style={{ position: "relative", display: "inline-block", width: 10, height: 10, marginRight: 6, flexShrink: 0 }}>
      <span style={{
        display: "block", width: 10, height: 10, borderRadius: "50%",
        background: color, boxShadow: `0 0 6px ${color}`,
      }} />
      {status !== "offline" && (
        <span style={{
          position: "absolute", inset: 0, borderRadius: "50%",
          background: color, opacity: 0.4,
          animation: "ping 1.8s ease-out infinite",
        }} />
      )}
    </span>
  );
}

function ConnectionProgress({ server, compact = false }) {
  return (
    <div className={`connection-progress${compact ? " compact" : ""}`} role="status">
      <span className="connection-spinner" aria-hidden="true" />
      <div>
        <strong>Conectando à VPS...</strong>
        <p>{compact ? "Tentando conexão SSH e coletando métricas." : `Tentando conexão SSH em ${server.ip}, porta ${server.port || 22}. As métricas aparecerão assim que a coleta terminar.`}</p>
      </div>
    </div>
  );
}

function ServerCard({ server, selected, onClick }) {
  const connecting = server.status === "connecting";
  const diskPct = pct(server.disk.used, server.disk.total);
  const ramPct = pct(server.ram.used, server.ram.total);
  const sc = statusColor(server.status, server.cpu, server.disk);

  return (
    <div
      onClick={onClick}
      className="server-card"
      aria-busy={connecting}
      style={{
        background: selected ? "#0d0d1a" : "#080810",
        border: `1px solid ${selected ? sc : "#1e1e3a"}`,
        borderRadius: 12,
        padding: "20px 22px",
        cursor: "pointer",
        transition: "all 0.25s",
        boxShadow: selected ? `0 0 20px ${sc}22` : "none",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {selected && (
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, height: 2,
          background: `linear-gradient(90deg, transparent, ${sc}, transparent)`,
        }} />
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14, gap: 8, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <StatusDot status={server.status} cpu={server.cpu} disk={server.disk} />
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, fontSize: 15, color: "#e8e8ff" }}>
              {server.name}
            </span>
          </div>
          <div style={{ color: "#555", fontSize: 11, marginTop: 3, letterSpacing: 0.5 }}>
            {server.ip} · {server.location}
          </div>
        </div>
        <div style={{
          fontSize: 10, fontFamily: "monospace", color: sc,
          background: `${sc}18`, border: `1px solid ${sc}44`,
          borderRadius: 4, padding: "2px 8px", letterSpacing: 1,
        }}>
          {connecting ? "CONECTANDO" : server.status.toUpperCase()}
        </div>
      </div>

      {connecting ? <ConnectionProgress server={server} compact /> : <>
      <div style={{ display: "flex", gap: 16, justifyContent: "center", marginBottom: 16 }}>
        <Gauge value={Math.round(server.cpu)} label="CPU" />
        <Gauge value={ramPct} label="RAM" />
        <Gauge value={diskPct} label="DISK" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px", fontSize: 11, color: "#888" }}>
        {[
          ["UPTIME", server.uptime],
          ["OS", server.os],
          ["PROCS", server.processes],
          ["LOAD", server.load[0].toFixed(2)],
        ].map(([k, v]) => (
          <div key={k}>
            <span style={{ color: "#444", letterSpacing: 1 }}>{k} </span>
            <span style={{ color: "#aaa", fontFamily: "monospace" }}>{v}</span>
          </div>
        ))}
      </div>
      {server.error_details && <p className="connection-error">{server.error_details}</p>}
      </>}
    </div>
  );
}

function DetailPanel({ server, onDelete, deleting }) {
  if (!server) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#333", fontFamily: "monospace", fontSize: 13 }}>
      ← selecione um servidor
    </div>
  );

  if (server.status === "connecting") return (
    <div className="connecting-details" aria-busy="true">
      <h2>{server.name}</h2>
      <p>{server.ip} · {server.location}</p>
      <ConnectionProgress server={server} />
    </div>
  );

  const sc = statusColor(server.status, server.cpu, server.disk);
  const diskPct = pct(server.disk.used, server.disk.total);
  const ramPct = pct(server.ram.used, server.ram.total);

  const rows = [
    ["hostname", server.name],
    ["ip address", server.ip],
    ["location", server.location],
    ["os", server.os],
    ["uptime", server.uptime],
    ["processes", server.processes],
    ["load avg", server.load.join(" · ")],
    ["net rx", server.network.rx],
    ["net tx", server.network.tx],
  ];

  return (
    <div style={{ height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24, paddingBottom: 16, borderBottom: "1px solid #1e1e3a" }}>
        <StatusDot status={server.status} cpu={server.cpu} disk={server.disk} />
        <h2 style={{ margin: 0, fontSize: 20, fontFamily: "'JetBrains Mono', monospace", color: "#e8e8ff" }}>
          {server.name}
        </h2>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#444", fontFamily: "monospace" }}>
          {server.lastChecked ? `checked ${server.lastChecked.toLocaleTimeString()}` : "ainda não verificado"}
        </span>
      </div>

      {server.error_details && <div className="error-message" role="status" style={{ marginBottom: 20 }}>{server.error_details}</div>}

      {/* Metric bars */}
      <div style={{ display: "grid", gap: 18, marginBottom: 24 }}>
        {[
          { label: "CPU Usage", value: Math.round(server.cpu), unit: `${Math.round(server.cpu)}%` },
          { label: "RAM", value: ramPct, unit: `${server.ram.used} GB / ${server.ram.total} GB` },
          { label: "Disk", value: diskPct, unit: `${server.disk.used} GB / ${server.disk.total} GB` },
        ].map(({ label, value, unit }) => (
          <div key={label}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12 }}>
              <span style={{ color: "#666", letterSpacing: 1 }}>{label.toUpperCase()}</span>
              <span style={{ color: value >= 85 ? "#ff3b3b" : value >= 65 ? "#ffaa00" : sc, fontFamily: "monospace" }}>{unit}</span>
            </div>
            <Bar value={value} />
          </div>
        ))}
      </div>

      {/* Detail rows */}
      <div style={{ background: "#080810", border: "1px solid #1e1e3a", borderRadius: 8, overflow: "hidden" }}>
        {rows.map(([k, v], i) => (
          <div key={k} style={{
            display: "flex", padding: "10px 16px",
            borderBottom: i < rows.length - 1 ? "1px solid #12121f" : "none",
            fontSize: 12,
          }}>
            <span style={{ color: "#444", letterSpacing: 1, width: 100, flexShrink: 0 }}>{k}</span>
            <span style={{ color: "#aaa", fontFamily: "monospace" }}>{v}</span>
          </div>
        ))}
      </div>

      <button 
        disabled={deleting}
        onClick={() => {
          if (confirm(`Tem certeza que deseja remover o servidor ${server.name}?`)) {
            onDelete(server.id);
          }
        }}
        style={{
          marginTop: 20, width: "100%", background: "transparent", border: "1px solid #ff3b3b44",
          color: "#ff3b3b", borderRadius: 8, padding: "10px", cursor: "pointer",
          fontSize: 12, fontFamily: "monospace", letterSpacing: 1, transition: "0.2s"
        }}
      >
        {deleting ? "REMOVENDO..." : "REMOVER SERVIDOR"}
      </button>

      {/* Load avg visual */}
      <div style={{ marginTop: 20, background: "#080810", border: "1px solid #1e1e3a", borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 11, color: "#444", letterSpacing: 1, marginBottom: 12 }}>LOAD AVERAGE</div>
        <div style={{ display: "flex", gap: 16 }}>
          {["1 min", "5 min", "15 min"].map((label, i) => (
            <div key={label} style={{ flex: 1, textAlign: "center" }}>
              <div style={{ fontSize: 18, fontFamily: "monospace", color: server.load[i] > 1.5 ? "#ff3b3b" : server.load[i] > 1 ? "#ffaa00" : sc }}>
                {server.load[i].toFixed(2)}
              </div>
              <div style={{ fontSize: 10, color: "#444", marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    apiRequest("/api/auth/me", { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setUser(data.user);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setSessionError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setCheckingSession(false);
      });
    return () => controller.abort();
  }, [attempt]);

  const sessionExpired = useCallback(() => {
    setUser(null);
    setCheckingSession(true);
    setSessionError("");
    setAttempt((value) => value + 1);
  }, []);

  async function logout() {
    await apiRequest("/api/auth/logout", { method: "POST" });
    setUser(null);
  }

  if (checkingSession) return <main className="session-state" role="status">Carregando sua conta...</main>;
  if (sessionError) return (
    <main className="session-state">
      <p className="error-message" role="alert">{sessionError}</p>
      <button className="primary-button" onClick={sessionExpired}>Tentar novamente</button>
    </main>
  );
  if (!user) return <AuthScreen onAuthenticated={setUser} />;
  return <Dashboard key={user.id} user={user} onLogout={logout} onSessionExpired={sessionExpired} />;
}

const emptyServerForm = { name: "", ip: "", port: 22, location: "Brasil", user: "root", ssh_key: "", password: "", passphrase: "" };

function connectingServer(server) {
  return {
    ...server, status: "connecting", lastChecked: null, cpu: 0,
    ram: { used: 0, total: 0 }, disk: { used: 0, total: 0 },
    load: [0, 0, 0], network: { rx: "—", tx: "—" },
    uptime: "—", os: "—", processes: 0,
  };
}

function Dashboard({ user, onLogout, onSessionExpired }) {
  const [servers, setServers] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [formData, setFormData] = useState({ ...emptyServerForm });
  const pollingController = useRef(null);
  const selected = servers.find((server) => server.id === selectedId) || null;
  const refresh = () => {
    // Stop an older response from replacing a newly added, connecting card.
    pollingController.current?.abort();
    setRefreshVersion((value) => value + 1);
  };

  useEffect(() => {
    const controller = new AbortController();
    pollingController.current = controller;
    let timeout;
    async function poll() {
      setLoading(true);
      try {
        const data = await apiRequest("/api/vps", { signal: controller.signal });
        if (controller.signal.aborted) return;
        setServers(data.map((server) => ({ ...server, lastChecked: new Date(server.lastChecked) })));
        setLastRefresh(new Date());
        setError("");
      } catch (failure) {
        if (controller.signal.aborted) return;
        if (failure.status === 401) {
          onSessionExpired();
          return;
        }
        setError(failure.message);
        setServers((current) => current.map((server) => server.status === "connecting" ? {
          ...server, status: "offline",
          error_details: `Não foi possível verificar a conexão. ${failure.message}`,
        } : server));
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          timeout = setTimeout(poll, 30000);
        }
      }
    }
    poll();
    return () => {
      controller.abort();
      clearTimeout(timeout);
    };
  }, [refreshVersion, onSessionExpired]);

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      const created = await apiRequest("/api/vps", {
        method: "POST",
        body: { ...formData, port: Number(formData.port) },
      });
      refresh();
      setServers((current) => [...current, connectingServer(created)]);
      setSelectedId(created.id);
      setShowAddModal(false);
      setFormData({ ...emptyServerForm });
    } catch (failure) {
      if (failure.status === 401) onSessionExpired();
      else setFormError(failure.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    setSaving(true);
    setError("");
    try {
      await apiRequest(`/api/vps/${id}`, { method: "DELETE" });
      setServers((current) => current.filter((server) => server.id !== id));
      setSelectedId(null);
      refresh();
    } catch (failure) {
      if (failure.status === 401) onSessionExpired();
      else setError(failure.message);
    } finally {
      setSaving(false);
    }
  };

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await onLogout();
    } catch (failure) {
      if (failure.status === 401) onSessionExpired();
      else setError(failure.message);
      setLoggingOut(false);
    }
  }

  const offline = servers.filter((s) => s.status === "offline").length;
  const connecting = servers.filter((s) => s.status === "connecting").length;
  const warning = servers.filter((s) => s.status !== "offline" && s.status !== "connecting" && (s.status === "warning" || s.cpu > 65 || pct(s.disk.used, s.disk.total) > 75)).length;
  const online = servers.length - offline - warning - connecting;

  return (
    <>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 20px", minHeight: "100vh" }}>
        <div className="account-bar">
          <span>Olá, <strong>{user.name}</strong> <span className="account-email">· {user.email}</span></span>
          <button className="secondary-button" disabled={loggingOut || saving} onClick={handleLogout}>{loggingOut ? "Saindo..." : "Sair da conta"}</button>
        </div>
        {/* Header */}
        <div className="dashboard-header">
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 800, letterSpacing: -0.5 }}>
              <span style={{ color: "var(--accent)" }}>VPS</span> Monitor
            </h1>
            <div style={{ fontSize: 12, color: "#444", fontFamily: "monospace", marginTop: 2 }}>
              {servers.length} servidores · {lastRefresh ? `atualizado ${lastRefresh.toLocaleTimeString()}` : "aguardando atualização"}
            </div>
          </div>

          <div className="dashboard-actions">
            {/* Summary badges */}
            <div style={{ display: "flex", gap: 8 }}>
              {[
                { label: `${online} online`, color: "#00e5a0" },
                { label: `${warning} atenção`, color: "#ffaa00" },
                { label: `${offline} offline`, color: "#ff3b3b" },
                ...(connecting ? [{ label: `${connecting} conectando`, color: "#78a7ff" }] : []),
              ].map(({ label, color }) => (
                <span key={label} style={{
                  fontSize: 11, color, background: `${color}18`, border: `1px solid ${color}44`,
                  borderRadius: 6, padding: "4px 10px", fontFamily: "monospace", letterSpacing: 0.5,
                }}>{label}</span>
              ))}
            </div>

            <button
              onClick={() => { setFormError(""); setShowAddModal(true); }}
              disabled={saving || loggingOut}
              style={{
                background: "var(--accent)", border: "none", color: "#04040d",
                borderRadius: 8, padding: "8px 16px", cursor: "pointer",
                fontFamily: "monospace", fontSize: 12, fontWeight: 700,
                transition: "all 0.2s",
              }}
            >
              + ADICIONAR VPS
            </button>

            {/* Refresh button */}
            <button
              onClick={refresh}
              disabled={loading || saving}
              style={{
                background: "transparent", border: "1px solid #1e1e3a", color: loading ? "#333" : "#888",
                borderRadius: 8, padding: "8px 16px", cursor: loading ? "not-allowed" : "pointer",
                fontFamily: "monospace", fontSize: 12, display: "flex", alignItems: "center", gap: 6,
                transition: "all 0.2s",
              }}
            >
              <span style={loading ? { display: "inline-block", animation: "spin 0.7s linear infinite" } : {}}>↻</span>
              {loading ? "atualizando..." : "atualizar"}
            </button>
          </div>
        </div>

        {error && <div className="error-message dashboard-error" role="alert">{error}</div>}

        {!servers.length && (
          <div className="empty-state" role="status">
            <h2>{loading ? "Buscando suas VPS..." : "Seu painel começa aqui"}</h2>
            <p>{loading ? "Aguarde enquanto consultamos seus servidores." : "Adicione sua primeira VPS. Ela ficará salva na sua conta para os próximos acessos."}</p>
            {!loading && <button className="primary-button" onClick={() => { setFormError(""); setShowAddModal(true); }}>+ ADICIONAR VPS</button>}
          </div>
        )}

        {/* Main layout */}
        {!!servers.length && <div className="dashboard-grid">
          {/* Server list */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {servers.map((s) => (
              <ServerCard
                key={s.id}
                server={s}
                selected={selected?.id === s.id}
                onClick={() => setSelectedId(s.id === selectedId ? null : s.id)}
              />
            ))}
          </div>

          {/* Detail panel */}
          <div style={{
            background: "#080810", border: "1px solid #1e1e3a", borderRadius: 12,
            padding: 24, minHeight: 480, position: "sticky", top: 20,
          }}>
            <DetailPanel server={selected} onDelete={handleDelete} deleting={saving} />
          </div>
        </div>}

        {/* Modal Adicionar VPS */}
        {showAddModal && (
          <div style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 20
          }}>
            <div role="dialog" aria-modal="true" aria-labelledby="new-server-title" className="server-modal" style={{
              background: "#080810", border: "1px solid #1e1e3a", borderRadius: 16,
              padding: 32, maxWidth: 500, width: "100%", boxShadow: "0 20px 50px rgba(0,0,0,0.5)"
            }}>
              <h2 id="new-server-title" style={{ margin: "0 0 24px 0", fontSize: 22 }}>Novo Servidor</h2>
              <form onSubmit={handleAdd} style={{ display: "grid", gap: 16 }}>
                {[
                  { label: "Nome do Servidor", key: "name", placeholder: "ex: Produção" },
                  { label: "IP público do Servidor", key: "ip", placeholder: "IPv4 ou IPv6 da VPS" },
                  { label: "Porta SSH", key: "port", placeholder: "22", type: "number" },
                  { label: "Localização", key: "location", placeholder: "Brasil" },
                  { label: "Usuário SSH", key: "user", placeholder: "root" },
                  { label: "Senha SSH (opcional)", key: "password", placeholder: "Senha se não usar chave", type: "password" },
                ].map(({ label, key, placeholder, type = "text" }) => (
                  <div key={key}>
                    <label htmlFor={`vps-${key}`} style={{ display: "block", fontSize: 10, color: "#999", letterSpacing: 1, marginBottom: 6 }}>{label.toUpperCase()}</label>
                    <input 
                      id={`vps-${key}`}
                      type={type}
                      required={key !== "password"}
                      disabled={saving}
                      maxLength={key === "password" ? 1024 : key === "ip" ? 45 : 100}
                      min={key === "port" ? 1 : undefined}
                      max={key === "port" ? 65535 : undefined}
                      autoComplete={key === "password" ? "new-password" : "off"}
                      value={formData[key]}
                      onChange={(e) => setFormData({ ...formData, [key]: e.target.value })}
                      placeholder={placeholder}
                      style={{
                        width: "100%", background: "#04040d", border: "1px solid #1e1e3a",
                        borderRadius: 8, padding: "10px 14px", color: "#e8e8ff", fontSize: 13,
                        outline: "none", fontFamily: "monospace"
                      }}
                    />
                  </div>
                ))}
                <label className="vps-key-label" htmlFor="vps-ssh-key">CHAVE PRIVADA SSH (OPCIONAL)
                  <textarea id="vps-ssh-key" rows={4} maxLength={32768} placeholder="Cole o conteúdo da chave privada, incluindo BEGIN e END" value={formData.ssh_key} onChange={(e) => setFormData({ ...formData, ssh_key: e.target.value })} disabled={saving} autoComplete="off" spellCheck={false} />
                  <small>Preencha a senha SSH ou a chave privada. Se preencher os dois, a chave será usada.</small>
                </label>
                {formData.ssh_key && <label className="vps-key-label" htmlFor="vps-passphrase">SENHA DA CHAVE (OPCIONAL)
                  <input id="vps-passphrase" type="password" maxLength={1024} value={formData.passphrase} onChange={(e) => setFormData({ ...formData, passphrase: e.target.value })} disabled={saving} autoComplete="new-password" />
                </label>}
                {formError && <div className="error-message" role="alert">{formError}</div>}
                <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
                  <button 
                    type="button" 
                    disabled={saving}
                    onClick={() => { setShowAddModal(false); setFormData({ ...emptyServerForm }); setFormError(""); }}
                    style={{
                      flex: 1, background: "transparent", border: "1px solid #1e1e3a",
                      color: "#888", borderRadius: 8, padding: "12px", cursor: "pointer",
                      fontFamily: "monospace"
                    }}
                  >
                    CANCELAR
                  </button>
                  <button 
                    type="submit"
                    disabled={saving}
                    style={{
                      flex: 1, background: "var(--accent)", border: "none",
                      color: "#04040d", borderRadius: 8, padding: "12px", cursor: "pointer",
                      fontFamily: "monospace", fontWeight: 700
                    }}
                  >
                    {saving ? "SALVANDO..." : "SALVAR"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{ marginTop: 32, textAlign: "center", fontSize: 11, color: "#333", fontFamily: "monospace" }}>
          Suas VPS estão salvas na sua conta · atualização automática a cada 30 segundos
        </div>
      </div>
    </>
  );
}
