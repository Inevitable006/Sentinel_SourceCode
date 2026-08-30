const { BasePlugin } = require('../base-plugin');
const { logger } = require('../../core/logger');

class WebFetcherPlugin extends BasePlugin {
  constructor() {
    super('web-fetcher', 'Allows SENTINEL to read text content from public URLs.');
    
    this.registerTool({
      name: 'fetch_url',
      description: 'Fetches the text content of a webpage. Useful for researching current events, reading documentation, or summarizing articles. Note: Only works on public pages without CAPTCHAs.',
      parameters: {
        type: 'object',
        properties: {
          url: { type: 'string', description: 'The absolute URL to fetch (must include https://)' }
        },
        required: ['url']
      }
    }, this.fetchUrl);
  }

  async fetchUrl({ url }) {
    logger.info('plugin', `Fetching URL: ${url}`);
    
    if (!url.startsWith('http')) {
      return { error: 'Invalid URL. Must start with http:// or https://' };
    }

    try {
      const response = await fetch(url, {
        headers: {
          'User-Agent': 'SENTINEL/1.0 (Local AI Assistant)'
        }
      });
      
      if (!response.ok) {
        return { error: `HTTP Error: ${response.status} ${response.statusText}` };
      }
      
      let text = await response.text();
      
      // Basic HTML stripping to save tokens
      text = text.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
      text = text.replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '');
      text = text.replace(/<[^>]+>/g, ' ');
      text = text.replace(/\s+/g, ' ').trim();
      
      // Truncate to ~4000 characters to prevent overflowing the AI's context window
      if (text.length > 4000) {
        text = text.substring(0, 4000) + '... [CONTENT TRUNCATED]';
      }

      return { success: true, content: text };
    } catch (err) {
      return { error: `Network error: ${err.message}` };
    }
  }
}

module.exports = WebFetcherPlugin;
