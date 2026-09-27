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
  }
});
