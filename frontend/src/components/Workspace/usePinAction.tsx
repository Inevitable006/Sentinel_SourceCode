import { useState } from 'react';
import { ApiError } from '../../lib/backend';

// Runs an action; if the backend asks for a fresh PIN, shows a PIN field and retries with it.
export function usePinAction(setMessage: (m: string) => void) {
  const [pending, setPending] = useState<((pin: string) => Promise<void>) | null>(null);
  const [pin, setPin] = useState('');

  const run = async (action: (pin?: string) => Promise<void>) => {
    try {
      await action();
    } catch (e) {
      if (e instanceof ApiError && e.code === 'pin_required') {
        setMessage(e.message);
        setPending(() => async (p: string) => { await action(p); });
      } else {
        setMessage(e instanceof Error ? e.message : 'Something went wrong.');
      }
    }
  };

  const prompt = pending && (
    <form className="ws-pin" onSubmit={async (e) => {
      e.preventDefault();
      const act = pending; const p = pin;
      setPending(null); setPin('');
      try { await act(p); } catch (err) { setMessage(err instanceof Error ? err.message : 'PIN was not accepted.'); }
    }}>
      <label>PIN <input type="password" autoComplete="current-password" value={pin} onChange={e => setPin(e.target.value)} autoFocus /></label>
      <button type="submit" disabled={!pin}>Confirm</button>
      <button type="button" onClick={() => { setPending(null); setPin(''); setMessage('Cancelled.'); }}>Cancel</button>
    </form>
  );

  return { run, prompt };
}
