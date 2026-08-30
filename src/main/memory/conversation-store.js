const fs = require('fs');
const path = require('path');
const { appPaths } = require('../core/app-paths');
const { logger } = require('../core/logger');
const { errorHandler } = require('../core/error-handler');

/**
 * ConversationStore
 * Handles saving, loading, and searching of chat histories.
 * Stores conversations as JSON files in the memory directory.
 */
class ConversationStore {
  constructor() {
    this.initialized = false;
    this.conversationsDir = null;
    this.currentConversationId = null;
    this.messages = [];
  }

  /**
   * Initializes the conversation store
   */
  init() {
    return errorHandler.wrapSync(() => {
      this.conversationsDir = appPaths.conversations;
      this.initialized = true;
      logger.info('memory', 'Conversation store initialized', { dir: this.conversationsDir });
      return true;
    }, 'conversation-store.init');
  }

  /**
   * Starts a new conversation
   */
  startNewConversation() {
    this.currentConversationId = `conv_${Date.now()}`;
    this.messages = [];
    logger.info('memory', 'Started new conversation', { id: this.currentConversationId });
    return this.currentConversationId;
  }

  /**
   * Adds a message to the current conversation and saves it
   * @param {string} role - 'user' or 'assistant'
   * @param {string} content - The message content
   */
  addMessage(role, content) {
    return errorHandler.wrapSync(() => {
      if (!this.initialized) this.init();
      if (!this.currentConversationId) this.startNewConversation();

      const message = {
        role,
        content,
        timestamp: new Date().toISOString()
      };

      this.messages.push(message);
      
      // Prevent infinite memory/disk bloat (User reported flaw fix)
      const MAX_MESSAGES = 100;
      if (this.messages.length > MAX_MESSAGES) {
        this.messages = this.messages.slice(-MAX_MESSAGES);
        logger.warn('memory', `Conversation exceeded ${MAX_MESSAGES} messages. Older messages truncated to save memory.`);
      }
      
      this._saveCurrentConversation();
      return message;
    }, 'conversation-store.addMessage');
  }

  /**
   * Gets the current conversation history
   */
  getHistory() {
    return this.messages;
  }

  /**
   * Loads a specific conversation by ID
   * @param {string} id - Conversation ID
   */
  loadConversation(id) {
    return errorHandler.wrapSync(() => {
      if (!this.initialized) this.init();
      const filePath = path.join(this.conversationsDir, `${id}.json`);
      
      if (fs.existsSync(filePath)) {
        const data = fs.readFileSync(filePath, 'utf8');
        const parsed = JSON.parse(data);
        this.currentConversationId = parsed.id;
        this.messages = parsed.messages;
        logger.info('memory', 'Loaded conversation', { id, messageCount: this.messages.length });
        return this.messages;
      }
      
      logger.warn('memory', 'Conversation not found', { id });
      return null;
    }, 'conversation-store.loadConversation');
  }

  /**
   * Lists all saved conversations (metadata only)
   */
  listConversations() {
    return errorHandler.wrapSync(() => {
      if (!this.initialized) this.init();
      
      const files = fs.readdirSync(this.conversationsDir);
      const conversations = files
        .filter(f => f.endsWith('.json'))
        .map(f => {
          const filePath = path.join(this.conversationsDir, f);
          const stats = fs.statSync(filePath);
          // Just read a snippet to get metadata without parsing massive arrays
          const data = fs.readFileSync(filePath, 'utf8');
          try {
            const parsed = JSON.parse(data);
            return {
              id: parsed.id,
              preview: parsed.messages[0] ? parsed.messages[0].content.substring(0, 50) : 'Empty conversation',
              updatedAt: stats.mtime,
              messageCount: parsed.messages.length
            };
          } catch (e) {
            return null;
          }
        })
        .filter(c => c !== null)
        .sort((a, b) => b.updatedAt - a.updatedAt);
        
      return conversations;
    }, 'conversation-store.listConversations');
  }

  /**
   * Internal helper to save current conversation to disk
   */
  _saveCurrentConversation() {
    if (!this.currentConversationId || this.messages.length === 0) return;

    const filePath = path.join(this.conversationsDir, `${this.currentConversationId}.json`);
    const data = {
      id: this.currentConversationId,
      updatedAt: new Date().toISOString(),
      messages: this.messages
    };

    // Use synchronous write for reliability during active chat
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf8');
  }
}

const conversationStore = new ConversationStore();
module.exports = { conversationStore, ConversationStore };
