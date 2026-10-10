import React, { useState } from 'react';
import { backendInfo } from '../../lib/backend';

type Check = { manifest: { created: string }; counts: Record<string, number> };

// Restore from an encrypted .sentinelbak file. Works only while Sentinel is locked.
// The backup is checked with your PIN/recovery key before anything is replaced; current data is kept aside.
const RestorePanel: React.FC<{ onDone: () => void }> = ({ onDone }) => {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<'recovery' | 'pin'>('recovery');
  const [secret, setSecret] = useState('');
  const [checked, setChecked] = useState<Check | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const send = async (path: 'verify' | 'restore') => {
    if (!file) return;
    setBusy(true); setMessage('');
    try {
      const { port, token } = await backendInfo();
      const res = await fetch(`http://127.0.0.1:${port}/api/backup/${path}`, {
        method: 'POST', body: file,
        headers: { 'X-Sentinel-Session': token, 'Content-Type': 'application/octet-stream',
                   'X-Sentinel-Restore-Kind': kind, 'X-Sentinel-Restore-Secret': secret },
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(String(body.detail || 'That did not work.'));
      if (path === 'verify') setChecked(body);
      else { setMessage(`Restored. ${body.next}`); setSecret(''); setChecked(null); onDone(); }
    } catch (e) { setMessage(e instanceof Error ? e.message : 'That did not work.'); }
    finally { setBusy(false); }
  };

  if (!open) return <button type="button" className="unlock-link" onClick={() => setOpen(true)}>Restore from a backup…</button>;
  return (
    <div className="unlock-card wide" style={{ marginTop: '1rem' }}>
      <h2>Restore from a backup</h2>
      <p className="unlock-muted">On this PC you can use your PIN. On a new PC use your recovery key. Your current data is kept in a "pre-restore" folder, not deleted.</p>
      <input type="file" accept=".sentinelbak" onChange={e => { setFile(e.target.files?.[0] ?? null); setChecked(null); }} />
      <select value={kind} onChange={e => { setKind(e.target.value as 'recovery' | 'pin'); setChecked(null); }}>
        <option value="recovery">Recovery key</option><option value="pin">PIN</option>
      </select>
      <input type="password" autoComplete="off" placeholder={kind === 'pin' ? 'PIN' : 'XXXX-XXXX-…'} value={secret}
             onChange={e => { setSecret(e.target.value); setChecked(null); }} />
      {checked && (
        <p>Backup from {checked.manifest.created}: {Object.entries(checked.counts).map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(', ')}.
          Restoring replaces what is on this PC now.</p>
      )}
      {message && <p className="unlock-error" role="alert">{message}</p>}
      {!checked
        ? <button type="button" className="unlock-primary" disabled={busy || !file || !secret} onClick={() => send('verify')}>{busy ? 'Checking…' : 'Check backup'}</button>
        : <button type="button" className="unlock-primary" disabled={busy} onClick={() => send('restore')}>{busy ? 'Restoring…' : 'Restore this backup'}</button>}
      <button type="button" className="unlock-link" onClick={() => setOpen(false)}>Cancel</button>
    </div>
  );
};

export default RestorePanel;
