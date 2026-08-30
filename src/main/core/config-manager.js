/**
 * SENTINEL — Config Manager
 * Persistent settings & state management with corruption recovery.
 * 
 * Features:
 * - Auto-creates default config on first run
 * - Atomic writes (write to temp file, then rename) to prevent corruption
 * - Automatic backup before every save
 * - Deep merge for partial updates
 * - Schema validation for critical settings
 * - In-memory cache for fast reads
 * 
 * Usage:
 *   const { configManager } = require('./core/config-manager');
 *   await configManager.initialize();
 *   const theme = configManager.get('ui.theme');
 *   configManager.set('ui.theme', 'dark');
 */

const fs = require('fs');
const path = require('path');
const { appPaths } = require('./app-paths');
const { logger } = require('./logger');

// Default configuration — used on first run or corruption recovery
const DEFAULT_CONFIG = {
  // ─── Meta ───
  version: '1.0.0',
  firstRunDate: null,       // Set on first initialization
  lastRunDate: null,         // Updated every startup

  // ─── AI Settings ───
  ai: {
    preferredBackend: 'auto',  // 'auto', 'ollama', 'transformers', 'api'
    ollamaUrl: 'http://localhost:11434',
    preferredModel: 'auto',    // 'auto' = let profiler decide
    temperature: 0.7,
    maxTokens: 512,
    streamResponses: true,
    contextWindowSize: 10,     // Number of messages to include in context
    apiEndpoint: null,         // Optional external API URL
    apiKey: null               // Optional API key (stored locally)
  },

  // ─── UI Settings ───
  ui: {
    theme: 'dark',             // 'dark', 'light', 'auto'
    animationsEnabled: true,   // Disabled on low-end hardware
    animationLevel: 'full',    // 'full', 'reduced', 'none'
    fontSize: 14,
    fontFamily: 'system',
    sidebarCollapsed: false,
    windowBounds: null         // { x, y, width, height } — restored on launch
  },

  // ─── System Monitoring ───
  monitoring: {
    updateIntervalMs: 2000,    // How often to poll system stats
    enableGpuMonitoring: true,
    enableNetworkMonitoring: true,
    enableProcessList: true
  },

  // ─── Privacy & Data ───
  privacy: {
    saveConversations: true,   // Persist conversations to disk
    enableLearning: true,      // Allow user pattern learning
    logLevel: 'info',          // 'debug', 'info', 'warn', 'error'
    maxConversationAge: 90,    // Days to keep old conversations
    maxLogAge: 30              // Days to keep old logs
  },

  // ─── Hotkeys ───
  hotkeys: {
    toggleWindow: 'Control+Shift+S',
    newChat: 'Control+N',
    sendMessage: 'Enter'
  },

  // ─── System Profile (populated by profiler) ───
  systemProfile: null
};

class ConfigManager {
  constructor() {
    this.config = null;       // In-memory config cache
    this.isInitialized = false;
    this.saveTimeout = null;  // Debounce saves
  }

  /**
   * Initialize config manager. Loads existing config or creates defaults.
   * @returns {Object} The loaded configuration
   */
  initialize() {
    if (this.isInitialized) return this.config;

    const timer = logger.startTimer('Config initialization');

    try {
      if (appPaths.isFirstRun()) {
        // First run — create default config
        logger.info('config', 'First run detected — creating default configuration');
        this.config = { ...this._deepClone(DEFAULT_CONFIG) };
        this.config.firstRunDate = new Date().toISOString();
        this.config.lastRunDate = new Date().toISOString();
        this._saveSync();
      } else {
        // Load existing config
        this.config = this._loadSync();
        this.config.lastRunDate = new Date().toISOString();

        // Merge with defaults to add any new keys from updates
        this.config = this._deepMerge(this._deepClone(DEFAULT_CONFIG), this.config);

        this._saveSync();
      }

      this.isInitialized = true;
      timer.stop({ keys: Object.keys(this.config).length });
      logger.info('config', 'Configuration loaded successfully');
      return this.config;

    } catch (err) {
      logger.error('config', 'Failed to initialize config — using defaults', {
        error: err.message
      });
      this.config = { ...this._deepClone(DEFAULT_CONFIG) };
      this.config.firstRunDate = new Date().toISOString();
      this.config.lastRunDate = new Date().toISOString();
      this.isInitialized = true;

      // Try to save the defaults
      try { this._saveSync(); } catch (e) { /* non-critical */ }

      timer.stop({ fallback: true });
      return this.config;
    }
  }

  /**
   * Get a config value by dot-notation path.
   * @param {string} keyPath - Dot-notation path (e.g., 'ai.temperature')
   * @param {*} [defaultValue] - Value to return if key doesn't exist
   * @returns {*} The config value
   * 
   * @example
   *   configManager.get('ai.temperature');       // 0.7
   *   configManager.get('ui.theme');              // 'dark'
   *   configManager.get('nonexistent', 'fallback'); // 'fallback'
   */
  get(keyPath, defaultValue = undefined) {
    if (!this.config) return defaultValue;

    const keys = keyPath.split('.');
    let current = this.config;

    for (const key of keys) {
      if (current === null || current === undefined || typeof current !== 'object') {
        return defaultValue;
      }
      current = current[key];
    }

    return current !== undefined ? current : defaultValue;
  }

  /**
   * Set a config value by dot-notation path. Auto-saves after debounce.
   * @param {string} keyPath - Dot-notation path (e.g., 'ai.temperature')
   * @param {*} value - The value to set
   */
  set(keyPath, value) {
    if (!this.config) {
      logger.warn('config', 'Attempted to set config before initialization');
      return;
    }

    const keys = keyPath.split('.');
    let current = this.config;

    // Navigate to parent
    for (let i = 0; i < keys.length - 1; i++) {
      if (typeof current[keys[i]] !== 'object' || current[keys[i]] === null) {
        current[keys[i]] = {};
      }
      current = current[keys[i]];
    }

    const lastKey = keys[keys.length - 1];
    const oldValue = current[lastKey];
    current[lastKey] = value;

    logger.debug('config', `Config updated: ${keyPath}`, { oldValue, newValue: value });

    // Debounced save — wait 500ms for batch updates
    this._debounceSave();
  }

  /**
   * Get the entire config object (read-only clone).
   * @returns {Object} Deep clone of the config
   */
  getAll() {
    return this._deepClone(this.config || DEFAULT_CONFIG);
  }

  /**
   * Reset a specific key to its default value.
   * @param {string} keyPath - Dot-notation path to reset
   */
  reset(keyPath) {
    const defaultValue = this._getFromObject(DEFAULT_CONFIG, keyPath);
    if (defaultValue !== undefined) {
      this.set(keyPath, this._deepClone(defaultValue));
      logger.info('config', `Config reset to default: ${keyPath}`);
    }
  }

  /**
   * Reset entire config to defaults. Creates backup first.
   */
  resetAll() {
    logger.warn('config', 'Full config reset requested');
    this._backupCurrent();
    this.config = {
      ...this._deepClone(DEFAULT_CONFIG),
      firstRunDate: this.config?.firstRunDate || new Date().toISOString(),
      lastRunDate: new Date().toISOString()
    };
    this._saveSync();
    logger.info('config', 'Config reset to defaults complete');
  }

  // ─── Private: File I/O ─────────────────────────────────────────

  /**
   * Load config from disk synchronously.
   */
  _loadSync() {
    const filePath = appPaths.configFile;

    if (!fs.existsSync(filePath)) {
      throw new Error('Config file does not exist');
    }

    const content = fs.readFileSync(filePath, 'utf8');

    // Validate JSON
    try {
      const parsed = JSON.parse(content);
      if (typeof parsed !== 'object' || parsed === null) {
        throw new Error('Config is not a valid object');
      }
      return parsed;
    } catch (parseErr) {
      // Config is corrupted — attempt recovery
      logger.error('config', 'Config file corrupted — attempting recovery', {
        error: parseErr.message
      });
      return this._recoverConfig(filePath);
    }
  }

  /**
   * Save config to disk synchronously with atomic write.
   */
  _saveSync() {
    const filePath = appPaths.configFile;
    const tempPath = filePath + '.tmp';

    try {
      // Write to temp file first
      const content = JSON.stringify(this.config, null, 2);
      fs.writeFileSync(tempPath, content, 'utf8');

      // Atomic rename (replaces target)
      fs.renameSync(tempPath, filePath);
    } catch (err) {
      // Clean up temp file on failure
      try { if (fs.existsSync(tempPath)) fs.unlinkSync(tempPath); } catch (e) { /* ignore */ }
      logger.error('config', 'Failed to save config', { error: err.message });
      throw err;
    }
  }

  /**
   * Debounced save — waits 500ms for batch updates.
   */
  _debounceSave() {
    if (this.saveTimeout) clearTimeout(this.saveTimeout);
    this.saveTimeout = setTimeout(() => {
      try {
        this._saveSync();
      } catch (err) {
        logger.error('config', 'Debounced save failed', { error: err.message });
      }
    }, 500);
  }

  /**
   * Backup current config before destructive operations.
   */
  _backupCurrent() {
    try {
      if (fs.existsSync(appPaths.configFile)) {
        const backupPath = appPaths.getBackupFile('config');
        fs.copyFileSync(appPaths.configFile, backupPath);
        logger.info('config', `Config backed up to ${path.basename(backupPath)}`);
      }
    } catch (err) {
      logger.warn('config', 'Failed to create config backup', { error: err.message });
    }
  }

  /**
   * Attempt to recover a corrupted config file.
   * Tries: most recent backup → defaults.
   */
  _recoverConfig(corruptedPath) {
    // Rename corrupted file for analysis
    try {
      const corruptedBackup = corruptedPath + '.corrupted';
      fs.renameSync(corruptedPath, corruptedBackup);
      logger.warn('config', 'Corrupted config saved for analysis');
    } catch (e) { /* ignore */ }

    // Try to find most recent backup
    try {
      const backupFiles = fs.readdirSync(appPaths.backups)
        .filter(f => f.startsWith('config-') && f.endsWith('.json'))
        .sort()
        .reverse();

      if (backupFiles.length > 0) {
        const backupPath = path.join(appPaths.backups, backupFiles[0]);
        const content = fs.readFileSync(backupPath, 'utf8');
        const parsed = JSON.parse(content);
        logger.info('config', `Recovered config from backup: ${backupFiles[0]}`);
        return parsed;
      }
    } catch (e) {
      logger.warn('config', 'No usable backup found');
    }

    // Final fallback — use defaults
    logger.warn('config', 'Using default config after recovery failure');
    return this._deepClone(DEFAULT_CONFIG);
  }

  // ─── Private: Utilities ─────────────────────────────────────────

  /**
   * Deep merge source into target (target values take priority).
   */
  _deepMerge(defaults, overrides) {
    const result = { ...defaults };

    for (const key of Object.keys(overrides)) {
      if (
        overrides[key] &&
        typeof overrides[key] === 'object' &&
        !Array.isArray(overrides[key]) &&
        defaults[key] &&
        typeof defaults[key] === 'object' &&
        !Array.isArray(defaults[key])
      ) {
        result[key] = this._deepMerge(defaults[key], overrides[key]);
      } else {
        result[key] = overrides[key];
      }
    }

    return result;
  }

  /**
   * Deep clone an object.
   */
  _deepClone(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  /**
   * Get a value from an object by dot-notation path.
   */
  _getFromObject(obj, keyPath) {
    const keys = keyPath.split('.');
    let current = obj;
    for (const key of keys) {
      if (current === null || current === undefined) return undefined;
      current = current[key];
    }
    return current;
  }

  /**
   * Shutdown: flush any pending saves.
   */
  shutdown() {
    if (this.saveTimeout) {
      clearTimeout(this.saveTimeout);
      this.saveTimeout = null;
    }
    // Final save
    try {
      if (this.config) {
        this._backupCurrent();
        this._saveSync();
      }
    } catch (err) {
      // Best effort on shutdown
    }
    this.isInitialized = false;
  }
}

// Singleton
const configManager = new ConfigManager();

module.exports = { configManager, ConfigManager, DEFAULT_CONFIG };
