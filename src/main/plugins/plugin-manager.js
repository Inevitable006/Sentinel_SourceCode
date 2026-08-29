const fs = require('fs');
const path = require('path');
const { logger } = require('../core/logger');
const { appPaths } = require('../core/app-paths');

/**
 * SENTINEL — Plugin Manager
 * Dynamically loads and manages tool plugins.
 */
class PluginManager {
  constructor() {
    this.plugins = new Map();
    this.schemasCache = [];
  }

  async initialize() {
    logger.info('plugin', 'Initializing plugin manager...');
    const builtinDir = path.join(__dirname, 'core');

    // Ensure core plugins directory exists
    if (!fs.existsSync(builtinDir)) {
      fs.mkdirSync(builtinDir, { recursive: true });
    }

    // Load core plugins
    await this._loadPluginsFromDirectory(builtinDir);

    // Load user plugins (if any exist in appdata)
    const userPluginsDir = path.join(appPaths.plugins);
    if (!fs.existsSync(userPluginsDir)) {
      fs.mkdirSync(userPluginsDir, { recursive: true });
    } else {
      await this._loadPluginsFromDirectory(userPluginsDir);
    }

    this._rebuildSchemaCache();
    logger.info('plugin', `Plugin manager initialized. Loaded ${this.plugins.size} plugins.`);
  }

  async _loadPluginsFromDirectory(dirPath) {
    if (!fs.existsSync(dirPath)) return;

    const files = fs.readdirSync(dirPath).filter(f => f.endsWith('.js'));
    for (const file of files) {
      try {
        // SECURITY REMEDIATION (Phase 5): Isolate legacy os-control plugin
        if (file === 'os-control.js') {
          logger.info('plugin', `Skipping disabled legacy plugin: ${file}`);
          continue;
        }

        const PluginClass = require(path.join(dirPath, file));
        // Expecting the export to be a class that extends BasePlugin
        const pluginInstance = new PluginClass();
        this.plugins.set(pluginInstance.name, pluginInstance);
        logger.debug('plugin', `Loaded plugin: ${pluginInstance.name}`);
      } catch (err) {
        logger.error('plugin', `Failed to load plugin: ${file}`, { error: err.message });
      }
    }
  }

  _rebuildSchemaCache() {
    this.schemasCache = [];
    for (const plugin of this.plugins.values()) {
      this.schemasCache.push(...plugin.getSchemas());
    }
  }

  getAvailableSchemas() {
    return this.schemasCache;
  }

  async executeTool(toolName, args) {
    logger.info('plugin', `Executing tool: ${toolName}`);

    for (const plugin of this.plugins.values()) {
      const tool = plugin.tools.find(t => t.schema.name === toolName);
      if (tool) {
        try {
          const result = await plugin.execute(toolName, args);
          return { success: true, result };
        } catch (err) {
          logger.error('plugin', `Tool execution failed: ${toolName}`, { error: err.message });
          return { success: false, error: err.message };
        }
      }
    }

    return { success: false, error: `Tool not found: ${toolName}` };
  }
}

const pluginManager = new PluginManager();
module.exports = { pluginManager };
