/**
 * SENTINEL — Logger
 * Structured event logging system with automatic file rotation.
 * 
 * Features:
 * - Writes to daily log files: sentinel-YYYY-MM-DD.log
 * - Structured JSON format for machine readability
 * - Console output with color coding for development
 * - Log categories: system, ai, user, error, performance, module
 * - Automatic cleanup of logs older than 30 days
 * - Buffered writes to minimize disk I/O
 * 
 * Usage:
 *   const { logger } = require('./core/logger');
 *   logger.info('system', 'App started', { version: '1.0.0' });
 *   logger.error('ai', 'Model failed to load', { model: 'qwen2.5' });
 */

const fs = require('fs');
const path = require('path');
const { appPaths } = require('./app-paths');

// Log levels with numeric priority
const LOG_LEVELS = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
  fatal: 4
};

// Valid categories for structured filtering
const CATEGORIES = ['system', 'ai', 'user', 'error', 'performance', 'module', 'memory', 'config'];

class Logger {
  constructor() {
    this.minLevel = LOG_LEVELS.debug;
    this.writeBuffer = [];
    this.flushInterval = null;
    this.maxLogAgeDays = 30;
    this.isInitialized = false;
    this.consoleEnabled = true;
  }

  /**
   * Initialize the logger. Must be called after appPaths.ensureDirectories().
   */
  initialize() {
    if (this.isInitialized) return;

    // Flush buffer to disk every 2 seconds (reduces I/O)
    this.flushInterval = setInterval(() => this.flush(), 2000);

    // Clean up old log files on startup
    this._cleanupOldLogs();

    this.isInitialized = true;
  }

  /**
   * Log a debug message.
   * @param {string} category - Log category (system, ai, user, etc.)
   * @param {string} message - Human-readable message
   * @param {Object} [data] - Optional structured data
   */
  debug(category, message, data = null) {
    this._log('debug', category, message, data);
  }

  /**
   * Log an info message.
   */
  info(category, message, data = null) {
    this._log('info', category, message, data);
  }

  /**
   * Log a warning.
   */
  warn(category, message, data = null) {
    this._log('warn', category, message, data);
  }

  /**
   * Log an error.
   */
  error(category, message, data = null) {
    this._log('error', category, message, data);
  }

  /**
   * Log a fatal error.
   */
  fatal(category, message, data = null) {
    this._log('fatal', category, message, data);
    // Fatal errors flush immediately
    this.flush();
  }

  /**
   * Log a performance measurement.
   * @param {string} operation - What was measured
   * @param {number} durationMs - Duration in milliseconds
   * @param {Object} [data] - Optional additional data
   */
  perf(operation, durationMs, data = null) {
    this._log('info', 'performance', operation, {
      ...data,
      durationMs,
      durationFormatted: durationMs < 1000
        ? `${Math.round(durationMs)}ms`
        : `${(durationMs / 1000).toFixed(2)}s`
    });
  }

  /**
   * Create a timer utility for measuring operation duration.
   * @param {string} operation - Name of the operation
   * @returns {{ stop: Function }} Call stop() to log the duration
   */
  startTimer(operation) {
    const start = performance.now();
    return {
      stop: (data = null) => {
        const duration = performance.now() - start;
        this.perf(operation, duration, data);
        return duration;
      }
    };
  }

  /**
   * Internal logging method.
   */
  _log(level, category, message, data) {
    if (LOG_LEVELS[level] < this.minLevel) return;

    const entry = {
      timestamp: new Date().toISOString(),
      level,
      category: CATEGORIES.includes(category) ? category : 'system',
      message,
      ...(data ? { data } : {})
    };

    // Buffer for file write
    this.writeBuffer.push(entry);

    // Console output (colored)
    if (this.consoleEnabled) {
      this._consoleLog(entry);
    }

    // If buffer is getting large, flush immediately
    if (this.writeBuffer.length >= 50) {
      this.flush();
    }
  }

  /**
   * Colored console output for development.
   */
  _consoleLog(entry) {
    const prefix = `[SENTINEL:${entry.category}]`;
    const msg = entry.message;

    switch (entry.level) {
      case 'debug':
        console.log(`\x1b[90m${prefix} ${msg}\x1b[0m`);
        break;
      case 'info':
        console.log(`\x1b[36m${prefix}\x1b[0m ${msg}`);
        break;
      case 'warn':
        console.warn(`\x1b[33m${prefix}\x1b[0m ${msg}`);
        break;
      case 'error':
        console.error(`\x1b[31m${prefix}\x1b[0m ${msg}`);
        break;
      case 'fatal':
        console.error(`\x1b[41m\x1b[37m ${prefix} FATAL: ${msg} \x1b[0m`);
        break;
    }

    if (entry.data) {
      console.log(`  ↳`, entry.data);
    }
  }

  /**
   * Flush buffered log entries to disk.
   */
  flush() {
    if (this.writeBuffer.length === 0) return;

    const entries = this.writeBuffer.splice(0);
    const logFile = appPaths.getLogFile();

    try {
      const lines = entries.map(e => JSON.stringify(e)).join('\n') + '\n';
      fs.appendFileSync(logFile, lines, 'utf8');
    } catch (err) {
      // Can't log to file — at least keep console output
      console.error('[SENTINEL:Logger] Failed to write log file:', err.message);
    }
  }

  /**
   * Clean up log files older than maxLogAgeDays.
   */
  _cleanupOldLogs() {
    try {
      const files = fs.readdirSync(appPaths.logs);
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - this.maxLogAgeDays);

      let cleaned = 0;
      for (const file of files) {
        if (!file.startsWith('sentinel-') || !file.endsWith('.log')) continue;

        // Extract date from filename: sentinel-YYYY-MM-DD.log
        const dateMatch = file.match(/sentinel-(\d{4}-\d{2}-\d{2})\.log/);
        if (!dateMatch) continue;

        const fileDate = new Date(dateMatch[1]);
        if (fileDate < cutoffDate) {
          fs.unlinkSync(path.join(appPaths.logs, file));
          cleaned++;
        }
      }

      if (cleaned > 0) {
        this.info('system', `Cleaned up ${cleaned} old log file(s)`);
      }
    } catch (err) {
      // Non-critical — don't crash over log cleanup
    }
  }

  /**
   * Read recent log entries for diagnostics.
   * @param {number} [count=100] - Number of recent entries to return
   * @param {string} [category] - Optional category filter
   * @returns {Array} Array of log entry objects
   */
  getRecentEntries(count = 100, category = null) {
    try {
      const logFile = appPaths.getLogFile();
      if (!fs.existsSync(logFile)) return [];

      const content = fs.readFileSync(logFile, 'utf8');
      const lines = content.trim().split('\n').filter(l => l.trim());

      let entries = lines.map(line => {
        try { return JSON.parse(line); }
        catch { return null; }
      }).filter(Boolean);

      if (category) {
        entries = entries.filter(e => e.category === category);
      }

      return entries.slice(-count);
    } catch (err) {
      return [];
    }
  }

  /**
   * Set minimum log level.
   * @param {string} level - 'debug', 'info', 'warn', 'error', 'fatal'
   */
  setLevel(level) {
    if (LOG_LEVELS[level] !== undefined) {
      this.minLevel = LOG_LEVELS[level];
    }
  }

  /**
   * Shutdown: flush remaining entries and stop interval.
   */
  shutdown() {
    this.flush();
    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = null;
    }
    this.isInitialized = false;
  }
}

// Singleton
const logger = new Logger();

module.exports = { logger, Logger, LOG_LEVELS, CATEGORIES };
