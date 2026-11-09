import React, { useCallback, useEffect, useState, useRef } from 'react';
import { apiGet, apiPost, backendInfo, ApiError } from '../../lib/backend';

type Backup = { name: string; size: number; created: string };
type PendingOp = { type: 'create' } | { type: 'save'; name: string };

// Create an encrypted backup and save a copy anywhere (USB drive, another disk, cloud folder).
const BackupSettings: React.FC = () => {
  const [backups, setBackups] = useState<Backup[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pin, setPin] = useState('');
  const [needPin, setNeedPin] = useState(false);
  const [pendingOp, setPendingOp] = useState<PendingOp | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);

  const loadRequestIdRef = useRef(0);
  const isMountedRef = useRef(true);

  const load = useCallback(() => {
    const reqId = ++loadRequestIdRef.current;
    setLoading(true);
    setLoadError(null);
    apiGet<{ backups: Backup[] }>('/api/backup')
      .then(r => {
        if (loadRequestIdRef.current === reqId) {
          setBackups(r.backups);
          setLoadError(null);
          setLoading(false);
        }
      })
      .catch(e => {
        if (loadRequestIdRef.current === reqId) {
          setBackups(null); // Clear stale backup data on failure
          const errText = e instanceof Error ? e.message : 'Could not load backup list.';
          setLoadError(errText);
          setMessage(errText);
          setLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    load();
    return () => {
      isMountedRef.current = false;
      loadRequestIdRef.current += 1;
    };
  }, [load]);

  const executeOp = useCallback(async (op: PendingOp, pinToUse?: string) => {
    if (busy) return;
    setBusy(true);
    if (op.type === 'save') {
      setDownloading(op.name);
    }
    try {
      if (op.type === 'create') {
        const r = await apiPost<{ name: string; size: number }>('/api/backup/create', { pin: pinToUse || undefined });
        if (isMountedRef.current) {
          setMessage(`Backup created (${(r.size / 1024 / 1024).toFixed(1)} MB). Save a copy somewhere other than this PC.`);
          setNeedPin(false);
          setPin('');
          setPendingOp(null);
          load();
        }
      } else if (op.type === 'save') {
        const { port, token } = await backendInfo();
        const res = await fetch(`http://127.0.0.1:${port}/api/backup/download/${encodeURIComponent(op.name)}`, {
          method: 'POST',
          headers: { 'X-Sentinel-Session': token, 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: pinToUse || undefined }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new ApiError(res.status, body.detail ?? null);
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = op.name;
        a.click();
        // Delay revocation so Electron/Chromium download manager completes reading stream
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        if (isMountedRef.current) {
          setMessage('Choose where to save the copy (for example a USB drive).');
          setNeedPin(false);
          setPin('');
          setPendingOp(null);
        }
      }
    } catch (e) {
      if (isMountedRef.current) {
        if (e instanceof ApiError && e.code === 'pin_required') {
          setPendingOp(op);
          setNeedPin(true);
          setMessage(e.message || 'Owner PIN required.');
        } else {
          setMessage(e instanceof Error ? e.message : 'That did not work.');
        }
      }
    } finally {
      if (isMountedRef.current) {
        setBusy(false);
        if (op.type === 'save') {
          setDownloading(null);
        }
      }
    }
  }, [busy, load]);

  const create = () => {
    void executeOp({ type: 'create' }, pin || undefined);
  };

  const save = (name: string) => {
    void executeOp({ type: 'save', name }, pin || undefined);
  };

  const handlePinSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!busy && pin.length > 0 && pendingOp) {
      void executeOp(pendingOp, pin);
    }
  };

  const handleCancelPin = () => {
    setNeedPin(false);
    setPin('');
    setPendingOp(null);
    setMessage('Operation cancelled.');
  };

  return (
    <div className="settings-section">
      <h3>Backup</h3>
      <p className="settings-desc">
        A backup holds your chats, memories, tasks, portfolio and settings, still encrypted. It opens only with your PIN on this PC, or your recovery key on any PC. Keep your recovery key safe: without it a backup cannot be opened elsewhere.
      </p>

      {needPin && (
        <form
          style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', margin: '0.5rem 0', flexWrap: 'wrap' }}
          onSubmit={handlePinSubmit}
        >
          <label htmlFor="backup-pin-input" className="settings-desc" style={{ margin: 0 }}>
            Owner PIN
          </label>
          <input
            id="backup-pin-input"
            type="password"
            placeholder="PIN"
            autoComplete="current-password"
            value={pin}
            disabled={busy}
            autoFocus
            aria-label="Owner PIN for backup"
            onChange={e => setPin(e.target.value)}
          />
          <button type="submit" disabled={busy || pin.length === 0}>
            {busy ? 'Verifying…' : 'Confirm PIN'}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={handleCancelPin}
          >
            Cancel
          </button>
        </form>
      )}

      <button type="button" disabled={busy || downloading !== null} onClick={create}>
        {busy && !downloading ? 'Working…' : 'Create backup now'}
      </button>

      {loading && <p className="settings-desc" role="status">Loading backups…</p>}
      {!loading && loadError && (
        <p className="settings-desc" role="alert">
          Could not load backups: {loadError}
        </p>
      )}
      {!loading && !loadError && backups && backups.length === 0 && (
        <p className="settings-desc">No backups created yet.</p>
      )}

      {!loading && !loadError && backups && backups.length > 0 && (
        <ul className="settings-desc" aria-label="Existing backups">
          {backups.map(b => (
            <li key={b.name} style={{ margin: '0.25rem 0' }}>
              {b.created.replace('T', ' ')} · {(b.size / 1024 / 1024).toFixed(1)} MB
              <button
                type="button"
                style={{ marginLeft: '0.5rem' }}
                disabled={busy || downloading !== null}
                onClick={() => save(b.name)}
                aria-label={`Save a copy of backup from ${b.created}`}
              >
                {downloading === b.name ? 'Saving copy…' : 'Save a copy…'}
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="settings-desc">
        To restore: lock Sentinel, then choose "Restore from a backup" on the lock screen. The last 5 backups are kept on this PC.
      </p>
      {message && <p className="settings-desc" role="status" aria-live="polite">{message}</p>}
    </div>
  );
};

export default BackupSettings;
