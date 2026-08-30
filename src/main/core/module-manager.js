/**
 * SENTINEL — Module Manager
 * Manages the lifecycle of all SENTINEL modules (features).
 * 
 * Every feature in SENTINEL is a "module" with a standard interface.
 * The ModuleManager handles:
 * - Registration & dependency resolution
 * - Ordered initialization (respecting dependencies)
 * - Health monitoring
 * - Graceful shutdown
 * - Error isolation (one module failing doesn't crash others)
 * 
 * Module Interface:
 * {
 *   name: string,              // Unique module name
 *   version: string,           // Module version
 *   dependencies: string[],    // Names of modules this depends on
 *   initialize(): Promise,     // Setup (can fail gracefully)
 *   start(): Promise,          // Begin operation
 *   stop(): Promise,           // Pause operation
 *   getStatus(): Object,       // Health check
 *   destroy(): Promise         // Full cleanup
 * }
 */

const { logger } = require('./logger');

// Module states
const MODULE_STATES = {
  REGISTERED: 'registered',
  INITIALIZING: 'initializing',
  READY: 'ready',
  RUNNING: 'running',
  STOPPED: 'stopped',
  ERROR: 'error',
  DESTROYED: 'destroyed'
};

class ModuleManager {
  constructor() {
    this.modules = new Map();     // name → { module, state, error, metadata }
    this.initOrder = [];          // Resolved initialization order
    this.isShuttingDown = false;
  }

  /**
   * Register a module with the manager.
   * @param {Object} module - Module instance implementing the standard interface
   * @throws {Error} If module is invalid or name is already taken
   */
  register(module) {
    // Validate module interface
    if (!module.name || typeof module.name !== 'string') {
      throw new Error('Module must have a "name" property (string)');
    }

    if (this.modules.has(module.name)) {
      throw new Error(`Module "${module.name}" is already registered`);
    }

    // Ensure required methods exist (provide no-op defaults for optional ones)
    const wrappedModule = {
      name: module.name,
      version: module.version || '1.0.0',
      dependencies: module.dependencies || [],
      initialize: module.initialize?.bind(module) || (async () => {}),
      start: module.start?.bind(module) || (async () => {}),
      stop: module.stop?.bind(module) || (async () => {}),
      getStatus: module.getStatus?.bind(module) || (() => ({ healthy: true })),
      destroy: module.destroy?.bind(module) || (async () => {}),
      _original: module // Keep reference to original
    };

    this.modules.set(module.name, {
      module: wrappedModule,
      state: MODULE_STATES.REGISTERED,
      error: null,
      registeredAt: Date.now(),
      initializedAt: null,
      startedAt: null
    });

    logger.debug('module', `Module registered: ${module.name} v${wrappedModule.version}`, {
      dependencies: wrappedModule.dependencies
    });
  }

  /**
   * Initialize all registered modules in dependency order.
   * Modules whose dependencies failed will be skipped gracefully.
   * 
   * @returns {Object} Results: { succeeded: string[], failed: string[], skipped: string[] }
   */
  async initializeAll() {
    const timer = logger.startTimer('Module initialization (all)');

    // Resolve dependency order
    try {
      this.initOrder = this._resolveDependencyOrder();
    } catch (err) {
      logger.fatal('module', 'Dependency resolution failed', { error: err.message });
      throw err;
    }

    const results = { succeeded: [], failed: [], skipped: [] };
    const failedSet = new Set();

    for (const name of this.initOrder) {
      const entry = this.modules.get(name);

      // Check if any dependency failed
      const depsFailed = entry.module.dependencies.some(dep => failedSet.has(dep));
      if (depsFailed) {
        entry.state = MODULE_STATES.ERROR;
        entry.error = 'Dependency failed';
        results.skipped.push(name);
        failedSet.add(name);
        logger.warn('module', `Module skipped (dependency failed): ${name}`);
        continue;
      }

      // Initialize the module
      try {
        entry.state = MODULE_STATES.INITIALIZING;
        logger.info('module', `Initializing module: ${name}...`);

        const moduleTimer = logger.startTimer(`Module init: ${name}`);
        await entry.module.initialize();
        moduleTimer.stop();

        entry.state = MODULE_STATES.READY;
        entry.initializedAt = Date.now();
        entry.error = null;
        results.succeeded.push(name);

        logger.info('module', `Module initialized: ${name} ✓`);
      } catch (err) {
        entry.state = MODULE_STATES.ERROR;
        entry.error = err.message;
        results.failed.push(name);
        failedSet.add(name);

        logger.error('module', `Module initialization failed: ${name}`, {
          error: err.message,
          stack: err.stack?.split('\n').slice(0, 3).join('\n')
        });
      }
    }

    timer.stop({
      total: this.initOrder.length,
      succeeded: results.succeeded.length,
      failed: results.failed.length,
      skipped: results.skipped.length
    });

    return results;
  }

  /**
   * Start all initialized modules.
   * @returns {Object} Results
   */
  async startAll() {
    const results = { started: [], failed: [] };

    for (const [name, entry] of this.modules) {
      if (entry.state !== MODULE_STATES.READY) continue;

      try {
        await entry.module.start();
        entry.state = MODULE_STATES.RUNNING;
        entry.startedAt = Date.now();
        results.started.push(name);
      } catch (err) {
        entry.state = MODULE_STATES.ERROR;
        entry.error = err.message;
        results.failed.push(name);
        logger.error('module', `Module start failed: ${name}`, { error: err.message });
      }
    }

    return results;
  }

  /**
   * Gracefully shutdown all modules in reverse dependency order.
   */
  async shutdownAll() {
    if (this.isShuttingDown) return;
    this.isShuttingDown = true;

    const timer = logger.startTimer('Module shutdown (all)');
    const shutdownOrder = [...this.initOrder].reverse();

    for (const name of shutdownOrder) {
      const entry = this.modules.get(name);
      if (!entry) continue;

      try {
        if (entry.state === MODULE_STATES.RUNNING) {
          await entry.module.stop();
          entry.state = MODULE_STATES.STOPPED;
        }
        await entry.module.destroy();
        entry.state = MODULE_STATES.DESTROYED;
        logger.debug('module', `Module destroyed: ${name}`);
      } catch (err) {
        logger.warn('module', `Error during shutdown of ${name}`, { error: err.message });
        // Continue shutting down other modules
      }
    }

    timer.stop({ modules: shutdownOrder.length });
  }

  /**
   * Get the status of all modules.
   * @returns {Object} Module statuses
   */
  getStatusAll() {
    const statuses = {};

    for (const [name, entry] of this.modules) {
      statuses[name] = {
        state: entry.state,
        version: entry.module.version,
        error: entry.error,
        uptime: entry.startedAt ? Date.now() - entry.startedAt : 0,
        health: null
      };

      // Get module-specific health (only for running modules)
      if (entry.state === MODULE_STATES.RUNNING) {
        try {
          statuses[name].health = entry.module.getStatus();
        } catch (err) {
          statuses[name].health = { healthy: false, error: err.message };
        }
      }
    }

    return statuses;
  }

  /**
   * Get the status of a specific module.
   * @param {string} name - Module name
   * @returns {Object|null}
   */
  getStatus(name) {
    const entry = this.modules.get(name);
    if (!entry) return null;

    return {
      state: entry.state,
      version: entry.module.version,
      error: entry.error,
      uptime: entry.startedAt ? Date.now() - entry.startedAt : 0,
      health: entry.state === MODULE_STATES.RUNNING ? entry.module.getStatus() : null
    };
  }

  /**
   * Check if a module is running.
   * @param {string} name - Module name
   * @returns {boolean}
   */
  isRunning(name) {
    const entry = this.modules.get(name);
    return entry?.state === MODULE_STATES.RUNNING;
  }

  /**
   * Get the original module instance for direct access.
   * @param {string} name - Module name
   * @returns {Object|null} The original module instance
   */
  getModule(name) {
    const entry = this.modules.get(name);
    return entry?.module?._original || null;
  }

  /**
   * Resolve module initialization order using topological sort.
   * Detects circular dependencies.
   * @returns {string[]} Ordered list of module names
   */
  _resolveDependencyOrder() {
    const visited = new Set();
    const visiting = new Set(); // For cycle detection
    const order = [];

    const visit = (name) => {
      if (visited.has(name)) return;

      if (visiting.has(name)) {
        throw new Error(`Circular dependency detected involving module "${name}"`);
      }

      const entry = this.modules.get(name);
      if (!entry) {
        throw new Error(`Module "${name}" is listed as a dependency but not registered`);
      }

      visiting.add(name);

      for (const dep of entry.module.dependencies) {
        visit(dep);
      }

      visiting.delete(name);
      visited.add(name);
      order.push(name);
    };

    for (const name of this.modules.keys()) {
      visit(name);
    }

    return order;
  }

  /**
   * Get a summary suitable for diagnostics.
   */
  getSummary() {
    const total = this.modules.size;
    let running = 0, error = 0, stopped = 0;

    for (const [, entry] of this.modules) {
      if (entry.state === MODULE_STATES.RUNNING) running++;
      else if (entry.state === MODULE_STATES.ERROR) error++;
      else if (entry.state === MODULE_STATES.STOPPED || entry.state === MODULE_STATES.DESTROYED) stopped++;
    }

    return { total, running, error, stopped };
  }
}

// Singleton
const moduleManager = new ModuleManager();

module.exports = { moduleManager, ModuleManager, MODULE_STATES };
