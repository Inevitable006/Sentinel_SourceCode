const { contextBridge, ipcRenderer } = require('electron');

// ─── Secure API Bridge ──────────────────────────────────────────
// Exposes a safe, controlled API to the renderer process.
// No direct Node.js access is given to the frontend.
//
// Architecture: renderer → preload (this file) → main process
// The renderer can ONLY call methods exposed here.

contextBridge.exposeInMainWorld('sentinel', {
  // ── Window Controls ──
  window: {
    minimize: () => ipcRenderer.send('window-minimize'),
    maximize: () => ipcRenderer.send('window-maximize'),
    close: () => ipcRenderer.send('window-close'),
    isMaximized: () => ipcRenderer.invoke('window-is-maximized')
  },

  // ── System Information ──
  system: {
    getStats: () => ipcRenderer.invoke('get-system-stats'),
    getCpuTemp: () => ipcRenderer.invoke('get-cpu-temperature'),
    getProcesses: () => ipcRenderer.invoke('get-processes'),
    launchApp: (appPath) => ipcRenderer.invoke('launch-app', appPath),
    killProcess: (pid) => ipcRenderer.invoke('kill-process', pid)
  },

  // ── File System ──
  files: {
    readDirectory: (dirPath) => ipcRenderer.invoke('read-directory', dirPath),
    openFile: (filePath) => ipcRenderer.invoke('open-file', filePath)
  },

  // ── Screen Capture ──
  screen: {
    capture: (width, height) => ipcRenderer.invoke('capture-screen', width, height)
  },

  // ── AI Engine ──
  ai: {
    initialize: () => ipcRenderer.invoke('ai-initialize'),
    chat: (messages) => ipcRenderer.invoke('ai-chat', messages),
    chatStream: (messages) => ipcRenderer.invoke('ai-chat-stream', messages),
    getStatus: () => ipcRenderer.invoke('ai-status'),
    onStreamToken: (callback) => {
      ipcRenderer.on('ai-stream-token', (event, token) => callback(token));
    },
    onStreamEnd: (callback) => {
      ipcRenderer.on('ai-stream-end', () => callback());
    },
    onStreamError: (callback) => {
      ipcRenderer.on('ai-stream-error', (event, error) => callback(error));
    },
    removeStreamListeners: () => {
      ipcRenderer.removeAllListeners('ai-stream-token');
      ipcRenderer.removeAllListeners('ai-stream-end');
      ipcRenderer.removeAllListeners('ai-stream-error');
    }
  },

  // ── Core Systems (Phase 1) ──
  // These APIs expose the foundation layer to the UI
  core: {
    // System profile — hardware capabilities, tier, recommendations
    getSystemProfile: () => ipcRenderer.invoke('get-system-profile'),

    // Configuration — read/write app settings
    getConfig: (keyPath) => ipcRenderer.invoke('get-config', keyPath),
    setConfig: (keyPath, value) => ipcRenderer.invoke('set-config', keyPath, value),
    getAllConfig: () => ipcRenderer.invoke('get-all-config'),

    // Diagnostics — error stats, module health
    getErrorStats: () => ipcRenderer.invoke('get-error-stats'),
    getModuleStatus: () => ipcRenderer.invoke('get-module-status'),

    // Boot info — first run detection, tier, safe mode status
    getBootInfo: () => ipcRenderer.invoke('get-boot-info')
  },

  // ── Memory Subsystem (Phase 2) ──
  memory: {
    startConversation: () => ipcRenderer.invoke('memory-start-conversation'),
    addMessage: (role, content) => ipcRenderer.invoke('memory-add-message', role, content),
    listConversations: () => ipcRenderer.invoke('memory-list-conversations'),
    loadConversation: (id) => ipcRenderer.invoke('memory-load-conversation', id),
    getProfile: () => ipcRenderer.invoke('memory-get-profile'),
    learnFact: (topic, content) => ipcRenderer.invoke('memory-learn-fact', topic, content),
    getContext: (message) => ipcRenderer.invoke('memory-get-context', message)
  },

  // ── Authentication ──
  auth: {
    getSessionToken: () => ipcRenderer.invoke('auth-get-session-token'),
    getBackendPort: () => ipcRenderer.invoke('auth-get-backend-port')
  }
});
