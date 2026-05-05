import { useState, useEffect, useCallback } from "react";

// ─── Simulated SSH fetch (replace with your real backend) ──────────────────
// In production, replace `fetchVPSData` with a call to your backend API
// that runs SSH commands and returns the parsed data.

// In production, replace `fetchVPSData` with a call to your backend API
// that runs SSH commands and returns the parsed data.

async function fetchVPSData() {
  const res = await fetch("/api/vps");
  if (!res.ok) throw new Error(`Backend returned ${res.status}`);
  const data = await res.json();
  return data.map((s) => ({ ...s, lastChecked: new Date(s.lastChecked) }));
}

// ─── Helpers ──────────────────────────────────────────────────────────────
const pct = (used, total) => Math.round((used / total) * 100);

function statusColor(status, cpu, disk) {
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
    <span style={{ position: "relative", display: "inline-block", width: 10, height: 10, marginRight: 6 }}>
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

function ServerCard({ server, selected, onClick }) {
  const diskPct = pct(server.disk.used, server.disk.total);
  const ramPct = pct(server.ram.used, server.ram.total);
  const sc = statusColor(server.status, server.cpu, server.disk);

  return (
    <div
      onClick={onClick}
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

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
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
          {server.status.toUpperCase()}
        </div>
      </div>

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
    </div>
  );
}

function DetailPanel({ server, onDelete }) {
  if (!server) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#333", fontFamily: "monospace", fontSize: 13 }}>
      ← selecione um servidor
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
    <div style={{ height: "100%", overflowY: "auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24, paddingBottom: 16, borderBottom: "1px solid #1e1e3a" }}>
        <StatusDot status={server.status} cpu={server.cpu} disk={server.disk} />
        <h2 style={{ margin: 0, fontSize: 20, fontFamily: "'JetBrains Mono', monospace", color: "#e8e8ff" }}>
          {server.name}
        </h2>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#444", fontFamily: "monospace" }}>
          checked {server.lastChecked.toLocaleTimeString()}
        </span>
      </div>

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
        REMOVER SERVIDOR
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
  const [servers, setServers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [showAddModal, setShowAddModal] = useState(false);
  const [formData, setFormData] = useState({ name: "", ip: "", location: "Brasil", user: "root", ssh_key: "", password: "", sudo_password: "" });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchVPSData();
      setServers(data);
      setLastRefresh(new Date());
    } catch (e) {
      console.error("Error fetching servers:", e);
    }
    setLoading(false);
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await fetch("/api/vps", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });
      setShowAddModal(false);
      setFormData({ name: "", ip: "", location: "Brasil", user: "root", ssh_key: "", password: "", sudo_password: "" });
      refresh();
    } catch (e) {
      alert("Erro ao adicionar servidor");
    }
    setLoading(false);
  };

  const handleDelete = async (id) => {
    setLoading(true);
    try {
      await fetch(`/api/vps/${id}`, { method: "DELETE" });
      setSelected(null);
      refresh();
    } catch (e) {
      alert("Erro ao remover servidor");
    }
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []);

  const online = servers.filter((s) => s.status === "online").length;
  const warning = servers.filter((s) => s.status === "warning" || s.cpu > 65 || pct(s.disk.used, s.disk.total) > 75).length;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@700;800&display=swap');
        :root { --accent: #00e5a0; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #04040d; color: #e8e8ff; font-family: 'Syne', sans-serif; min-height: 100vh; }
        ::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: #080810; } ::-webkit-scrollbar-thumb { background: #1e1e3a; border-radius: 2px; }
        @keyframes ping { 0% { transform: scale(1); opacity: 0.6; } 100% { transform: scale(2.4); opacity: 0; } }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 20px", minHeight: "100vh" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 32 }}>
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 800, letterSpacing: -0.5 }}>
              <span style={{ color: "var(--accent)" }}>VPS</span> Monitor
            </h1>
            <div style={{ fontSize: 12, color: "#444", fontFamily: "monospace", marginTop: 2 }}>
              {servers.length} servidores · atualizado {lastRefresh.toLocaleTimeString()}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            {/* Summary badges */}
            <div style={{ display: "flex", gap: 8 }}>
              {[
                { label: `${online} online`, color: "#00e5a0" },
                { label: `${warning} atenção`, color: "#ffaa00" },
                { label: `${servers.length - online - warning < 0 ? 0 : servers.length - online - warning} offline`, color: "#ff3b3b" },
              ].map(({ label, color }) => (
                <span key={label} style={{
                  fontSize: 11, color, background: `${color}18`, border: `1px solid ${color}44`,
                  borderRadius: 6, padding: "4px 10px", fontFamily: "monospace", letterSpacing: 0.5,
                }}>{label}</span>
              ))}
            </div>

            <button
              onClick={() => setShowAddModal(true)}
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
              disabled={loading}
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

        {/* Main layout */}
        <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 20, alignItems: "start" }}>
          {/* Server list */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {servers.map((s) => (
              <ServerCard
                key={s.id}
                server={s}
                selected={selected?.id === s.id}
                onClick={() => setSelected(s.id === selected?.id ? null : s)}
              />
            ))}
          </div>

          {/* Detail panel */}
          <div style={{
            background: "#080810", border: "1px solid #1e1e3a", borderRadius: 12,
            padding: 24, minHeight: 480, position: "sticky", top: 20,
          }}>
            <DetailPanel server={selected} onDelete={handleDelete} />
          </div>
        </div>

        {/* Modal Adicionar VPS */}
        {showAddModal && (
          <div style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 20
          }}>
            <div style={{
              background: "#080810", border: "1px solid #1e1e3a", borderRadius: 16,
              padding: 32, maxWidth: 500, width: "100%", boxShadow: "0 20px 50px rgba(0,0,0,0.5)"
            }}>
              <h2 style={{ margin: "0 0 24px 0", fontSize: 22 }}>Novo Servidor</h2>
              <form onSubmit={handleAdd} style={{ display: "grid", gap: 16 }}>
                {[
                  { label: "Nome do Servidor", key: "name", placeholder: "ex: Produção" },
                  { label: "IP do Servidor", key: "ip", placeholder: "191.252.000.00" },
                  { label: "Localização", key: "location", placeholder: "Brasil" },
                  { label: "Usuário", key: "user", placeholsder: "root" },
                  { label: "Chave SSH", key: "ssh_key", placeholder: "C:\\Users\\Username\\.ssh\\ed25519'" },
                  { label: "Senha SSH (opcional)", key: "password", placeholder: "Senha se não usar chave", type: "password" },
                  { label: "Senha Sudo (opcional)", key: "sudo_password", placeholder: "Caso o usuário não seja root", type: "password" },
                ].map(({ label, key, placeholder, type = "text" }) => (
                  <div key={key}>
                    <label style={{ display: "block", fontSize: 10, color: "#666", letterSpacing: 1, marginBottom: 6 }}>{label.toUpperCase()}</label>
                    <input 
                      type={type}
                      required={key !== "password" && key !== "ssh_key"}
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
                <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
                  <button 
                    type="button" 
                    onClick={() => setShowAddModal(false)}
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
                    style={{
                      flex: 1, background: "var(--accent)", border: "none",
                      color: "#04040d", borderRadius: 8, padding: "12px", cursor: "pointer",
                      fontFamily: "monospace", fontWeight: 700
                    }}
                  >
                    SALVAR
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{ marginTop: 32, textAlign: "center", fontSize: 11, color: "#333", fontFamily: "monospace" }}>
          Para conectar às suas VPS reais, veja o arquivo README incluído
        </div>
      </div>
    </>
  );
}
