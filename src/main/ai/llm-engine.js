/**
 * SENTINEL — LLM Engine
 * Smart AI backend with dual-mode support:
 * 1. Ollama (recommended) — runs models via Ollama server
 * 2. Transformers.js — direct ONNX Runtime (requires HuggingFace access)
 * 3. Fallback — smart pre-built responses when no AI backend available
 */

const { aiRuleset } = require('./ai-ruleset');
const { memoryManager } = require('../memory/memory-manager');
const { systemProfiler } = require('../core/system-profiler');
const { cloudRouter } = require('./cloud-router');
const { pluginManager } = require('../plugins/plugin-manager');

class LLMEngine {
  constructor() {
    this.mode = null; // 'transformers', 'cloud', 'fallback'
    this.pipeline = null;
    this.transformersModelId = 'onnx-community/Phi-3-mini-4k-instruct'; // Microsoft's highly intelligent local model
    this.isLoaded = false;
    this.isLoading = false;
    this.loadProgress = 0;
    this.systemPrompt = this._getSystemPrompt();
  }

  _getSystemPrompt(message = '') {
    // 1. Get context from Memory Manager
    let context = {};
    try {
      context = memoryManager.getContextForMessage(message);
      
      // Inject system state (mock for now, can be wired to systemProfiler later)
      context.systemState = 'All systems nominal.';
      
      // Inject tools from PluginManager
      context.tools = pluginManager.getAvailableSchemas();
    } catch (err) {
      console.error('[SENTINEL] Error getting memory context', err);
    }
    
    // 2. Generate prompt using AI Ruleset
    try {
      return aiRuleset.generateSystemPrompt(context);
    } catch (err) {
      console.error('[SENTINEL] Error generating system prompt from ruleset', err);
      return 'You are SENTINEL, a local AI assistant. Please assist the user.';
    }
  }

  async initialize() {
    if (this.isLoading) return { success: false, error: 'Already loading' };
    if (this.isLoaded) return { success: true, message: 'Already loaded' };

    this.isLoading = true;
    this.loadProgress = 0;

    // Strategy 1: Try Transformers.js (ONNX Runtime Local AI)
    console.log('[SENTINEL] Initializing local AI via Transformers.js (ONNX Runtime)...');
    try {
      const { pipeline, env } = await import('@huggingface/transformers');
      env.allowLocalModels = true;
      env.useBrowserCache = false;

      this.pipeline = await pipeline('text-generation', this.transformersModelId, {
        dtype: 'q4',
        device: 'auto',
        progress_callback: (progress) => {
          if (progress.status === 'progress') {
            this.loadProgress = Math.round((progress.loaded / progress.total) * 100) || 0;
          }
        }
      });

      this.mode = 'transformers';
      this.isLoaded = true;
      this.isLoading = false;
      this.loadProgress = 100;
      console.log('[SENTINEL] Transformers.js engine ready.');
      return { success: true, model: this.transformersModelId, mode: 'transformers' };
    } catch (tfErr) {
      console.log('[SENTINEL] Transformers.js failed:', tfErr.message);
    }

    // Strategy 3: Try Cloud Routing (if online and configured)
    if (cloudRouter.isConfigured()) {
      const isOnline = await cloudRouter.checkOnlineStatus();
      if (isOnline) {
        console.log('[SENTINEL] Local models failed. Online mode active: using Cloud Router.');
        this.mode = 'cloud';
        this.isLoaded = true;
        this.isLoading = false;
        this.loadProgress = 100;
        return { success: true, model: 'cloud', mode: 'cloud' };
      }
    }

    // Strategy 4: Fallback to smart pre-built responses
    console.log('[SENTINEL] Using fallback response engine.');
    this.mode = 'fallback';
    this.isLoaded = true;
    this.isLoading = false;
    this.loadProgress = 100;
    return { 
      success: true, 
      model: 'fallback', 
      mode: 'fallback',
      message: 'Running in offline fallback mode. No local or cloud models available.'
    };
  }

  // ─── Memory/Token Management ──────────────────────────────────
  _truncateContext(messages) {
    // Keep context window lean to prevent OOM / Token limits
    // Max 20 recent messages + any system messages
    const systemMessages = messages.filter(m => m.role === 'system');
    const conversationMessages = messages.filter(m => m.role !== 'system');
    
    const recentMessages = conversationMessages.slice(-20);
    return [...systemMessages, ...recentMessages];
  }

  async chat(messages) {
    if (!this.isLoaded) return { error: 'Engine not initialized' };
    
    messages = this._truncateContext(messages);

    let response;
    switch (this.mode) {
      case 'transformers': response = await this._chatTransformers(messages); break;
      case 'cloud': response = await this._chatCloud(messages); break;
      case 'fallback': response = this._chatFallback(messages); break;
      default: return { error: 'Unknown mode' };
    }
    
    return await this._processPotentialToolCall(response, messages);
  }

  async chatStream(messages, onToken, onEnd) {
    if (!this.isLoaded) throw new Error('Engine not initialized');
    
    messages = this._truncateContext(messages);
    
    // For streaming, we need to intercept the output. If it looks like JSON, we buffer it.
    // To keep it simple for now, if streaming detects a tool call, we handle it post-stream.
    // In a full implementation, we'd buffer '{' and stop emitting tokens until we know if it's a tool.
    
    switch (this.mode) {
      case 'transformers': return await this._chatStreamTransformers(messages, onToken, onEnd);
      case 'cloud': return await this._chatStreamCloud(messages, onToken, onEnd);
      case 'fallback': return this._chatStreamFallback(messages, onToken, onEnd);
      default: throw new Error('Unknown mode');
    }
  }

  // ─── Tool Processing (Phase 5) ──────────────────────────────
  async _processPotentialToolCall(response, messages) {
    if (response.error || !response.content) return response;

    const content = response.content;
    let jsonMatch = null;
    let toolCall = null;
    
    const startIndex = content.indexOf('{"tool":');
    if (startIndex !== -1) {
      for (let i = content.length; i > startIndex; i--) {
        if (content[i - 1] === '}') {
          try {
            const possibleJson = content.substring(startIndex, i);
            toolCall = JSON.parse(possibleJson);
            if (toolCall && toolCall.tool) {
              jsonMatch = possibleJson;
              break;
            }
          } catch (e) {
            // Ignore syntax errors, try smaller substring
          }
        }
      }
    }
    
    if (jsonMatch && toolCall) {
      try {
        console.log('[SENTINEL] Tool call intercepted:', toolCall.tool);
        
        const result = await pluginManager.executeTool(toolCall.tool, toolCall.args);
        
        // Feed result back into context silently
        const toolResultMessage = { 
          role: 'system', 
          content: `[TOOL RESULT for ${toolCall.tool}]: ${JSON.stringify(result)}` 
        };
        
        const newMessages = [...messages, { role: 'assistant', content: jsonMatch }, toolResultMessage];
        
        // Recurse to let the AI respond to the tool result
        // We only allow 1 recursion depth for safety
        if (!messages.some(m => m.content && m.content.includes('[TOOL RESULT'))) {
            return await this.chat(newMessages);
        } else {
            return { role: 'assistant', content: `Tool executed: ${JSON.stringify(result)}` };
        }
        
      } catch (err) {
        console.error('[SENTINEL] Failed to parse or execute tool call', err);
      }
    }

    return response;
  }



  // ─── Cloud Backend (Online Enhanced) ────────────────────────
  async _chatCloud(messages) {
    try {
      const lastMessage = messages.length > 0 ? messages[messages.length - 1].content : '';
      const dynamicPrompt = this._getSystemPrompt(lastMessage);
      
      return await cloudRouter.routeChat(messages, dynamicPrompt);
    } catch (err) {
      return { error: `Cloud routing error: ${err.message}` };
    }
  }

  async _chatStreamCloud(messages, onToken, onEnd) {
    try {
      // For now, simulate streaming for cloud APIs that don't support it natively yet in our stub
      const result = await this._chatCloud(messages);
      if (result.error) throw new Error(result.error);
      
      const words = result.content.split(' ');
      let i = 0;
      
      const interval = setInterval(() => {
        if (i < words.length) {
          onToken(words[i] + ' ');
          i++;
        } else {
          clearInterval(interval);
          onEnd();
        }
      }, 50); // Fake streaming delay
      
    } catch (err) {
      throw err;
    }
  }

  // ─── Transformers.js Backend ────────────────────────────────
  async _chatTransformers(messages) {
    try {
      const formattedMessages = [
        { role: 'system', content: this.systemPrompt },
        ...messages
      ];

      const output = await this.pipeline(formattedMessages, {
        max_new_tokens: 512,
        temperature: 0.7,
        top_p: 0.9,
        do_sample: true,
        return_full_text: false
      });

      const responseText = output[0]?.generated_text;
      let content = this._extractContent(responseText);
      return { role: 'assistant', content };
    } catch (err) {
      return { error: err.message };
    }
  }

  async _chatStreamTransformers(messages, onToken, onEnd) {
    const result = await this._chatTransformers(messages);
    if (result.error) throw new Error(result.error);
    
    const words = result.content.split(' ');
    for (let i = 0; i < words.length; i++) {
      const token = (i === 0 ? '' : ' ') + words[i];
      onToken(token);
      await new Promise(r => setTimeout(r, 30));
    }
    onEnd();
  }

  // ─── Fallback (No AI) ──────────────────────────────────────
  _chatFallback(messages) {
    const lastMessage = messages[messages.length - 1]?.content?.toLowerCase() || '';
    let response;

    if (lastMessage.includes('hello') || lastMessage.includes('hi') || lastMessage.includes('hey')) {
      response = "Good day, sir. I'm SENTINEL, your local AI assistant. I'm currently running in **fallback mode** while the built-in AI model is loading or downloading.\n\nIn the meantime, I can still monitor your system, launch apps, and manage files.";
    } else if (lastMessage.includes('system') || lastMessage.includes('cpu') || lastMessage.includes('ram') || lastMessage.includes('memory')) {
      response = "Certainly, sir. Please check the **System** tab in the sidebar to view real-time CPU, RAM, disk, and network statistics. I'm monitoring everything for you.";
    } else if (lastMessage.includes('who are you') || lastMessage.includes('what are you')) {
      response = "I am **SENTINEL** — Smart Engine for Natural Talk & Intelligent Local Execution. I'm a fully local AI assistant designed to make your PC feel alive. I run entirely on your machine — no cloud, no external servers, complete privacy.\n\nCurrently in fallback mode while the local AI model initializes.";
    } else if (lastMessage.includes('help') || lastMessage.includes('what can you do')) {
      response = "Here's what I can do, sir:\n\n• **Chat** — Full AI conversations\n• **System Monitor** — Real-time CPU, RAM, disk, GPU stats\n• **Launch Apps** — Open any application by name\n• **File Management** — Browse and organize files\n• **Screen Capture** — Take screenshots\n• **Reminders** — Set timers and schedules\n\nSwitch to the **System** tab to see your PC stats in real-time!";
    } else {
      response = "I appreciate the input, sir, but I'm currently operating in **fallback mode** while the local language model is loading. I can understand basic commands but not complex conversations yet.\n\nIn the meantime, try the **System** tab or ask me about what I can do.";
    }

    return { role: 'assistant', content: response };
  }

  _chatStreamFallback(messages, onToken, onEnd) {
    const result = this._chatFallback(messages);
    const words = result.content.split(' ');
    let i = 0;
    
    const interval = setInterval(() => {
      if (i < words.length) {
        onToken((i === 0 ? '' : ' ') + words[i]);
        i++;
      } else {
        clearInterval(interval);
        onEnd();
      }
    }, 25);
  }

  // ─── Helpers ────────────────────────────────────────────────
  _extractContent(responseText) {
    if (typeof responseText === 'string') return responseText.trim();
    if (Array.isArray(responseText)) {
      const lastMsg = responseText[responseText.length - 1];
      return lastMsg?.content || lastMsg?.text || JSON.stringify(lastMsg);
    }
    if (responseText?.content) return responseText.content;
    return String(responseText || '');
  }

  getStatus() {
    return {
      loaded: this.isLoaded,
      loading: this.isLoading,
      progress: this.loadProgress,
      model: this.mode === 'transformers' ? this.transformersModelId : 'fallback',
      mode: this.mode
    };
  }
}

module.exports = { LLMEngine };
