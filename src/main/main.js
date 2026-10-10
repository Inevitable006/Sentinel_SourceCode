// Bypass corporate proxy SSL certificate interception
// Required for downloading AI models from HuggingFace behind corporate firewalls
// process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'; // REMOVED for Security

const { app, BrowserWindow, ipcMain, globalShortcut, Tray, Menu, nativeImage, dialog, session } = require('electron');
const path = require('path');
const { fileURLToPath } = require('url');

// ─── Trusted UI location ─────────────────────────────────────────
// The only page allowed in the app window, and the only page allowed to
// ask for the backend session token.
const IS_DEV = process.argv.includes('--dev');
const DEV_ORIGIN = 'http://localhost:5173';
const APP_INDEX_PATH = path.resolve(__dirname, '../../frontend/dist/index.html');

function isAppUrl(url) {
  try {
    const u = new URL(url);
    if (IS_DEV) return u.origin === DEV_ORIGIN;
    if (u.protocol !== 'file:') return false;
    return path.resolve(fileURLToPath(u)).toLowerCase() === APP_INDEX_PATH.toLowerCase();
  } catch {
    return false;
  }
}

function isTrustedSender(event) {
  return isAppUrl(event?.senderFrame?.url || '');
}

// ─── Core Systems ────────────────────────────────────────────────
// Import SENTINEL's foundation layer (Phase 1)
const { appPaths } = require('./core/app-paths');
const { logger } = require('./core/logger');
const { configManager } = require('./core/config-manager');
const { systemProfiler } = require('./core/system-profiler');
const { moduleManager } = require('./core/module-manager');
// AI/Memory imports temporarily removed for Phase 1 Safety
const { errorHandler } = require('./core/error-handler');

let mainWindow = null;
let tray = null;
let isQuitting = false;

// ─── Boot Sequence ───────────────────────────────────────────────
// SENTINEL boots in a specific order to ensure all dependencies are met.
// This is the "spine" of the application — everything branches from here.

async function bootSentinel() {
  const bootStart = performance.now();

  // STEP 1: Create directory structure
  // Must happen first — everything else writes to these directories
  console.log('[SENTINEL] Step 1/6: Creating directory structure...');
  const dirsCreated = appPaths.ensureDirectories();
  if (!dirsCreated) {
    console.error('[SENTINEL] FATAL: Could not create data directories');
    dialog.showErrorBox('SENTINEL — Fatal Error',
      'Could not create application data directories.\n' +
      'Please check disk permissions and try again.');
    app.quit();
    return;
  }

  // STEP 2: Initialize logger
  // Must happen second — all subsequent steps use logging
  console.log('[SENTINEL] Step 2/6: Starting logger...');
  logger.initialize();
  logger.info('system', '═══════════════════════════════════════════════');
  logger.info('system', 'SENTINEL boot sequence initiated', {
    version: app.getVersion?.() || '1.0.0',
    platform: process.platform,
    arch: process.arch,
    electron: process.versions.electron,
    node: process.versions.node
  });

  // STEP 3: Initialize error handler
  // Must happen before any complex operations
  console.log('[SENTINEL] Step 3/6: Installing error handlers...');
  errorHandler.initialize();

  // Check for previous crash
  if (appPaths.didCrash()) {
    logger.warn('system', 'Previous session may have crashed — performing cautious startup');
  }

  // STEP 4: Load configuration
  console.log('[SENTINEL] Step 4/6: Loading configuration...');
  errorHandler.wrapSync(
    () => configManager.initialize(),
    { category: 'system', operation: 'Config initialization', fallback: null }
  );

  const isFirstRun = appPaths.isFirstRun() || configManager.get('firstRunDate') === null;
  if (isFirstRun) {
    logger.info('system', '🎉 First run detected — welcome to SENTINEL!');
  }

  // STEP 5: Profile system hardware
  console.log('[SENTINEL] Step 5/6: Profiling system hardware...');
  const profile = await errorHandler.wrap(
    () => systemProfiler.profile_system(),
    { category: 'system', operation: 'System profiling', retry: true, fallback: null }
  );

  if (profile) {
    // Store profile in config
    configManager.set('systemProfile', systemProfiler.getSummary());

    // Apply UI recommendations based on hardware
    const uiRec = systemProfiler.getUIRecommendation();
    if (uiRec) {
      configManager.set('ui.animationLevel', uiRec.animationLevel);
      configManager.set('monitoring.updateIntervalMs', uiRec.monitoringIntervalMs);
    }

    logger.info('system', `Hardware tier: ${profile.tier.toUpperCase()}`, systemProfiler.getSummary());
  }

  // STEP 6: Initialize memory subsystems (Disabled for Phase 1)
  console.log('[SENTINEL] Step 6/7: Memory subsystems deferred to Python backend');
  // STEP 7: Initialize plugin subsystem & evolution loop (Disabled for Phase 1)
  console.log('[SENTINEL] Step 7/8: Plugin subsystems deferred to Python backend');

  // STEP 7.5: Spawn Python AI Backend with Bounded Retry
  console.log('[SENTINEL] Step 7.5/8: Spawning Python AI Backend...');
  const { spawn } = require('child_process');
  const crypto = require('crypto');

  // Generate a cryptographically secure, single-use session token for this boot
  global.SENTINEL_SESSION_TOKEN = crypto.randomBytes(32).toString('hex');
  logger.info('system', 'Generated ephemeral session token for backend authentication');

  global.SENTINEL_BACKEND_PORT = process.env.SENTINEL_BACKEND_PORT || 8000;
  process.env.SENTINEL_BACKEND_PORT = global.SENTINEL_BACKEND_PORT;

  // Python runtime: the installed app uses its own portable runtime (resources/python, built by
  // tools/build_runtime.ps1); a development checkout uses backend/.venv. Never a machine-specific path.
  const fs = require('fs');
  const backendRoot = app.isPackaged ? path.join(process.resourcesPath, 'backend') : path.join(__dirname, '../../backend');
  const pythonCmd = app.isPackaged
    ? path.join(process.resourcesPath, 'python', 'python.exe')
    : path.join(backendRoot, '.venv', 'Scripts', 'python.exe');
  const serverScript = path.join(backendRoot, 'run_server.py');
  if (!fs.existsSync(pythonCmd)) {
    logger.error('system', 'Python runtime not found', { expected: app.isPackaged ? 'resources/python/python.exe' : 'backend/.venv' });
  }

  let aiProcess = null;
  let retryCount = 0;
  const MAX_RETRIES = 3;

  // One failure handler for both "exited with an error" and "could not be spawned at all".
  function handleBackendFailure(reason) {
    if (isQuitting) return;
    retryCount++;
    if (retryCount <= MAX_RETRIES) {
      const backoffMs = retryCount * 2000;
      logger.info('system', `Restarting Python backend in ${backoffMs}ms (${reason})...`);
      setTimeout(spawnBackend, backoffMs);
    } else {
      logger.error('system', 'Python backend exceeded max retries. Entering Safe Mode.', { reason });
      errorHandler.enterSafeMode(new Error(`Backend could not be restarted: ${reason}`));
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('backend-fatal-error');
      }
    }
  }

  function spawnBackend() {
    let failureHandled = false;
    const failOnce = (reason) => {
      if (failureHandled) return;
      failureHandled = true;
      handleBackendFailure(reason);
    };
    try {
      logger.info('system', `Spawning Python backend (Attempt ${retryCount + 1}/${MAX_RETRIES + 1})...`);

      const backendEnv = {
        ...process.env,
        SENTINEL_SESSION_TOKEN: global.SENTINEL_SESSION_TOKEN,
        SENTINEL_BACKEND_PORT: global.SENTINEL_BACKEND_PORT,
        PYTHONUNBUFFERED: '1' // stream backend logs live (and keep them if it crashes)
      };

      aiProcess = spawn(pythonCmd, [serverScript], {
        cwd: app.isPackaged ? backendRoot : path.join(__dirname, '../../'),
        stdio: 'pipe',
        env: backendEnv
      });
      aiProcess.on('error', (err) => {
        logger.error('system', 'Backend spawn error', { error: err.message });
        failOnce(`spawn error: ${err.code || err.message}`);
      });

      aiProcess.stdout.on('data', (data) => console.log(`[Python AI] ${data}`));
      aiProcess.stderr.on('data', (data) => console.error(`[Python AI] ${data}`));

      aiProcess.on('exit', (code) => {
        logger.warn('system', `Python backend exited with code ${code}`);
        if (code !== 0) failOnce(`exit code ${code}`);
      });
    } catch (err) {
      logger.error('system', 'Failed to spawn Python backend', { error: err.message });
      failOnce(`spawn threw: ${err.message}`);
    }
  }

  spawnBackend();

  // Locking Windows, sleeping or hibernating locks Sentinel too (encrypted database closed).
  // After resume the owner must unlock again; the UI gate shows the unlock screen.
  const { powerMonitor } = require('electron');
  const lockSentinel = (reason) => {
    const http = require('http');
    const req = http.request({
      host: '127.0.0.1', port: Number(global.SENTINEL_BACKEND_PORT), path: '/api/lock', method: 'POST',
      headers: { 'X-Sentinel-Session': global.SENTINEL_SESSION_TOKEN, 'Content-Length': 0 }, timeout: 3000
    }, (res) => {
      res.resume();
      logger.info('system', `Sentinel locked (${reason}): HTTP ${res.statusCode}`);
      if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('sentinel-locked');
    });
    req.on('error', (err) => logger.warn('system', `Could not lock Sentinel on ${reason}`, { error: err.message }));
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.end();
  };
  powerMonitor.on('lock-screen', () => lockSentinel('Windows lock'));
  powerMonitor.on('suspend', () => lockSentinel('sleep'));

  app.on('before-quit', () => {
    if (aiProcess) aiProcess.kill();
  });

  // STEP 8: Create window and tray
  console.log('[SENTINEL] Step 8/8: Creating window...');
  createWindow();
  createTray();

  // Register global hotkeys
  const toggleHotkey = configManager.get('hotkeys.toggleWindow', 'Control+Shift+S');
  globalShortcut.register(toggleHotkey, () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  // Boot complete
  const bootDuration = performance.now() - bootStart;
  logger.info('system', `SENTINEL boot complete in ${bootDuration.toFixed(0)}ms`, {
    firstRun: isFirstRun,
    tier: profile?.tier || 'unknown',
    safeMode: errorHandler.isSafeMode()
  });
  logger.info('system', '═══════════════════════════════════════════════');
}

// ─── Window Creation ─────────────────────────────────────────────
function createWindow() {
  // Restore window bounds from config
  const savedBounds = configManager.get('ui.windowBounds');

  mainWindow = new BrowserWindow({
    width: savedBounds?.width || 1200,
    height: savedBounds?.height || 800,
    x: savedBounds?.x,
    y: savedBounds?.y,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    transparent: false,
    backgroundColor: '#0a0a0f',
    titleBarStyle: 'hidden',
    titleBarOverlay: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    },
    icon: path.join(__dirname, '../../assets/icons/sentinel.png'),
    show: false
  });

  // Security: the window may only ever show the Sentinel UI. A link in model
  // output must not load a web page that could reach the preload bridge.
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  // Microphone only, from our main UI; camera, embedded frames and other permissions stay denied.
  require('./core/media-permissions').installMicrophonePermissions(mainWindow.webContents, isAppUrl);
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!isAppUrl(url)) {
      event.preventDefault();
      logger.warn('security', 'Blocked navigation away from the app UI', { url: String(url).slice(0, 200) });
    }
  });

  if (IS_DEV) {
    mainWindow.loadURL(DEV_ORIGIN);
  } else {
    mainWindow.loadFile(APP_INDEX_PATH);
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Save window bounds on resize/move
  mainWindow.on('resize', () => saveWindowBounds());
  mainWindow.on('move', () => saveWindowBounds());

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

let saveBoundsTimeout = null;
function saveWindowBounds() {
  if (saveBoundsTimeout) clearTimeout(saveBoundsTimeout);
  saveBoundsTimeout = setTimeout(() => {
    if (mainWindow && !mainWindow.isMaximized() && !mainWindow.isMinimized()) {
      const bounds = mainWindow.getBounds();
      configManager.set('ui.windowBounds', bounds);
    }
  }, 500);
}

// ─── System Tray ─────────────────────────────────────────────────
function createTray() {
  // Create a simple 16x16 tray icon programmatically
  const iconSize = 16;

  tray = new Tray(nativeImage.createFromBuffer(
    Buffer.alloc(iconSize * iconSize * 4, 0),
    { width: iconSize, height: iconSize }
  ));

  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show SENTINEL', click: () => mainWindow.show() },
    { type: 'separator' },
    {
      label: `Tier: ${systemProfiler.getTier().toUpperCase()}`,
      enabled: false
    },
    {
      label: `Safe Mode: ${errorHandler.isSafeMode() ? 'ON' : 'OFF'}`,
      enabled: false
    },
    { type: 'separator' },
    { label: 'Quit', click: () => { isQuitting = true; app.quit(); } }
  ]);

  tray.setToolTip('SENTINEL — Your Local AI Assistant');
  tray.setContextMenu(contextMenu);
  tray.on('click', () => {
    mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
  });
}

// ─── IPC Handlers: Authentication ────────────────────────────────
ipcMain.handle('auth-get-session-token', (event) => {
  if (!isTrustedSender(event)) {
    logger.warn('security', 'Refused session token to untrusted frame');
    return null;
  }
  return global.SENTINEL_SESSION_TOKEN;
});
ipcMain.handle('auth-get-backend-port', (event) => (isTrustedSender(event) ? global.SENTINEL_BACKEND_PORT : null));

// ─── IPC Handlers: Window Controls ──────────────────────────────
ipcMain.on('window-minimize', () => mainWindow?.minimize());
ipcMain.on('window-maximize', () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});
ipcMain.on('window-close', () => mainWindow?.hide());

ipcMain.handle('window-is-maximized', () => mainWindow?.isMaximized());

// ─── Removed IPC surface (Phase 0) ──────────────────────────────
// System/process control, file access, screen capture, config writes and
// the legacy JS AI engine (with its cloud router) were exposed to the
// renderer but unused by the UI. They are gone; the UI talks only to the
// Python backend, which enforces policy, confirmation and audit.

// ─── Security: local-only network for the app window ────────────
// Defense in depth for the egress policy: the renderer may only load its own files and talk
// to local hosts (the Python backend; the Vite dev server in development). Every other
// request is cancelled and logged. The backend has its own egress guard for tools.
const LOCAL_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);
function isLocalRequestUrl(rawUrl) {
  let u;
  try { u = new URL(rawUrl); } catch { return false; }
  if (['file:', 'devtools:', 'data:', 'blob:'].includes(u.protocol)) return true;
  return ['http:', 'https:', 'ws:', 'wss:'].includes(u.protocol) && LOCAL_HOSTS.has(u.hostname);
}
function installLocalOnlyRequestFilter() {
  session.defaultSession.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, callback) => {
    if (isLocalRequestUrl(details.url)) return callback({});
    logger.warn('security', 'Blocked non-local request from the app window', { url: String(details.url).slice(0, 200) });
    callback({ cancel: true });
  });
}

// ─── App Lifecycle ──────────────────────────────────────────────
app.whenReady().then(() => {
  installLocalOnlyRequestFilter();
  bootSentinel().catch(err => {
    console.error('[SENTINEL] Boot failed:', err);
    // Last resort — create window anyway
    createWindow();
  });

  // Automated smoke test (tools/check.ps1): quit cleanly after N ms, so the
  // backend shutdown and crash flag behave exactly like a normal user quit.
  const quitAfterMs = parseInt(process.env.SENTINEL_SMOKE_QUIT_AFTER_MS || '', 10);
  if (quitAfterMs > 0) {
    setTimeout(() => { isQuitting = true; app.quit(); }, quitAfterMs);
  }

  // OS Integration (Phase 7)
  // 1. Global Summon Hotkey
  globalShortcut.register('CommandOrControl+Shift+Space', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    }
  });

  // 2. Register for startup
  app.setLoginItemSettings({
    openAtLogin: false,
    openAsHidden: true,
    path: app.getPath('exe')
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  globalShortcut.unregisterAll();

  // Clean shutdown sequence
  logger.info('system', 'SENTINEL shutting down...');

  // Shutdown modules
  moduleManager.shutdownAll().catch(() => { });

  // Save config and clear crash flag
  configManager.shutdown();
  errorHandler.shutdown();

  // Flush logs last
  logger.shutdown();
});
