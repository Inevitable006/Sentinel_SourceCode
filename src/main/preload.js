const { contextBridge, ipcRenderer } = require('electron');

// ─── Secure API Bridge ──────────────────────────────────────────
// Exposes the smallest possible API to the renderer (which runs sandboxed).
// The UI talks to the Python backend over HTTP/WebSocket using the session
// token; it gets no direct access to the OS through this bridge.
//
// Removed in Phase 0 (unused by the UI, each one widened the attack surface):
// system/process control, file-system access, screen capture, config writes,
// the legacy JS AI engine and its memory subsystem.

contextBridge.exposeInMainWorld('sentinel', {
  // ── Window Controls ──
  window: {
    minimize: () => ipcRenderer.send('window-minimize'),
    maximize: () => ipcRenderer.send('window-maximize'),
    close: () => ipcRenderer.send('window-close'),
    isMaximized: () => ipcRenderer.invoke('window-is-maximized')
  },

  // ── Authentication ──
  auth: {
    getSessionToken: () => ipcRenderer.invoke('auth-get-session-token'),
    getBackendPort: () => ipcRenderer.invoke('auth-get-backend-port')
  },

  // ── Backend lifecycle (receive-only) ──
  backend: {
    // Called once if the backend could not be (re)started and Sentinel entered Safe Mode.
    onFatalError: (callback) => {
      const handler = () => callback();
      ipcRenderer.on('backend-fatal-error', handler);
      return () => ipcRenderer.removeListener('backend-fatal-error', handler);
    },
    // Called when Windows lock / sleep locked Sentinel, so the UI re-checks immediately.
    onLocked: (callback) => {
      const handler = () => callback();
      ipcRenderer.on('sentinel-locked', handler);
      return () => ipcRenderer.removeListener('sentinel-locked', handler);
    }
  }
});
