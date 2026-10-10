import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost, backendInfo, ApiError } from '../../lib/backend';

type Backup = { name: string; size: number; created: string };

// Create an encrypted backup and save a copy anywhere (USB drive, another disk, cloud folder).
const BackupSettings: React.FC = () => {
  const [backups, setBackups] = useState<Backup[]>([]);
  const [pin, setPin] = useState('');
  const [needPin, setNeedPin] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    apiGet<{ backups: Backup[] }>('/api/backup').then(r => setBackups(r.backups)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const withPin = async (fn: (pin?: string) => Promise<void>) => {
    setBusy(true);
    try { await fn(pin || undefined); setNeedPin(false); setPin(''); }
    catch (e) {
      if (e instanceof ApiError && e.code === 'pin_required') { setNeedPin(true); setMessage(e.message); }
      else setMessage(e instanceof Error ? e.message : 'That did not work.');
    } finally { setBusy(false); }
  };

  const create = () => withPin(async (p) => {
    const r = await apiPost<{ name: string; size: number }>('/api/backup/create', { pin: p });
    setMessage(`Backup created (${(r.size / 1024 / 1024).toFixed(1)} MB). Save a copy somewhere other than this PC.`);
    load();
  });

  const save = (name: string) => withPin(async (p) => {
    const { port, token } = await backendInfo();
    const res = await fetch(`http://127.0.0.1:${port}/api/backup/download/${encodeURIComponent(name)}`, {
      method: 'POST', headers: { 'X-Sentinel-Session': token, 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: p }) });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body.detail ?? null);
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
    setMessage('Choose where to save the copy (for example a USB drive).');
  });

  return (
    <div className="settings-section">
      <h3>Backup</h3>
      <p className="settings-desc">A backup holds your chats, memories, tasks, portfolio and settings, still encrypted. It opens only with your PIN on this PC, or your recovery key on any PC. Keep your recovery key safe: without it a backup cannot be opened elsewhere.</p>
      {needPin && <input type="password" placeholder="PIN" autoComplete="current-password" value={pin} onChange={e => setPin(e.target.value)} />}
      <button type="button" disabled={busy} onClick={create}>{busy ? 'Working…' : 'Create backup now'}</button>
      <ul className="settings-desc">
        {backups.map(b => (
          <li key={b.name}>{b.created.replace('T', ' ')} · {(b.size / 1024 / 1024).toFixed(1)} MB
            <button type="button" style={{ marginLeft: '0.5rem' }} disabled={busy} onClick={() => save(b.name)}>Save a copy…</button></li>
        ))}
      </ul>
      <p className="settings-desc">To restore: lock Sentinel, then choose "Restore from a backup" on the lock screen. The last 5 backups are kept on this PC.</p>
      <p className="settings-desc">{message}</p>
    </div>
  );
};

export default BackupSettings;
