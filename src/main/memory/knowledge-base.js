const fs = require('fs');
const path = require('path');
const { appPaths } = require('../core/app-paths');
const { logger } = require('../core/logger');
const { errorHandler } = require('../core/error-handler');

/**
 * KnowledgeBase
 * Stores permanent facts taught by the user.
 */
class KnowledgeBase {
  constructor() {
    this.initialized = false;
    this.knowledgePath = null;
    this.facts = []; // Array of { id, topic, content, timestamp }
  }

  init() {
    return errorHandler.wrapSync(() => {
      const kbDir = appPaths.knowledge;
      this.knowledgePath = path.join(kbDir, 'facts.json');
      
      this.load();
      this.initialized = true;
      logger.info('memory', 'Knowledge base initialized', { factsCount: this.facts.length });
      return true;
    }, 'knowledge-base.init');
  }

  load() {
    if (fs.existsSync(this.knowledgePath)) {
      try {
        const data = fs.readFileSync(this.knowledgePath, 'utf8');
        this.facts = JSON.parse(data);
      } catch (err) {
        logger.error('memory', 'Failed to load knowledge base', { error: err.message });
        this.facts = [];
      }
    } else {
      this.save();
    }
  }

  save() {
    try {
      fs.writeFileSync(this.knowledgePath, JSON.stringify(this.facts, null, 2), 'utf8');
    } catch (err) {
      logger.error('memory', 'Failed to save knowledge base', { error: err.message });
    }
  }

  /**
   * Adds a new fact to the knowledge base
   */
  addFact(topic, content) {
    return errorHandler.wrapSync(() => {
      if (!this.initialized) this.init();

      const fact = {
        id: `fact_${Date.now()}`,
        topic: topic.toLowerCase(),
        content,
        timestamp: new Date().toISOString()
      };

      this.facts.push(fact);
      this.save();
      logger.info('memory', 'New fact learned', { topic });
      return fact;
    }, 'knowledge-base.addFact');
  }

  /**
   * Retrieves facts relevant to a topic or query
   */
  getFacts(query) {
    return errorHandler.wrapSync(() => {
      if (!this.initialized) this.init();
      const q = query.toLowerCase();
      // Basic keyword matching (can be upgraded to semantic search later)
      return this.facts.filter(f => f.topic.includes(q) || f.content.toLowerCase().includes(q));
    }, 'knowledge-base.getFacts');
  }
}

const knowledgeBase = new KnowledgeBase();
module.exports = { knowledgeBase, KnowledgeBase };
