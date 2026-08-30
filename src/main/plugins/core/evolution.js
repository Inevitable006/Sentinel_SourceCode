const { BasePlugin } = require('../base-plugin');
const { evolutionManager } = require('../../core/evolution-manager');
const { logger } = require('../../core/logger');

class EvolutionPlugin extends BasePlugin {
  constructor() {
    super('evolution', 'Allows SENTINEL to write and hot-reload its own capabilities.');
    
    this.registerTool({
      name: 'self_evolve',
      description: 'Writes a new plugin in Javascript and hot-reloads it into SENTINEL dynamically. Use this when the user asks you to learn a new capability that requires interacting with the OS or Node.js.',
      parameters: {
        type: 'object',
        properties: {
          plugin_name: { type: 'string', description: 'A short, hyphenated name for the plugin (e.g. "git-manager")' },
          description: { type: 'string', description: 'What the plugin does' },
          javascript_code: { 
            type: 'string', 
            description: 'The raw javascript code for the plugin. MUST require "../base-plugin", export a class extending BasePlugin, and use module.exports.' 
          }
        },
        required: ['plugin_name', 'description', 'javascript_code']
      }
    }, this.selfEvolve);
  }

  async selfEvolve({ plugin_name, description, javascript_code }) {
    logger.info('evolution', `self_evolve tool called for ${plugin_name}`);
    
    // In a full implementation, we'd route this to CloudRouter for a QC check first.
    // For now, we trust the local model and pass it directly to EvolutionManager.
    
    return await evolutionManager.evolveCapability(plugin_name, description, javascript_code);
  }
}

module.exports = EvolutionPlugin;
