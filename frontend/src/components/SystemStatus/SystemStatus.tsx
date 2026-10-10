import React, { useEffect, useState } from 'react';
import { Cpu, HardDrive, Activity, ShieldCheck, Globe, WifiOff, Server } from 'lucide-react';
import { apiGet, timeAgo, type EgressStatus, type GovernorStatus, type ModelsInfo } from '../../lib/backend';
import './SystemStatus.css';

// Live readings from the local backend (refreshed every 5 s). Nothing here is made up:
// when the backend can't be reached, the panel says so instead of showing numbers.
type Health = { model_loaded: boolean; engine_status: string };

const POLL_MS = 5000;
const ONLINE_NOW_S = 60;

const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v)}%`);
const level = (v: number | null | undefined) => (v == null ? '' : v >= 90 ? 'danger' : v >= 75 ? 'warning' : '');
const gb = (mb: number | null | undefined) => (mb == null ? '–' : (mb / 1024).toFixed(1));

const STATE_LABEL: Record<string, [string, string]> = {
  idle: ['Idle', 'success'],
  interactive: ['Ready', 'success'],
  high_load: ['Paused: PC busy', 'warning'],
  emergency: ['Paused: PC overloaded', 'danger'],
  user_paused: ['Paused by you', 'warning'],
};

const Bar: React.FC<{ label: string; right: string; value: number | null | undefined }> = ({ label, right, value }) => (
  <div className="progress-bar-container">
    <div className="progress-label"><span>{label}</span><span>{right}</span></div>
    <div className="progress-bg">
      <div className={`progress-fill ${level(value)}`} style={{ width: `${Math.min(100, Math.max(0, value ?? 0))}%` }} />
    </div>
  </div>
);

const SystemStatus: React.FC = () => {
  const [gov, setGov] = useState<GovernorStatus | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [egress, setEgress] = useState<EgressStatus | null>(null);
  const [modelName, setModelName] = useState('');
  const [latency, setLatency] = useState<number | null>(null);
  const [reachable, setReachable] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      const t0 = performance.now();
      try {
        const [g, h, e, m] = await Promise.all([
          apiGet<GovernorStatus>('/api/governor/status'),
          apiGet<Health>('/health'),
          apiGet<EgressStatus>('/api/egress/status'),
          apiGet<ModelsInfo>('/api/models'),
        ]);
        if (!alive) return;
        setLatency(Math.round(performance.now() - t0));
        setGov(g); setHealth(h); setEgress(e);
        // What is loaded wins; otherwise the chosen profile. Never throw on an unexpected shape.
        const profiles = Array.isArray(m?.profiles) ? m.profiles : [];
        setModelName(m?.loaded?.name ?? profiles.find(p => p.id === m?.active_profile)?.name ?? String(m?.active_profile ?? ''));
        setReachable(true);
      } catch {
        if (alive) { setReachable(false); setLatency(null); }
      }
    };
    poll();
    const id = window.setInterval(poll, POLL_MS);
    return () => { alive = false; window.clearInterval(id); };
  }, []);

  const gpu = gov?.gpu;
  const [stateText, stateClass] = STATE_LABEL[gov?.state ?? ''] ?? [gov?.state ?? '–', ''];
  const last = egress?.last ?? null;
  const onlineNow = !!last && last.decision === 'allowed' && (Date.now() - Date.parse(last.ts)) / 1000 < ONLINE_NOW_S;

  return (
    <aside className="system-status glass-panel">
      <div className="status-header">
        <h3>System Telemetry</h3>
        <Activity size={16} className={reachable ? 'icon-pulse' : ''} />
      </div>

      {reachable === false && <div className="status-offline-note">Backend not reachable. Readings paused.</div>}

      <div className="telemetry-widgets">
        <div className="widget">
          <div className="widget-header"><Cpu size={16} /><span>AI Core</span></div>
          <div className="widget-body">
            <div className="metric"><span className="label">State</span><span className={`value ${stateClass}`}>{stateText}</span></div>
            <div className="metric"><span className="label">Model</span><span className="value">{modelName || '–'}</span></div>
            <div className="metric">
              <span className="label">Engine</span>
              <span className={`value ${health?.model_loaded ? 'success' : 'muted'}`}>
                {health ? (health.model_loaded ? `Loaded (${health.engine_status})` : health.engine_status === 'UNAVAILABLE' ? 'Unavailable' : 'Not loaded') : '–'}
              </span>
            </div>
          </div>
        </div>

        <div className="widget">
          <div className="widget-header"><HardDrive size={16} /><span>This PC</span></div>
          <div className="widget-body">
            <Bar label="CPU" right={pct(gov?.cpu_percent)} value={gov?.cpu_percent} />
            <Bar label="RAM"
                 right={gov?.ram_total_gb ? `${gov.ram_used_gb} / ${gov.ram_total_gb} GB` : pct(gov?.ram_percent)}
                 value={gov?.ram_percent} />
            {gpu?.available ? (
              <Bar label={`VRAM · ${gpu.name ?? 'GPU'}`}
                   right={`${gb(gpu.vram_used_mb)} / ${gb(gpu.vram_total_mb)} GB${gpu.temp_c != null ? ` · ${Math.round(gpu.temp_c)}°C` : ''}`}
                   value={gpu.vram_percent} />
            ) : null}
            {gpu?.available && (gov?.sentinel_vram_mb ?? 0) > 0 && (
              <div className="privacy-sub">Sentinel's model uses {gb(gov?.sentinel_vram_mb)} GB of it</div>
            )}
            {gpu?.available ? null : (
              <div className="metric"><span className="label">GPU</span><span className="value muted">{gpu ? 'Not detected' : '–'}</span></div>
            )}
          </div>
        </div>

        <div className="widget">
          <div className="widget-header">
            {egress?.offline ? <WifiOff size={16} /> : onlineNow ? <Globe size={16} /> : <ShieldCheck size={16} />}
            <span>Privacy</span>
          </div>
          <div className="widget-body">
            <div className="metric">
              <span className="label">Internet</span>
              {egress?.offline
                ? <span className="value success">Offline mode</span>
                : onlineNow
                  ? <span className="value warning">Online now</span>
                  : <span className="value" title="Offline mode is off: approved tools may go online.">{egress ? 'Allowed (idle)' : '–'}</span>}
            </div>
            {last && (
              <div className="privacy-sub">
                Last {last.decision === 'blocked' ? 'blocked' : 'online'}: <strong>{last.host}</strong>
                {last.tool ? ` (${last.tool})` : ''} · {timeAgo(last.ts)}
              </div>
            )}
            {egress && (
              <div className="privacy-sub">This session: {egress.allowed_total} allowed · {egress.blocked_total} blocked</div>
            )}
          </div>
        </div>

        <div className="widget">
          <div className="widget-header"><Server size={16} /><span>Backend</span></div>
          <div className="widget-body">
            <div className="metric">
              <span className="label">Local API</span>
              <span className={`value ${reachable ? 'success' : reachable === false ? 'danger' : ''}`}>
                {reachable ? `${latency} ms` : reachable === false ? 'Not reachable' : '–'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};

export default SystemStatus;
