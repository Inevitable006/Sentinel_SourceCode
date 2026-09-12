const { BasePlugin } = require('../base-plugin');
const { spawn } = require('child_process');
const { logger } = require('../../core/logger');

class OSControlPlugin extends BasePlugin {
  constructor() {
    super('os-control', 'Provides safe OS-level commands like checking time and launching applications.');

    this.registerTool({
      name: 'get_time',
      description: 'Gets the current system time.',
      parameters: { type: 'object', properties: {} }
    }, this.getTime.bind(this));

    this.registerTool({
      name: 'launch_app',
      description: 'Launches a standard system application (e.g., calculator, notepad, explorer).',
      parameters: {
        type: 'object',
        properties: {
          app_name: { type: 'string', description: 'The name of the app to launch (e.g., calc, notepad, explorer)' }
        },
        required: ['app_name']
      }
    }, this.launchApp.bind(this));
  }

  async getTime() {
    return { time: new Date().toISOString() };
  }

  async launchApp({ app_name }) {
    return { error: `launch_app tool is disabled pending Phase 5 security review and confirmation framework.` };
  }
}

module.exports = OSControlPlugin;
