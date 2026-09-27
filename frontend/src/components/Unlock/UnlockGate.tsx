import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, LOCK_EVENT, type UnlockStatus } from '../../lib/backend';
import UnlockScreen from './UnlockScreen';
import './Unlock.css';

// Shows the app only while Sentinel is unlocked. While locked, nothing behind this gate is
// mounted, so no chat connection or data request is even attempted.
const UnlockGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [status, setStatus] = useState<UnlockStatus | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [holdOpen, setHoldOpen] = useState(false); // keeps the setup screen up while the recovery key is shown

  const refresh = useCallback(async () => {
    try {
      setStatus(await apiGet<UnlockStatus>('/api/unlock/status'));
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 4000);
    window.addEventListener(LOCK_EVENT, refresh);
    return () => {
      window.clearInterval(id);
      window.removeEventListener(LOCK_EVENT, refresh);
    };
  }, [refresh]);

  if (!status) {
    return (
      <div className="unlock-screen">
        <div className="unlock-card">
          <p className="unlock-muted">{unreachable ? 'Waiting for the Sentinel backend to start…' : 'Starting…'}</p>
        </div>
      </div>
    );
  }
  if (status.state === 'unlocked' && !holdOpen) return <>{children}</>;
  return <UnlockScreen status={status} onChanged={refresh} setHoldOpen={setHoldOpen} />;
};

export default UnlockGate;
