/**
 * SENTINEL — Error Handler
 * Global error boundaries, auto-retry, safe mode, and crash recovery.
 * 
 * Features:
 * - Catches uncaught exceptions and unhandled promise rejections
 * - Auto-retry for transient failures (network, file locks)
 * - Error rate tracking — triggers safe mode if too many errors
 * - Safe mode disables non-essential features to keep app running
 * - Crash flag system — detects if last session crashed
 * 
 * Error Philosophy:
 *   SENTINEL should NEVER crash completely. It should degrade gracefully:
 *   1. Try to recover the specific operation
 *   2. If that fails, disable the feature that's causing problems
 *   3. If too many features fail, enter safe mode
 *   4. Only as a last resort, restart the app
 */

const { logger } = require('./logger');
const { appPaths } = require('./app-paths');

// Error categories for tracking
const ERROR_CATEGORIES = {
  AI: 'ai',
  SYSTEM: 'system',
  FILE: 'file',
  NETWORK: 'network',
  MODULE: 'module',
  UI: 'ui',
  UNKNOWN: 'unknown'
};

// Retry configuration per error type
const RETRY_CONFIG = {
  network: { maxRetries: 3, baseDelayMs: 1000, backoffMultiplier: 2 },
  file: { maxRetries: 2, baseDelayMs: 500, backoffMultiplier: 1.5 },
  ai: { maxRetries: 2, baseDelayMs: 2000, backoffMultiplier: 2 },
  default: { maxRetries: 1, baseDelayMs: 1000, backoffMultiplier: 1 }
};

class ErrorHandler {
  constructor() {
    this.errorCounts = {};         // category → count in current window
    this.errorTimestamps = [];     // Recent error timestamps for rate limiting
    this.safeMode = false;         // Whether safe mode is active
    this.isInitialized = false;

    // Safe mode triggers if more than 10 errors in 60 seconds
    this.safeModeThreshold = 10;
    this.safeModeWindowMs = 60000;

    // Callbacks for safe mode events
    this.onSafeModeChange = null;
  }

  /**
   * Initialize the error handler. Installs global error handlers.
   */
  initialize() {
    if (this.isInitialized) return;

    // Handle uncaught exceptions
    process.on('uncaughtException', (error) => {
      this._handleFatal('uncaughtException', error);
    });

    // Handle unhandled promise rejections
    process.on('unhandledRejection', (reason, promise) => {
      const error = reason instanceof Error ? reason : new Error(String(reason));
      this._handleFatal('unhandledRejection', error);
    });

    // Check if last session crashed
    if (appPaths.didCrash()) {
      logger.warn('system', 'Previous session crashed — entering cautious startup', {
        crashFlagDate: this._readCrashFlagDate()
      });
    }

    // Set crash flag (cleared on clean exit)
    appPaths.setCrashFlag();

    this.isInitialized = true;
    logger.info('system', 'Error handler initialized');
  }

  /**
   * Wrap an async operation with error handling and optional retry.
   * 
   * @param {Function} operation - Async function to execute
   * @param {Object} options - Configuration
   * @param {string} [options.category='unknown'] - Error category
   * @param {string} [options.operation='unnamed'] - Human-readable operation name
   * @param {boolean} [options.retry=false] - Whether to retry on failure
   * @param {*} [options.fallback=null] - Value to return if all attempts fail
   * @param {boolean} [options.silent=false] - Don't log errors (for expected failures)
   * @returns {*} Operation result or fallback value
   * 
   * @example
   *   const result = await errorHandler.wrap(
   *     () => fetchFromOllama(messages),
   *     { category: 'ai', operation: 'AI chat', retry: true, fallback: null }
   *   );
   */
  async wrap(operation, options = {}) {
    const {
      category = ERROR_CATEGORIES.UNKNOWN,
      operation: opName = 'unnamed operation',
      retry = false,
      fallback = null,
      silent = false
    } = options;

    if (!retry) {
      // Simple wrap without retry
      try {
        return await operation();
      } catch (err) {
        this._trackError(category, err, opName, silent);
        return fallback;
      }
    }

    // Retry logic
    const retryConfig = RETRY_CONFIG[category] || RETRY_CONFIG.default;
    let lastError = null;

    for (let attempt = 0; attempt <= retryConfig.maxRetries; attempt++) {
      try {
        if (attempt > 0) {
          const delay = retryConfig.baseDelayMs * Math.pow(retryConfig.backoffMultiplier, attempt - 1);
          logger.debug('system', `Retry ${attempt}/${retryConfig.maxRetries} for "${opName}" after ${delay}ms`);
          await this._sleep(delay);
        }
        return await operation();
      } catch (err) {
        lastError = err;
        if (attempt < retryConfig.maxRetries) {
          logger.warn('system', `Operation "${opName}" failed (attempt ${attempt + 1}), retrying...`, {
            error: err.message
          });
        }
      }
    }

    // All retries exhausted
    this._trackError(category, lastError, opName, silent);
    return fallback;
  }

  /**
   * Wrap a synchronous operation with error handling.
   * @param {Function} operation - Sync function to execute
   * @param {Object} options - Same as wrap() options
   * @returns {*} Operation result or fallback value
   */
  wrapSync(operation, options = {}) {
    const {
      category = ERROR_CATEGORIES.UNKNOWN,
      operation: opName = 'unnamed operation',
      fallback = null,
      silent = false
    } = options;

    try {
      return operation();
    } catch (err) {
      this._trackError(category, err, opName, silent);
      return fallback;
    }
  }

  /**
   * Track an error and check safe mode threshold.
   */
  _trackError(category, error, operation, silent = false) {
    // Increment counters
    this.errorCounts[category] = (this.errorCounts[category] || 0) + 1;
    this.errorTimestamps.push(Date.now());

    // Clean old timestamps
    const now = Date.now();
    this.errorTimestamps = this.errorTimestamps.filter(t => now - t < this.safeModeWindowMs);

    // Log the error
    if (!silent) {
      logger.error(category, `Operation failed: ${operation}`, {
        error: error.message,
        category,
        totalErrors: this.errorCounts[category],
        recentErrors: this.errorTimestamps.length
      });
    }

    // Check safe mode threshold
    if (!this.safeMode && this.errorTimestamps.length >= this.safeModeThreshold) {
      this._enterSafeMode();
    }
  }

  /**
   * Handle fatal errors (uncaught exceptions, unhandled rejections).
   */
  _handleFatal(type, error) {
    logger.fatal('system', `${type}: ${error.message}`, {
      stack: error.stack,
      type
    });

    // In production, try to keep running
    // In development, crash is acceptable for debugging
    if (process.argv.includes('--dev')) {
      console.error(`\n[SENTINEL FATAL] ${type}:`, error);
    }

    // Don't exit — try to keep running
    // The crash flag is already set, so if we do exit, next launch will know
  }

  /**
   * Enter safe mode — disable non-essential features.
   */
  _enterSafeMode() {
    if (this.safeMode) return;

    this.safeMode = true;
    logger.warn('system', '⚠️ SAFE MODE ACTIVATED — Too many errors detected', {
      errorCounts: { ...this.errorCounts },
      recentErrors: this.errorTimestamps.length
    });

    // Notify listeners
    if (this.onSafeModeChange) {
      try {
        this.onSafeModeChange(true);
      } catch (err) {
        // Don't let callback errors make things worse
      }
    }
  }

  /**
   * Exit safe mode.
   */
  exitSafeMode() {
    if (!this.safeMode) return;

    this.safeMode = false;
    this.errorCounts = {};
    this.errorTimestamps = [];

    logger.info('system', 'Safe mode deactivated — normal operation resumed');

    if (this.onSafeModeChange) {
      try {
        this.onSafeModeChange(false);
      } catch (err) { /* ignore */ }
    }
  }

  /**
   * Check if safe mode is active.
   * @returns {boolean}
   */
  isSafeMode() {
    return this.safeMode;
  }

  /**
   * Get error statistics for diagnostics.
   */
  getStats() {
    return {
      safeMode: this.safeMode,
      errorCounts: { ...this.errorCounts },
      totalErrors: Object.values(this.errorCounts).reduce((a, b) => a + b, 0),
      recentErrors: this.errorTimestamps.length,
      safeModeThreshold: this.safeModeThreshold,
      lastCrash: appPaths.didCrash() ? this._readCrashFlagDate() : null
    };
  }

  /**
   * Read the crash flag date.
   */
  _readCrashFlagDate() {
    try {
      const fs = require('fs');
      if (fs.existsSync(appPaths.crashFlag)) {
        return fs.readFileSync(appPaths.crashFlag, 'utf8').trim();
      }
    } catch (e) { /* ignore */ }
    return null;
  }

  /**
   * Clean shutdown — clear crash flag.
   */
  shutdown() {
    appPaths.clearCrashFlag();
    logger.info('system', 'Clean shutdown — crash flag cleared');
    this.isInitialized = false;
  }

  /**
   * Utility: async sleep.
   */
  _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

// Singleton
const errorHandler = new ErrorHandler();

module.exports = { errorHandler, ErrorHandler, ERROR_CATEGORIES, RETRY_CONFIG };
