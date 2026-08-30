/**
 * SENTINEL — Chat Interface
 * Handles message rendering, input, streaming, and markdown parsing
 */

class ChatInterface {
  constructor() {
    this.messagesContainer = document.getElementById('chat-messages');
    this.chatInput = document.getElementById('chat-input');
    this.sendBtn = document.getElementById('btn-send');
    this.voiceBtn = document.getElementById('btn-voice');
    this.statusText = document.getElementById('sentinel-status-text');

    this.messages = []; // Conversation history for AI context
    this.isStreaming = false;
    this.currentStreamEl = null;

    this._bindEvents();
    this._setupStreamListeners();
    this._initializeMemory();
  }

  async _initializeMemory() {
    this._connectWebSocket();
    this._pollEngineStatus();
  }

  _pollEngineStatus() {
    setInterval(async () => {
      try {
        const response = await fetch('http://localhost:8000/health');
        if (response.ok) {
          const data = await response.json();
          const indicator = document.getElementById('engine-indicator');
          if (indicator) {
            indicator.textContent = data.engine_status;
            if (data.engine_status === 'GPU') {
              indicator.style.color = '#00ff00';
            } else if (data.engine_status.includes('CPU')) {
              indicator.style.color = 'var(--accent-cyan)';
            } else {
              indicator.style.color = 'var(--text-secondary)';
            }
          }
        }
      } catch (e) {
        // Silently ignore polling errors
      }
    }, 5000);
  }

  async _connectWebSocket() {
    if (this.ws) {
      this.ws.close();
    }
    // Get secure session token
    let token = '';
    try {
      token = await window.sentinel.auth.getSessionToken();
    } catch (e) {
      console.error('Failed to get session token', e);
    }

    this.ws = new WebSocket(`ws://localhost:8000/ws/chat?token=${token}`);

    this.ws.onopen = () => {
      this.addSystemMessage('Connected to SENTINEL Secure Backend.');
      this._setInputEnabled(true);
      if (window.app?.orb) window.app.orb.setState('idle');
    };
    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this._handleWebSocketMessage(msg);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };
    this.ws.onclose = () => {
      this.addSystemMessage('Connection to backend lost. Reconnecting in 3 seconds...');
      this._setInputEnabled(false);
      setTimeout(() => this._connectWebSocket(), 3000);
    };
    this.ws.onerror = (error) => {
      console.error('WebSocket Error:', error);
      if (window.app?.orb) window.app.orb.setState('error');
    };
  }

  _bindEvents() {
    // Send button
    this.sendBtn.addEventListener('click', () => this.sendMessage());

    // Enter to send, Shift+Enter for newline
    this.chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    // Auto-resize textarea
    this.chatInput.addEventListener('input', () => {
      this.chatInput.style.height = 'auto';
      this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 120) + 'px';
    });

    // Voice button (placeholder for Phase 2)
    this.voiceBtn.addEventListener('click', () => {
      this.addSystemMessage('🎙️ Voice input coming in Phase 2. Stay tuned, sir.');
    });
  }

  _handleWebSocketMessage(msg) {
    switch (msg.type) {
      case 'status':
        this.addSystemMessage(msg.message);
        break;
      case 'error':
        this.addAssistantMessage(`[ERROR] ${msg.message}`);
        this._removeTypingIndicator();
        this._setInputEnabled(true);
        if (window.app?.orb) window.app.orb.setState('idle');
        break;
      case 'reply_start':
        this.isStreaming = true;
        this.currentStreamContent = '';
        this.currentStreamEl = this._createMessageElement('assistant', '');
        this.messagesContainer.appendChild(this.currentStreamEl);
        this._removeTypingIndicator();
        if (window.app?.orb) window.app.orb.setState('speaking');
        break;

      case 'reply_chunk':
        if (this.currentStreamEl) {
          this.currentStreamContent += msg.token;
          this.currentStreamEl.querySelector('.message-text').innerHTML =
            this._parseMarkdown(this.currentStreamContent);
          this._scrollToBottom();
        }
        break;
      case 'reply_end':
        this.isStreaming = false;
        this.currentStreamEl = null;
        this._setInputEnabled(true);
        if (window.app?.orb) window.app.orb.setState('idle');
        break;
      case 'tool_confirmation_required':
        this._showConfirmationModal(msg.data);
        break;
    }
  }

  async sendMessage() {
    const text = this.chatInput.value.trim();
    if (!text || this.isStreaming) return;
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.addSystemMessage('Cannot send message: Not connected to backend.');
      return;
    }

    // Add user message to UI
    this.addUserMessage(text);
    // Clear input
    this.chatInput.value = '';
    this.chatInput.style.height = 'auto';

    // Show typing indicator
    this._setInputEnabled(false);
    this._showTypingIndicator();

    if (window.app?.orb) window.app.orb.setState('thinking');

    // Send payload
    this.ws.send(JSON.stringify({ text: text, voice_enabled: false }));
  }

  _showConfirmationModal(data) {
    const modal = document.getElementById('tool-modal');
    if (!modal) return;

    const token = data.token;
    const preview = data.action_preview;

    // Safely assign textContent to prevent XSS
    document.getElementById('modal-tool-title').textContent = preview.title || preview.tool;
    document.getElementById('modal-purpose').textContent = preview.purpose || 'System operation';
    document.getElementById('modal-target').textContent = preview.target || 'System resources';

    const riskBadge = document.getElementById('modal-risk-tier');
    riskBadge.textContent = preview.risk;
    document.getElementById('modal-risk-desc').textContent = preview.risk_explanation || '';

    document.getElementById('modal-effect').textContent = preview.expected_effect || '';
    document.getElementById('modal-reversible').textContent = preview.is_reversible ? 'Yes' : 'No';

    // Color coding for risk tier
    if (preview.risk === 'TIER_3' || preview.risk === 'TIER_4') {
      riskBadge.style.color = 'var(--accent-red)';
      riskBadge.style.borderColor = 'var(--accent-red)';
    } else {
      riskBadge.style.color = 'var(--accent-cyan)';
      riskBadge.style.borderColor = 'var(--accent-cyan)';
    }

    document.getElementById('modal-args').textContent = JSON.stringify(preview.args, null, 2);
    // Start Countdown
    let timeLeft = 120;
    const timerEl = document.getElementById('modal-countdown');
    timerEl.textContent = timeLeft;
    const timerInterval = setInterval(() => {
      timeLeft--;
      timerEl.textContent = timeLeft;
      if (timeLeft <= 0) {
        clearInterval(timerInterval);
        this._closeModal();
      }
    }, 1000);

    // Attach event listeners for buttons
    const btnApprove = document.getElementById('btn-approve-tool');
    const btnReject = document.getElementById('btn-reject-tool');

    // Clear existing listeners
    const newBtnApprove = btnApprove.cloneNode(true);
    const newBtnReject = btnReject.cloneNode(true);
    btnApprove.parentNode.replaceChild(newBtnApprove, btnApprove);
    btnReject.parentNode.replaceChild(newBtnReject, btnReject);

    newBtnReject.addEventListener('click', () => {
      clearInterval(timerInterval);
      this.addSystemMessage(`Action rejected by user.`);
      this._closeModal();
      this._setInputEnabled(true);
    });

    newBtnApprove.addEventListener('click', async () => {
      clearInterval(timerInterval);
      newBtnApprove.disabled = true;
      newBtnApprove.textContent = 'Approving...';

      try {
        const sessionToken = await window.sentinel.auth.getSessionToken();
        const response = await fetch('http://localhost:8000/api/tools/confirm', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Sentinel-Session': sessionToken
          },
          body: JSON.stringify({
            token: token,
            tool_name: preview.tool,
            args: preview.args,
            session_id: "Websocket Session" // TODO: Use actual session ID or let backend infer
          })
        });

        const result = await response.json();
        if (result.status === 'error') {
          this.addAssistantMessage(`[ERROR] ${result.message}`);
        } else {
          // Success! Backend will usually handle continuing the chat loop, or we trigger it.
          this.addSystemMessage(`Action ${preview.tool} executed successfully.`);

          // Force a followup by sending a hidden message to the websocket
          this.ws.send(JSON.stringify({ text: "Tool executed successfully. Summarize the results." }));
        }
      } catch (err) {
        this.addAssistantMessage(`[ERROR] Failed to contact backend: ${err.message}`);
      }

      newBtnApprove.disabled = false;
      newBtnApprove.textContent = 'Approve Action';
      this._closeModal();
    });

    modal.classList.remove('hidden');
  }

  _closeModal() {
    const modal = document.getElementById('tool-modal');
    if (modal) modal.classList.add('hidden');
  }

  addUserMessage(text) {
    const el = this._createMessageElement('user', text);
    this.messagesContainer.appendChild(el);
    this._scrollToBottom();
  }

  addAssistantMessage(text) {
    const el = this._createMessageElement('assistant', text);
    this.messagesContainer.appendChild(el);
    this.messages.push({ role: 'assistant', content: text });
    this._scrollToBottom();
  }

  addSystemMessage(text) {
    const el = document.createElement('div');
    el.className = 'message system';
    el.innerHTML = `<div class="message-content">${text}</div>`;
    this.messagesContainer.appendChild(el);
    this._scrollToBottom();
  }

  _createMessageElement(role, text) {
    const el = document.createElement('div');
    el.className = `message ${role}`;

    const avatarText = role === 'user' ? 'U' : 'S';
    const time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

    el.innerHTML = `
      <div class="message-avatar">${avatarText}</div>
      <div class="message-content">
        <div class="message-text">${this._parseMarkdown(text)}</div>
        <div class="message-time">${time}</div>
      </div>
    `;

    return el;
  }

  _parseMarkdown(text) {
    if (!text) return '';

    // Simple markdown parser (no external dependency needed for basic formatting)
    let html = text
      // Escape HTML
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      // Code blocks
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
      // Inline code
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      // Bold
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      // Italic
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      // Links
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
      // Line breaks
      .replace(/\n/g, '<br>');

    // Wrap in paragraphs (simple)
    if (!html.includes('<pre>') && !html.includes('<br>')) {
      html = `<p>${html}</p>`;
    }

    return html;
  }

  _showTypingIndicator() {
    const el = document.createElement('div');
    el.className = 'message assistant';
    el.id = 'typing-indicator';
    el.innerHTML = `
      <div class="message-avatar">S</div>
      <div class="message-content">
        <div class="typing-indicator">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      </div>
    `;
    this.messagesContainer.appendChild(el);
    this._scrollToBottom();
  }

  _removeTypingIndicator() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
  }

  _scrollToBottom() {
    requestAnimationFrame(() => {
      this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    });
  }

  _setInputEnabled(enabled) {
    this.chatInput.disabled = !enabled;
    this.sendBtn.disabled = !enabled;
    this.sendBtn.style.opacity = enabled ? '1' : '0.5';
  }
}

// Export globally
window.ChatInterface = ChatInterface;
