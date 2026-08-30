const { configManager } = require('../core/config-manager');
const { logger } = require('../core/logger');

/**
 * CloudRouter
 * Handles routing to cloud APIs (Gemini, Claude, OpenAI) when in Online-Enhanced mode,
 * specifically for tasks too large for the local model, or if the local model fails.
 */
class CloudRouter {
  constructor() {
    this.geminiApiKey = configManager.get('apiKeys.gemini');
    this.openaiApiKey = configManager.get('apiKeys.openai');
    this.claudeApiKey = configManager.get('apiKeys.claude');
  }

  isConfigured() {
    return !!(this.geminiApiKey || this.openaiApiKey || this.claudeApiKey);
  }

  async checkOnlineStatus() {
    try {
      const response = await fetch('https://1.1.1.1', { mode: 'no-cors', signal: AbortSignal.timeout(2000) });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Routes a chat request to the best available cloud model
   */
  async routeChat(messages, systemPrompt) {
    const isOnline = await this.checkOnlineStatus();
    if (!isOnline) {
      throw new Error('System is offline. Cannot route to cloud.');
    }

    if (!this.isConfigured()) {
      throw new Error('No cloud APIs configured.');
    }

    // Prefer Gemini if available
    if (this.geminiApiKey) {
      return this._chatGemini(messages, systemPrompt);
    }
    
    // Additional providers can be implemented here
    throw new Error('Configured cloud API handler not fully implemented.');
  }

  async _chatGemini(messages, systemPrompt) {
    logger.info('ai', 'Routing task to Gemini (Cloud)');
    
    // Note: This is a placeholder for actual Google Generative AI SDK usage
    // For Phase 3, we just simulate the handoff based on the API key presence.
    try {
      // Build the standard Gemini REST payload (simplified)
      const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${this.geminiApiKey}`;
      
      const contents = messages.map(m => ({
        role: m.role === 'assistant' ? 'model' : m.role,
        parts: [{ text: m.content }]
      }));

      // Inject system prompt into first message or using system_instruction
      
      const payload = {
        system_instruction: { parts: [{ text: systemPrompt }] },
        contents: contents
      };

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(`Gemini API error: ${response.statusText}`);
      }

      const data = await response.json();
      const text = data.candidates?.[0]?.content?.parts?.[0]?.text || 'No response from Gemini.';
      
      return { role: 'assistant', content: text };
    } catch (err) {
      logger.error('ai', 'Cloud routing to Gemini failed', { error: err.message });
      throw err;
    }
  }
}

const cloudRouter = new CloudRouter();
module.exports = { cloudRouter, CloudRouter };
