// Bypass corporate proxy SSL certificate interception
// Required for downloading AI models from HuggingFace behind corporate firewalls
// process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'; // REMOVED for Security

const { app, BrowserWindow, ipcMain, globalShortcut, Tray, Menu, nativeImage, desktopCapturer, shell, dialog } = require('electron');
const path = require('path');
const si = require('systeminformation');

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

  // Point to the virtual environment python executable
  const pythonCmd = path.join(__dirname, '../../backend/.venv/Scripts/python.exe');
  const serverScript = path.join(__dirname, '../../backend/run_server.py');

  let aiProcess = null;
  let retryCount = 0;
  const MAX_RETRIES = 3;

  function spawnBackend() {
    try {
      logger.info('system', `Spawning Python backend (Attempt ${retryCount + 1}/${MAX_RETRIES + 1})...`);

      const backendEnv = { ...process.env, SENTINEL_SESSION_TOKEN: global.SENTINEL_SESSION_TOKEN };

      aiProcess = spawn(pythonCmd, [serverScript], {
        cwd: path.join(__dirname, '../../'),
        stdio: 'pipe',
        env: backendEnv
      });
      aiProcess.on('error', (err) => {
        logger.error('system', 'Backend spawn error (expected in packaged UI test)', { error: err.message });
      });

      aiProcess.stdout.on('data', (data) => console.log(`[Python AI] ${data}`));
      aiProcess.stderr.on('data', (data) => console.error(`[Python AI] ${data}`));

      aiProcess.on('exit', (code) => {
        logger.warn('system', `Python backend exited with code ${code}`);
        if (code !== 0 && !isQuitting) {
          retryCount++;
          if (retryCount <= MAX_RETRIES) {
            const backoffMs = retryCount * 2000;
            logger.info('system', `Restarting Python backend in ${backoffMs}ms...`);
            setTimeout(spawnBackend, backoffMs);
          } else {
            logger.error('system', 'Python backend exceeded max retries. Entering Safe Mode.');
            errorHandler.enterSafeMode(new Error('Backend crashed repeatedly'));
            if (mainWindow) {
              mainWindow.webContents.send('backend-fatal-error');
            }
          }
        }
      });
    } catch (err) {
      logger.error('system', 'Failed to spawn Python backend', { error: err.message });
    }
  }

  spawnBackend();

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
      sandbox: false
    },
    icon: path.join(__dirname, '../../assets/icons/sentinel.png'),
    show: false
  });

  const isDev = process.argv.includes('--dev');
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../../frontend/dist/index.html'));
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
ipcMain.handle('auth-get-session-token', () => global.SENTINEL_SESSION_TOKEN);

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

// ─── IPC Handlers: System Information ───────────────────────────
ipcMain.handle('get-system-stats', async () => {
  return await errorHandler.wrap(
    async () => {
      const [cpu, mem, disk, networkStats, battery, osInfo, graphics] = await Promise.all([
        si.currentLoad(),
        si.mem(),
        si.fsSize(),
        si.networkStats(),
        si.battery(),
        si.osInfo(),
        si.graphics()
      ]);
      return { cpu, mem, disk, networkStats, battery, osInfo, graphics, timestamp: Date.now() };
    },
    { category: 'system', operation: 'Get system stats', fallback: null, silent: true }
  );
});

ipcMain.handle('get-cpu-temperature', async () => {
  return await errorHandler.wrap(
    () => si.cpuTemperature(),
    { category: 'system', operation: 'Get CPU temperature', fallback: null, silent: true }
  );
});

// ─── IPC Handlers: Process Management ───────────────────────────
ipcMain.handle('get-processes', async () => {
  return await errorHandler.wrap(
    () => si.processes(),
    { category: 'system', operation: 'Get processes', fallback: null, silent: true }
  );
});

ipcMain.handle('launch-app', async (event, appPath) => {
  try {
    const errorMsg = await shell.openPath(appPath);
    if (errorMsg) {
      logger.warn('system', `Failed to launch app: ${appPath}`, { error: errorMsg });
      return { success: false, error: errorMsg };
    }
    logger.info('user', `Launched app: ${appPath}`);
    return { success: true };
  } catch (err) {
    logger.warn('system', `Failed to launch app: ${appPath}`, { error: err.message });
    return { success: false, error: err.message };
  }
});

ipcMain.handle('kill-process', async (event, pid) => {
  try {
    process.kill(pid, 'SIGKILL');
    logger.info('user', `Killed process: ${pid}`);
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});
// ─── IPC Handlers: File System ──────────────────────────────────
ipcMain.handle('read-directory', async (event, dirPath) => {
  const fs = require('fs');
  return errorHandler.wrapSync(
    () => {
      const entries = fs.readdirSync(dirPath, { withFileTypes: true });
      return entries.map(entry => ({
        name: entry.name,
        isDirectory: entry.isDirectory(),
        path: path.join(dirPath, entry.name)
      }));
    },
    { category: 'file', operation: `Read directory: ${dirPath}`, fallback: { error: 'Failed to read directory' } }
  );
});

ipcMain.handle('open-file', async (event, filePath) => {
  try {
    await shell.openPath(filePath);
    logger.info('user', `Opened file: ${filePath}`);
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

// ─── IPC Handlers: Screen Capture ───────────────────────────────
ipcMain.handle('capture-screen', async (event, width = 1920, height = 1080) => {
  return await errorHandler.wrap(
    async () => {
      const sources = await desktopCapturer.getSources({
        types: ['screen'],
        thumbnailSize: { width, height }
      });
      if (sources.length > 0) {
        return sources[0].thumbnail.toDataURL();
      }
      return null;
    },
    { category: 'system', operation: 'Screen capture', fallback: null }
  );
});

// ─── IPC Handlers: Core Systems (Phase 1) ───────────────────────
ipcMain.handle('get-system-profile', () => {
  return systemProfiler.getSummary();
});

ipcMain.handle('get-config', (event, keyPath) => {
  return configManager.get(keyPath);
});

ipcMain.handle('set-config', (event, keyPath, value) => {
  configManager.set(keyPath, value);
  return true;
});

ipcMain.handle('get-all-config', () => {
  return configManager.getAll();
});

ipcMain.handle('get-error-stats', () => {
  return errorHandler.getStats();
});

ipcMain.handle('get-module-status', () => {
  return moduleManager.getStatusAll();
});

ipcMain.handle('get-boot-info', () => {
  return {
    isFirstRun: configManager.get('firstRunDate') === null,
    tier: systemProfiler.getTier(),
    safeMode: errorHandler.isSafeMode(),
    profile: systemProfiler.getSummary(),
    lastRun: configManager.get('lastRunDate')
  };
});

// ─── IPC Handlers: AI Engine ────────────────────────────────────
let aiEngine = null;

ipcMain.handle('ai-initialize', async () => {
  return await errorHandler.wrap(
    async () => {
      const { LLMEngine } = require('./ai/llm-engine');
      aiEngine = new LLMEngine();
      const result = await aiEngine.initialize();
      logger.info('ai', 'AI engine initialized', result);
      return result;
    },
    { category: 'ai', operation: 'AI initialization', retry: true, fallback: { success: false, error: 'AI initialization failed' } }
  );
});

ipcMain.handle('ai-chat', async (event, messages) => {
  if (!aiEngine) {
    return { error: 'AI engine not initialized' };
  }
  return await errorHandler.wrap(
    () => aiEngine.chat(messages),
    { category: 'ai', operation: 'AI chat', fallback: { error: 'Chat request failed' } }
  );
});

ipcMain.handle('ai-chat-stream', async (event, messages) => {
  if (!aiEngine) {
    mainWindow.webContents.send('ai-stream-error', 'AI engine not initialized');
    return;
  }
  try {
    await aiEngine.chatStream(messages, (token) => {
      mainWindow.webContents.send('ai-stream-token', token);
    }, () => {
      mainWindow.webContents.send('ai-stream-end');
    });
  } catch (err) {
    logger.error('ai', 'Stream chat error', { error: err.message });
    mainWindow.webContents.send('ai-stream-error', err.message);
  }
});

ipcMain.handle('ai-status', async () => {
  if (!aiEngine) return { loaded: false };
  return aiEngine.getStatus();
});

// ─── Memory Subsystem (Deferred to Phase 2/Python) ───────────────
// ipcMain.handle('memory-start-conversation', () => memoryManager.startConversation());

// ─── App Lifecycle ──────────────────────────────────────────────
app.whenReady().then(() => {
  bootSentinel().catch(err => {
    console.error('[SENTINEL] Boot failed:', err);
    // Last resort — create window anyway
    createWindow();
  });

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
    openAtLogin: true,
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
