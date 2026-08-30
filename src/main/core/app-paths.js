/**
 * SENTINEL — App Paths
 * Centralized path management for all SENTINEL data directories.
 * 
 * All user data lives in %APPDATA%/sentinel/ on Windows.
 * This module ensures all directories exist on first access.
 * 
 * Directory Structure:
 *   %APPDATA%/sentinel/
 *   ├── config/          → App settings, user preferences
 *   ├── logs/            → Event logs (rotated)
 *   ├── memory/          → Conversations, knowledge base
 *   │   ├── conversations/
 *   │   ├── knowledge/
 *   │   └── profile/
 *   ├── models/          → Cached AI model data
 *   ├── plugins/         → User-installed plugins
 *   └── backups/         → Config & state backups
 */

const path = require('path');
const fs = require('fs');
const { app } = require('electron');

class AppPaths {
  constructor() {
    // Root data directory: %APPDATA%/sentinel
    this.root = path.join(app.getPath('appData'), 'sentinel');

    // Define all subdirectories
    this.config = path.join(this.root, 'config');
    this.logs = path.join(this.root, 'logs');
    this.memory = path.join(this.root, 'memory');
    this.conversations = path.join(this.root, 'memory', 'conversations');
    this.knowledge = path.join(this.root, 'memory', 'knowledge');
    this.profile = path.join(this.root, 'memory', 'profile');
    this.models = path.join(this.root, 'models');
    this.plugins = path.join(this.root, 'plugins');
    this.backups = path.join(this.root, 'backups');

    // Specific file paths
    this.configFile = path.join(this.config, 'settings.json');
    this.systemProfile = path.join(this.config, 'system-profile.json');
    this.userProfile = path.join(this.profile, 'user-profile.json');
    this.crashFlag = path.join(this.root, '.crash-flag');
    this.lockFile = path.join(this.root, '.lock');
  }

  /**
   * Ensure all required directories exist.
   * Safe to call multiple times — uses mkdirSync with recursive:true.
   * @returns {boolean} true if all directories were created/verified successfully
   */
  ensureDirectories() {
    const dirs = [
      this.root,
      this.config,
      this.logs,
      this.memory,
      this.conversations,
      this.knowledge,
      this.profile,
      this.models,
      this.plugins,
      this.backups
    ];

    try {
      for (const dir of dirs) {
        if (!fs.existsSync(dir)) {
          fs.mkdirSync(dir, { recursive: true });
        }
      }
      return true;
    } catch (err) {
      console.error('[SENTINEL:Paths] Failed to create directories:', err.message);
      return false;
    }
  }

  /**
   * Get the path for a log file for a specific date.
   * @param {Date} [date] - Date for the log file (defaults to today)
   * @returns {string} Full path to the log file
   */
  getLogFile(date = new Date()) {
    const dateStr = date.toISOString().split('T')[0]; // YYYY-MM-DD
    return path.join(this.logs, `sentinel-${dateStr}.log`);
  }

  /**
   * Get the path for a conversation file.
   * @param {string} conversationId - Unique conversation identifier
   * @returns {string} Full path to the conversation JSON file
   */
  getConversationFile(conversationId) {
    return path.join(this.conversations, `${conversationId}.json`);
  }

  /**
   * Get the path for a backup file with timestamp.
   * @param {string} name - Backup name (e.g., 'config', 'profile')
   * @returns {string} Full path to the backup file
   */
  getBackupFile(name) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    return path.join(this.backups, `${name}-${timestamp}.json`);
  }

  /**
   * Check if this is the first run (no config directory exists yet).
   * @returns {boolean}
   */
  isFirstRun() {
    return !fs.existsSync(this.configFile);
  }

  /**
   * Check if the app crashed last time (crash flag exists).
   * @returns {boolean}
   */
  didCrash() {
    return fs.existsSync(this.crashFlag);
  }

  /**
   * Set crash flag (called on startup, cleared on clean exit).
   */
  setCrashFlag() {
    try {
      fs.writeFileSync(this.crashFlag, new Date().toISOString());
    } catch (err) {
      // Non-critical — don't throw
    }
  }

  /**
   * Clear crash flag (called on clean shutdown).
   */
  clearCrashFlag() {
    try {
      if (fs.existsSync(this.crashFlag)) {
        fs.unlinkSync(this.crashFlag);
      }
    } catch (err) {
      // Non-critical — don't throw
    }
  }

  /**
   * Get a summary of all paths for diagnostics.
   * @returns {Object}
   */
  getSummary() {
    return {
      root: this.root,
      config: this.config,
      logs: this.logs,
      memory: this.memory,
      models: this.models,
      plugins: this.plugins,
      backups: this.backups,
      isFirstRun: this.isFirstRun(),
      didCrash: this.didCrash()
    };
  }
}

// Singleton — one instance for the entire app
const appPaths = new AppPaths();

module.exports = { appPaths, AppPaths };
