import React, { useEffect, useState } from 'react';
import { Lock, KeyRound, ShieldCheck, Copy, Check } from 'lucide-react';
import { apiPost, ApiError, type UnlockStatus } from '../../lib/backend';

type Migration = {
  migrated?: boolean;
  rows_copied?: number;
  test_rows_removed?: { test_memories: number; test_threads: number; empty_threads: number };
};

type Props = { status: UnlockStatus; onChanged: () => void; setHoldOpen: (hold: boolean) => void };

const UnlockScreen: React.FC<Props> = ({ status, onChanged, setHoldOpen }) => {
  const [mode, setMode] = useState<'pin' | 'recover'>('pin');
  const [pin, setPin] = useState('');
  const [pin2, setPin2] = useState('');
  const [recoveryInput, setRecoveryInput] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(status.retry_after || 0);
  const [recoveryKey, setRecoveryKey] = useState('');
  const [migration, setMigration] = useState<Migration | null>(null);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => { setWait(status.retry_after || 0); }, [status.retry_after]);
  useEffect(() => {
    if (wait <= 0) return;
    const id = window.setTimeout(() => setWait(w => Math.max(0, w - 1)), 1000);
    return () => window.clearTimeout(id);
  }, [wait]);

  const fail = (e: unknown) => {
    if (e instanceof ApiError) {
      if (e.status === 429) setWait(e.retryAfter || 30);
      setError(e.message);
    } else {
      setError('Could not reach the Sentinel backend.');
    }
  };

  const min = status.min_pin_length || 6;

  const doSetup = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setError('');
    if (pin !== pin2) { setError('The two PINs are different.'); return; }
    setBusy(true);
    setHoldOpen(true);
    try {
      const r = await apiPost<{ recovery_key: string; migration: Migration }>('/api/unlock/setup', { pin });
      setRecoveryKey(r.recovery_key);
      setMigration(r.migration);
      setPin(''); setPin2('');
    } catch (e) {
      setHoldOpen(false);
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const doUnlock = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setError('');
    setBusy(true);
    try {
      await apiPost('/api/unlock', { pin });
      setPin('');
      onChanged();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const doRecover = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setError('');
    if (pin !== pin2) { setError('The two new PINs are different.'); return; }
    setBusy(true);
    try {
      await apiPost('/api/unlock/recover', { recovery_key: recoveryInput, new_pin: pin });
      setPin(''); setPin2(''); setRecoveryInput('');
      onChanged();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const copyKey = async () => {
    try {
      await navigator.clipboard.writeText(recoveryKey);
      setCopied(true);
    } catch {
      setCopied(false);
      setError('Copy was blocked. Select the key and copy it by hand.');
    }
  };

  const finishSetup = () => {
    setRecoveryKey('');
    setHoldOpen(false);
    onChanged();
  };

  // 1) Right after setup: show the recovery key once.
  if (recoveryKey) {
    const removed = migration?.test_rows_removed;
    return (
      <div className="unlock-screen">
        <div className="unlock-card wide">
          <ShieldCheck size={28} className="unlock-icon ok" />
          <h1>Save your recovery key</h1>
          <p>If you forget your PIN, or Windows is reinstalled, this key is the only way back into your data. It is shown only this once.</p>
          <div className="recovery-key" aria-label="Recovery key">{recoveryKey}</div>
          <button type="button" className="unlock-secondary" onClick={copyKey}>
            {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? 'Copied' : 'Copy key'}
          </button>
          <p className="unlock-muted">Keep it on paper or in a password manager, not in a file next to Sentinel and never in a chat.</p>
          {migration?.migrated && (
            <p className="unlock-note">
              Your existing memories and chats ({migration.rows_copied ?? 0} records) are now in the encrypted database.
              {removed && (removed.test_memories + removed.test_threads + removed.empty_threads) > 0 &&
                ` Leftovers from old test runs were removed: ${removed.test_memories} memories and ${removed.test_threads + removed.empty_threads} empty or test chats.`}
              {' '}The old unencrypted file stays on this PC until you delete it in Settings.
            </p>
          )}
          {error && <p className="unlock-error" role="alert">{error}</p>}
          <label className="unlock-check">
            <input id="recovery-saved" type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} />
            I've saved my recovery key somewhere safe
          </label>
          <button type="button" className="unlock-primary" disabled={!saved} onClick={finishSetup}>Open Sentinel</button>
        </div>
      </div>
    );
  }

  // 2) First run: choose a PIN.
  if (status.state === 'setup_required') {
    return (
      <div className="unlock-screen">
        <form className="unlock-card" onSubmit={doSetup}>
          <KeyRound size={28} className="unlock-icon" />
          <h1>Set up Sentinel</h1>
          <p>Choose a PIN. It encrypts your memories, chats and settings on this PC{status.windows_bound ? ', and it only works together with your Windows login' : ''}.</p>
          <label htmlFor="setup-pin">PIN ({min}+ characters; longer is stronger)</label>
          <input id="setup-pin" type="password" autoFocus autoComplete="new-password" value={pin} onChange={e => setPin(e.target.value)} />
          <label htmlFor="setup-pin2">Type it again</label>
          <input id="setup-pin2" type="password" autoComplete="new-password" value={pin2} onChange={e => setPin2(e.target.value)} />
          {error && <p className="unlock-error" role="alert">{error}</p>}
          <button type="submit" className="unlock-primary" disabled={busy || pin.length < min}>
            {busy ? 'Encrypting…' : 'Encrypt my data'}
          </button>
          <p className="unlock-muted">Nobody, including Anthropic or Google, can reset this PIN. You'll get a recovery key next.</p>
        </form>
      </div>
    );
  }

  // 3) Locked: PIN, or the recovery key.
  const waiting = wait > 0;
  return (
    <div className="unlock-screen">
      {mode === 'pin' ? (
        <form className="unlock-card" onSubmit={doUnlock}>
          <Lock size={28} className="unlock-icon" />
          <h1>Sentinel is locked</h1>
          <label htmlFor="unlock-pin">PIN</label>
          <input id="unlock-pin" type="password" autoFocus autoComplete="current-password" value={pin}
                 onChange={e => setPin(e.target.value)} disabled={waiting} />
          {error && <p className="unlock-error" role="alert">{error}</p>}
          {waiting && <p className="unlock-muted">You can try again in {wait} s.</p>}
          <button type="submit" className="unlock-primary" disabled={busy || waiting || !pin}>{busy ? 'Unlocking…' : 'Unlock'}</button>
          <button type="button" className="unlock-link" onClick={() => { setMode('recover'); setError(''); setPin(''); }}>
            Forgot your PIN? Use your recovery key
          </button>
        </form>
      ) : (
        <form className="unlock-card" onSubmit={doRecover}>
          <KeyRound size={28} className="unlock-icon" />
          <h1>Use your recovery key</h1>
          <label htmlFor="recovery-input">Recovery key</label>
          <input id="recovery-input" type="text" autoFocus spellCheck={false} placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"
                 value={recoveryInput} onChange={e => setRecoveryInput(e.target.value)} disabled={waiting} />
          <label htmlFor="recover-pin">New PIN ({min}+ characters)</label>
          <input id="recover-pin" type="password" autoComplete="new-password" value={pin} onChange={e => setPin(e.target.value)} disabled={waiting} />
          <label htmlFor="recover-pin2">Type the new PIN again</label>
          <input id="recover-pin2" type="password" autoComplete="new-password" value={pin2} onChange={e => setPin2(e.target.value)} disabled={waiting} />
          {error && <p className="unlock-error" role="alert">{error}</p>}
          {waiting && <p className="unlock-muted">You can try again in {wait} s.</p>}
          <button type="submit" className="unlock-primary" disabled={busy || waiting || !recoveryInput || pin.length < min}>
            {busy ? 'Checking…' : 'Unlock and set new PIN'}
          </button>
          <button type="button" className="unlock-link" onClick={() => { setMode('pin'); setError(''); setPin(''); setPin2(''); }}>
            Back to PIN
          </button>
        </form>
      )}
    </div>
  );
};

export default UnlockScreen;
