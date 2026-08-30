const { BasePlugin } = require('../base-plugin');
const { memoryManager } = require('../../memory/memory-manager');
const { logger } = require('../../core/logger');

class MemoryPlugin extends BasePlugin {
  constructor() {
    super('memory', 'Allows SENTINEL to learn and remember facts about the user for long-term memory.');
    
    this.registerTool({
      name: 'learn_fact',
      description: 'Learns a new fact about the user or their preferences. Use this to remember things day-by-day (e.g. user name, user likes dark mode, user is a programmer).',
      parameters: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'A 1-2 word category for the fact (e.g., "name", "profession", "preference")' },
          content: { type: 'string', description: 'The actual fact to remember (e.g., "The user is a software engineer")' }
        },
        required: ['topic', 'content']
      }
    }, this.learnFact.bind(this));
  }

  async learnFact({ topic, content }) {
    try {
      const fact = memoryManager.learnFact(topic, content);
      logger.info('plugin', `Learned new fact: [${topic}] ${content}`);
      return { success: true, message: `Successfully memorized: ${content}` };
    } catch (err) {
      return { error: `Failed to learn fact: ${err.message}` };
    }
  }
}

module.exports = MemoryPlugin;
