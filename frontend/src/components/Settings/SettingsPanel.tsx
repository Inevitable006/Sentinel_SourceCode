import React, { useState, useEffect } from 'react';
import './SettingsPanel.css';
import { apiGet, apiPost, ApiError, timeAgo, type EgressEvent, type EgressStatus, type UnlockStatus } from '../../lib/backend';

interface ModelProfile {
  id: string;
  name: string;
  description: string;
}

const SettingsPanel: React.FC = () => {
  const [systemPrompt, setSystemPrompt] = useState('Loading...');
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [activeModel, setActiveModel] = useState<string>('');
  const [localOnly, setLocalOnly] = useState(false);
  const [offline, setOffline] = useState(false);
  const [netEvents, setNetEvents] = useState<EgressEvent[]>([]);
  const [unlock, setUnlock] = useState<UnlockStatus | null>(null);
  const [pinCurrent, setPinCurrent] = useState('');
  const [pinNew, setPinNew] = useState('');
  const [pinNew2, setPinNew2] = useState('');
  const [securityPin, setSecurityPin] = useState('');
  const [newRecoveryKey, setNewRecoveryKey] = useState('');
  const [secretNames, setSecretNames] = useState<{ name: string; updated_at: string }[]>([]);
  const [secretName, setSecretName] = useState('');
  const [secretValue, setSecretValue] = useState('');
  const [chatDays, setChatDays] = useState(180);
  const [researchDays, setResearchDays] = useState(90);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');

  const getAuthInfo = async () => {
    let port = 8000;
    let token = "dev_fallback_token";
    // @ts-ignore
    if (window.sentinel?.auth) {
      // @ts-ignore
      port = await window.sentinel.auth.getBackendPort();
      // @ts-ignore
      token = await window.sentinel.auth.getSessionToken();
    }
    return { port, token };
  };

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const { port, token } = await getAuthInfo();
        const headers = { 'X-Sentinel-Session': token };
        
        // Fetch Settings (Prompt)
        const settingsRes = await fetch(`http://127.0.0.1:${port}/settings`, { headers });
        if (settingsRes.ok) {
          const data = await settingsRes.json();
          setSystemPrompt(data.system_prompt);
        }

        // Fetch Models
        const modelsRes = await fetch(`http://127.0.0.1:${port}/api/models`, { headers });
        if (modelsRes.ok) {
          const mData = await modelsRes.json();
          setModels(mData.profiles);
          setActiveModel(mData.active_profile);
        }
      } catch (err) {
        console.error(err);
        setSystemPrompt('Error loading settings.');
      }
    };
    
    fetchSettings();
  }, []);

  // Internet access (egress guard): current mode + the most recent decisions.
  const refreshNetwork = async () => {
    try {
      const [st, log] = await Promise.all([
        apiGet<EgressStatus>('/api/egress/status'),
        apiGet<{ events: EgressEvent[] }>('/api/egress/log?limit=8'),
      ]);
      setOffline(st.offline);
      setNetEvents(log.events);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    refreshNetwork();
    const id = window.setInterval(refreshNetwork, 10000);
    return () => window.clearInterval(id);
  }, []);

  const refreshUnlock = async () => {
    try { setUnlock(await apiGet<UnlockStatus>('/api/unlock/status')); } catch (err) { console.error(err); }
  };
  useEffect(() => { refreshUnlock(); }, []);

  const say = (msg: string) => { setStatus(msg); setTimeout(() => setStatus(''), 4000); };
  const errText = (err: unknown) => (err instanceof ApiError ? err.message : 'Could not reach the backend.');

  const handleAutoLock = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    try {
      const r = await apiPost<{ auto_lock_minutes: number }>('/api/unlock/auto-lock', { minutes: Number(e.target.value), pin: securityPin || undefined });
      say(r.auto_lock_minutes ? `Sentinel will lock after ${r.auto_lock_minutes} idle minutes.` : 'Auto-lock turned off.');
      refreshUnlock();
    } catch (err) { say(errText(err)); }
  };

  const handleChangePin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pinNew !== pinNew2) { say('The two new PINs are different.'); return; }
    try {
      await apiPost('/api/unlock/change-pin', { current_pin: pinCurrent, new_pin: pinNew });
      setPinCurrent(''); setPinNew(''); setPinNew2('');
      say('PIN changed. Your recovery key still works.');
    } catch (err) { say(errText(err)); }
  };

  const handleDeleteOldDb = async () => {
    if (!window.confirm('Delete the old unencrypted copies listed here? Your encrypted data stays. This cannot be undone.')) return;
    try {
      const r = await apiPost<{ deleted: string[]; kept: { file: string; why: string }[] }>('/api/unlock/delete-old-db', { pin: securityPin || undefined });
      const kept = r.kept.map(k => `${k.file} (kept: ${k.why})`).join('; ');
      say(`Deleted: ${r.deleted.length ? r.deleted.join(', ') : 'nothing'}.${kept ? ' ' + kept : ''}`);
      refreshUnlock();
    } catch (err) { say(errText(err)); }
  };

  const refreshData = async () => {
    try {
      const [sec, ret] = await Promise.all([
        apiGet<{ secrets: { name: string; updated_at: string }[] }>('/api/secrets'),
        apiGet<{ retention_chat_days: number; retention_research_days: number }>('/api/retention'),
      ]);
      setSecretNames(sec.secrets);
      setChatDays(ret.retention_chat_days);
      setResearchDays(ret.retention_research_days);
    } catch (err) { console.error(err); }
  };
  useEffect(() => { refreshData(); }, []);

  const pinArg = () => ({ pin: securityPin || undefined });

  const handleSaveSecret = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiPost('/api/secrets', { name: secretName, value: secretValue, ...pinArg() });
      setSecretName(''); setSecretValue('');
      say('Secret saved. It is stored encrypted and never shown again.');
      refreshData();
    } catch (err) { say(errText(err)); }
  };

  const handleDeleteSecret = async (name: string) => {
    if (!window.confirm(`Delete the secret "${name}"?`)) return;
    try {
      await apiPost(`/api/secrets/${encodeURIComponent(name)}/delete`, pinArg());
      say(`Secret "${name}" deleted.`);
      refreshData();
    } catch (err) { say(errText(err)); }
  };

  const handleForgetAll = async () => {
    if (!window.confirm('Forget ALL remembered facts? This cannot be undone.')) return;
    try {
      const r = await apiPost<{ forgotten: number }>('/api/memory/forget-all', pinArg());
      say(`Forgot ${r.forgotten} memories.`);
    } catch (err) { say(errText(err)); }
  };

  const handleDeleteChats = async () => {
    if (!window.confirm('Delete ALL chat history? This cannot be undone.')) return;
    try {
      const r = await apiPost<{ deleted: number }>('/api/chats/delete-all', pinArg());
      say(`Deleted ${r.deleted} chat sessions.`);
    } catch (err) { say(errText(err)); }
  };

  const handleSaveRetention = async () => {
    try {
      const r = await apiPost<{ removed: { chats: number; research: number } }>('/api/retention',
        { chat_days: chatDays, research_days: researchDays, ...pinArg() });
      say(`Retention saved. Removed now: ${r.removed.chats} old chats, ${r.removed.research} old research entries.`);
    } catch (err) { say(errText(err)); }
  };

  const handleNewRecoveryKey = async () => {
    if (!window.confirm('Create a new recovery key? The old one will stop working.')) return;
    try {
      const r = await apiPost<{ recovery_key: string }>('/api/unlock/new-recovery-key', { pin: securityPin || undefined });
      setNewRecoveryKey(r.recovery_key);
      say('New recovery key created. Save it now; it is shown only once.');
    } catch (err) { say(errText(err)); }
  };

  const handleOfflineChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const enabled = e.target.checked;
    try {
      const st = await apiPost<EgressStatus>('/api/egress/offline', { enabled });
      setOffline(st.offline);
      setStatus(st.offline ? 'Offline mode on: nothing leaves this PC.' : 'Offline mode off: approved tools may use the internet.');
      setTimeout(() => setStatus(''), 3000);
    } catch (err) {
      console.error(err);
      setStatus('Could not change Offline mode.');
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setStatus('');
    
    try {
      const { port, token } = await getAuthInfo();
      const headers = {
        'Content-Type': 'application/json',
        'X-Sentinel-Session': token
      };

      const res = await fetch(`http://127.0.0.1:${port}/settings`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ system_prompt: systemPrompt })
      });

      if (res.ok) {
        setStatus('Settings saved successfully!');
      } else {
        setStatus('Failed to save settings.');
      }
    } catch (err) {
      setStatus('Network Error.');
      console.error(err);
    } finally {
      setSaving(false);
      setTimeout(() => setStatus(''), 3000);
    }
  };

  const handleModelChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newModel = e.target.value;
    setActiveModel(newModel);
    try {
      const { port, token } = await getAuthInfo();
      await fetch(`http://127.0.0.1:${port}/api/models/select`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Sentinel-Session': token
        },
        body: JSON.stringify({ profile_id: newModel })
      });
      setStatus('Model profile updated.');
      setTimeout(() => setStatus(''), 3000);
    } catch (e) {
      console.error(e);
    }
  };

  const handleClearMemory = async () => {
    if (!window.confirm("Clear your web research history? This cannot be undone.")) return;
    
    try {
      const { port, token } = await getAuthInfo();
      const res = await fetch(`http://127.0.0.1:${port}/api/research/clear`, {
        method: 'POST',
        headers: { 'X-Sentinel-Session': token }
      });
      if (res.ok) {
        setStatus('Research history cleared.');
        setTimeout(() => setStatus(''), 3000);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleLocalOnlyChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const isLocal = e.target.checked;
    setLocalOnly(isLocal);
    try {
      const { port, token } = await getAuthInfo();
      await fetch(`http://127.0.0.1:${port}/api/research/mode`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Sentinel-Session': token
        },
        body: JSON.stringify({ local_only: isLocal })
      });
      setStatus(`Local-Only Mode ${isLocal ? 'Enabled' : 'Disabled'}.`);
      setTimeout(() => setStatus(''), 3000);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="settings-container glass-panel">
      <h2>Sentinel Configuration</h2>
      
      <div className="settings-section">
        <h3>Model Selection</h3>
        <p className="settings-desc">Choose the AI model profile to use for processing.</p>
        <select value={activeModel} onChange={handleModelChange} className="settings-dropdown">
          {models.map(m => (
            <option key={m.id} value={m.id}>{m.name} ({m.description})</option>
          ))}
        </select>
      </div>

      <div className="settings-section">
        <h3>Privacy & Constraints</h3>
        <label className="settings-toggle">
          <input 
            type="checkbox" 
            checked={localOnly} 
            onChange={handleLocalOnlyChange} 
          />
          <span className="toggle-label">Strict Local-Only Mode (Disables Web/Network Skills)</span>
        </label>
        
        <label className="settings-toggle" style={{marginTop: '0.75rem'}}>
          <input
            id="offline-mode"
            type="checkbox"
            checked={offline}
            onChange={handleOfflineChange}
          />
          <span className="toggle-label">Offline mode: block all internet access (web search, market data, everything)</span>
        </label>

        <div className="net-activity">
          <p className="settings-desc" style={{marginTop: '1rem', marginBottom: '0.4rem'}}>Recent internet activity</p>
          {netEvents.length === 0 ? (
            <p className="settings-desc" style={{fontSize: '0.8rem'}}>Nothing has gone online this session.</p>
          ) : (
            <ul className="net-activity-list">
              {netEvents.map((ev, i) => (
                <li key={`${ev.ts}-${i}`} className={ev.decision}>
                  <span className="net-host">{ev.host || '(unknown host)'}</span>
                  <span className="net-meta">
                    {ev.decision === 'blocked' ? 'Blocked' : `Allowed${ev.status ? ` · HTTP ${ev.status}` : ''}`}
                    {ev.tool ? ` · ${ev.tool}` : ''} · {timeAgo(ev.ts)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="retention-grid">
          <label className="settings-desc" htmlFor="keep-chats">Keep chats for</label>
          <select id="keep-chats" className="settings-dropdown" value={chatDays} onChange={e => setChatDays(Number(e.target.value))}>
            {[30, 90, 180, 365].map(d => <option key={d} value={d}>{d} days</option>)}
            <option value={0}>Forever</option>
          </select>
          <label className="settings-desc" htmlFor="keep-research">Keep research history for</label>
          <select id="keep-research" className="settings-dropdown" value={researchDays} onChange={e => setResearchDays(Number(e.target.value))}>
            {[7, 30, 90, 365].map(d => <option key={d} value={d}>{d} days</option>)}
            <option value={0}>Forever</option>
          </select>
          <button type="button" className="save-btn" onClick={handleSaveRetention}>Save retention</button>
          <p className="settings-desc" style={{ fontSize: '0.8rem' }}>Remembered facts are kept until you forget them. Uses the PIN field in Security if needed.</p>
        </div>

        <div className="danger-row">
          <button type="button" className="save-btn" style={{ backgroundColor: 'var(--accent-red)' }} onClick={handleForgetAll}>Forget all memories</button>
          <button type="button" className="save-btn" style={{ backgroundColor: 'var(--accent-red)' }} onClick={handleDeleteChats}>Delete all chat history</button>
        </div>

        <div style={{marginTop: '1rem'}}>
          <button className="save-btn" style={{backgroundColor: 'var(--accent-red)'}} onClick={handleClearMemory}>
            Clear Research History
          </button>
          <p className="settings-desc" style={{marginTop: '0.5rem', fontSize: '0.8rem'}}>
            Deletes the list of web searches Sentinel has made. It does not touch remembered facts.
          </p>
        </div>
      </div>

      <div className="settings-section">
        <h3>Security</h3>
        <p className="settings-desc">
          Your memories, chats and settings are encrypted on this PC. {unlock?.windows_bound ? 'The PIN only works together with your Windows login. ' : ''}
          Actions of risk level {unlock?.pin_required_tier ?? 3} and above (changing files, launching programs, deleting) ask for your PIN again if you haven't typed it in the last 5 minutes.
        </p>
        <label className="settings-desc" htmlFor="security-pin" style={{ display: 'block', marginTop: '0.5rem' }}>
          Your PIN (needed for the changes below if you haven't typed it in the last 5 minutes)
        </label>
        <input id="security-pin" type="password" autoComplete="current-password" className="settings-dropdown" style={{ maxWidth: '360px' }}
               value={securityPin} onChange={e => setSecurityPin(e.target.value)} />
        <label className="settings-desc" htmlFor="auto-lock" style={{ display: 'block', marginTop: '0.5rem' }}>Lock automatically after</label>
        <select id="auto-lock" className="settings-dropdown" value={String(unlock?.auto_lock_minutes ?? 15)} onChange={handleAutoLock}>
          {[5, 15, 30, 60, 120].map(m => <option key={m} value={m}>{m} idle minutes</option>)}
          <option value="0">Never</option>
        </select>

        <form onSubmit={handleChangePin} style={{ display: 'grid', gap: '0.5rem', marginTop: '1rem', maxWidth: '360px' }}>
          <span className="settings-desc">Change PIN</span>
          <input id="pin-current" type="password" placeholder="Current PIN" autoComplete="current-password" className="settings-dropdown" value={pinCurrent} onChange={e => setPinCurrent(e.target.value)} />
          <input id="pin-new" type="password" placeholder={`New PIN (${unlock?.min_pin_length ?? 6}+ characters)`} autoComplete="new-password" className="settings-dropdown" value={pinNew} onChange={e => setPinNew(e.target.value)} />
          <input id="pin-new2" type="password" placeholder="New PIN again" autoComplete="new-password" className="settings-dropdown" value={pinNew2} onChange={e => setPinNew2(e.target.value)} />
          <button type="submit" className="save-btn" disabled={!pinCurrent || !pinNew}>Change PIN</button>
        </form>

        <form onSubmit={handleSaveSecret} className="secrets-box">
          <span className="settings-desc">Secrets vault: API keys and passwords for future integrations. Stored encrypted and never shown again after saving.</span>
          {secretNames.length > 0 && (
            <ul className="secret-list">
              {secretNames.map(sn => (
                <li key={sn.name}><code>{sn.name}</code>
                  <button type="button" className="link-btn" onClick={() => handleDeleteSecret(sn.name)}>Delete</button>
                </li>
              ))}
            </ul>
          )}
          <input id="secret-name" placeholder="Name, e.g. calendar.api_key" className="settings-dropdown" value={secretName} onChange={e => setSecretName(e.target.value)} />
          <input id="secret-value" type="password" placeholder="Value" autoComplete="off" className="settings-dropdown" value={secretValue} onChange={e => setSecretValue(e.target.value)} />
          <button type="submit" className="save-btn" disabled={!secretName || !secretValue}>Save secret</button>
        </form>

        <div style={{ marginTop: '1rem', display: 'grid', gap: '0.5rem', maxWidth: '480px' }}>
          <button type="button" className="save-btn" onClick={handleNewRecoveryKey}>Create a new recovery key</button>
          {newRecoveryKey && (
            <div className="recovery-key-box">
              <p>Your new recovery key (shown once; the old one no longer works):</p>
              <code>{newRecoveryKey}</code>
            </div>
          )}
        </div>

        {unlock?.old_unencrypted_db && (
          <div className="old-db-warning">
            <p><strong>Old unencrypted copies of your data are still on this PC:</strong></p>
            <ul>{(unlock.old_unencrypted_files ?? []).map(f => <li key={f}><code>{f}</code></li>)}</ul>
            <p>Their contents are already in the encrypted database. Files are only deleted if they're exactly what was moved in.</p>
            <button type="button" className="save-btn" style={{ backgroundColor: 'var(--accent-red)' }} onClick={handleDeleteOldDb}>Delete old unencrypted copies</button>
          </div>
        )}
      </div>

      <div className="settings-section">
        <h3>Personality & Core Instructions (System Prompt)</h3>
        <p className="settings-desc">
          This prompt dictates how Sentinel behaves. It is injected into the AI's context window before every conversation.
        </p>
        
        <textarea 
          className="prompt-editor"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={10}
        />
        
        <div className="settings-actions">
          <span className="status-msg">{status}</span>
          <button 
            className="save-btn" 
            onClick={handleSave} 
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsPanel;
