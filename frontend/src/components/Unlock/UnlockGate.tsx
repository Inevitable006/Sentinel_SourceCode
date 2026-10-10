import React, { useCallback, useEffect, useState } from 'react';
import { apiGet, LOCK_EVENT, onBackendFatal, onOsLocked, type UnlockStatus } from '../../lib/backend';
import UnlockScreen from './UnlockScreen';
import './Unlock.css';

// Shows the app only while Sentinel is unlocked. While locked, nothing behind this gate is
// mounted, so no chat connection or data request is even attempted.
// If the lock state cannot be confirmed (backend unreachable), private views are hidden too:
// the last known "unlocked" answer is not trusted.
const UnlockGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [status, setStatus] = useState<UnlockStatus | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [fatal, setFatal] = useState(false);
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
    const stopFatal = onBackendFatal(() => setFatal(true));
    const stopOsLock = onOsLocked(refresh);
    return () => {
      window.clearInterval(id);
      window.removeEventListener(LOCK_EVENT, refresh);
      stopFatal();
      stopOsLock();
    };
  }, [refresh]);

  if (fatal) {
    return (
      <div className="unlock-screen">
        <div className="unlock-card">
          <p>The Sentinel backend stopped and could not be restarted. Sentinel is in Safe Mode.</p>
          <p className="unlock-muted">Close and reopen Sentinel. If this keeps happening, check the logs in the Sentinel data folder.</p>
        </div>
      </div>
    );
  }
  if (!status || unreachable) {
    return (
      <div className="unlock-screen">
        <div className="unlock-card">
          <p className="unlock-muted">
            {!status ? (unreachable ? 'Waiting for the Sentinel backend to start…' : 'Starting…')
              : 'Lost contact with the Sentinel backend. Your data stays hidden until the connection returns.'}
          </p>
        </div>
      </div>
    );
  }
  if (status.state === 'unlocked' && !holdOpen) return <>{children}</>;
  return <UnlockScreen status={status} onChanged={refresh} setHoldOpen={setHoldOpen} />;
};

export default UnlockGate;
