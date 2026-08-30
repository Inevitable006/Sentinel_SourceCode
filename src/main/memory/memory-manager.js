const { logger } = require('../core/logger');
const { errorHandler } = require('../core/error-handler');
const { conversationStore } = require('./conversation-store');
const { userProfile } = require('./user-profile');
const { knowledgeBase } = require('./knowledge-base');

/**
 * MemoryManager
 * Orchestrates all memory subsystems (conversations, profile, knowledge).
 */
class MemoryManager {
  constructor() {
    this.initialized = false;
  }

  /**
   * Initializes all memory subsystems
   */
  init() {
    return errorHandler.wrapSync(() => {
      logger.info('memory', 'Initializing memory manager...');
      
      conversationStore.init();
      userProfile.init();
      knowledgeBase.init();
      
      this.initialized = true;
      logger.info('memory', 'Memory manager initialized successfully');
      return true;
    }, 'memory-manager.init');
  }

  /**
   * Gathers context for the AI prompt based on a user message
   */
  getContextForMessage(message) {
    if (!this.initialized) this.init();
    
    // 1. Get recent conversation history
    const history = conversationStore.getHistory();
    const recentHistory = history.slice(-10); // Last 10 messages
    
    // 2. Get user profile summary
    const profile = userProfile.getProfile();
    const userSummary = `User prefers verbosity level ${profile.preferences.verbosity.toFixed(1)} ` +
                        `and technical depth ${profile.preferences.technicalDepth.toFixed(1)}.`;
    
    // 3. Search knowledge base for keywords in the message
    // (A simple approach: just split words and search)
    const keywords = message.split(' ').filter(w => w.length > 3);
    const facts = new Set();
    keywords.forEach(kw => {
      const found = knowledgeBase.getFacts(kw);
      found.forEach(f => facts.add(f.content));
    });

    return {
      recentHistory,
      userSummary,
      relevantFacts: Array.from(facts)
    };
  }

  // --- Pass-through methods for IPC ---
  
  startConversation() {
    return conversationStore.startNewConversation();
  }
  
  addMessage(role, content) {
    return conversationStore.addMessage(role, content);
  }
  
  listConversations() {
    return conversationStore.listConversations();
  }
  
  loadConversation(id) {
    return conversationStore.loadConversation(id);
  }

  getProfile() {
    return userProfile.getProfile();
  }
  
  learnFact(topic, content) {
    return knowledgeBase.addFact(topic, content);
  }
}

const memoryManager = new MemoryManager();
module.exports = { memoryManager, MemoryManager };
