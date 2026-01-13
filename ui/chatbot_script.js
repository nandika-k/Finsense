// Chatbot UI Script with FastAPI Backend Integration

const API_BASE_URL = 'https://finsense-ktp7.onrender.com'; 

class ChatbotUI {
    constructor() {
        this.messagesArea = document.getElementById('messagesArea');
        this.userInput = document.getElementById('userInput');
        this.sendButton = document.getElementById('sendButton');
        this.sessionId = null;
        this.currentState = 'initial';
        this.progressMessageId = null;
        
        this.initializeEventListeners();
        this.adjustTextareaHeight();
        this.loadWelcomeMessage();
    }
    
    async loadWelcomeMessage() {
        try {
            // Send empty message to get welcome
            const response = await this.sendChatMessage('');
            this.sessionId = response.session_id;
            this.currentState = response.state;
            this.addBotMessage(response.bot_message);
        } catch (error) {
            // Fallback welcome message if API fails
            this.addBotMessage('Welcome! Unable to connect to server. Please check your connection and try again.');
        }
    }

    initializeEventListeners() {
        // Send button click
        this.sendButton.addEventListener('click', () => this.handleSendMessage());

        // Enter key to send (Shift+Enter for new line)
        this.userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSendMessage();
            }
        });

        // Auto-resize textarea
        this.userInput.addEventListener('input', () => this.adjustTextareaHeight());
    }

    adjustTextareaHeight() {
        this.userInput.style.height = 'auto';
        this.userInput.style.height = this.userInput.scrollHeight + 'px';
    }

    async handleSendMessage() {
        const message = this.userInput.value.trim();
        
        if (!message) return;

        // Disable input while processing
        this.setInputEnabled(false);

        // Add user message to chat
        this.addMessage(message, 'user');

        // Clear input
        this.userInput.value = '';
        this.adjustTextareaHeight();

        // Show typing indicator
        this.showTypingIndicator();

        try {
            // Send message to backend
            const response = await this.sendChatMessage(message);
            
            this.hideTypingIndicator();
            
            // Update session and state
            this.sessionId = response.session_id;
            this.currentState = response.state;
            
            // Add bot response
            this.addBotMessage(response.bot_message);
            
            // If ready to research, trigger research
            if (response.state === 'ready_to_research') {
                await this.startResearch();
            }
            
        } catch (error) {
            this.hideTypingIndicator();
            this.addBotMessage(`Error: ${error.message}. Please try again.`);
        } finally {
            this.setInputEnabled(true);
            this.userInput.focus();
        }
    }
    
    async sendChatMessage(message) {
        const response = await fetch(`${API_BASE_URL}/api/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: this.sessionId,
                message: message
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    }
    
    async startResearch() {
        // Show progress message
        this.progressMessageId = this.addProgressMessage('Initializing research...');
        this.setInputEnabled(false);
        
        try {
            // Update progress
            this.updateProgressMessage(this.progressMessageId, 'Fetching market data...');
            
            // Trigger research
            const response = await fetch(`${API_BASE_URL}/api/research`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.sessionId
                })
            });
            
            if (!response.ok) {
                throw new Error(`Research failed: ${response.status}`);
            }
            
            const result = await response.json();
            
            // Update progress
            this.updateProgressMessage(this.progressMessageId, 'Analyzing sectors and risks...');
            
            // Wait a moment for dramatic effect
            await new Promise(resolve => setTimeout(resolve, 500));
            
            this.updateProgressMessage(this.progressMessageId, 'Generating insights...');
            await new Promise(resolve => setTimeout(resolve, 500));
            
            // Remove progress message
            this.removeProgressMessage(this.progressMessageId);
            
            // Display results
            this.displayResults(result.results.html);
            
            // Show completion message
            this.addBotMessage('Analysis complete! You can ask me to analyze different sectors or start a new analysis by sending me a message.');
            
        } catch (error) {
            this.removeProgressMessage(this.progressMessageId);
            this.addBotMessage(`Research failed: ${error.message}. Please try again.`);
        } finally {
            this.setInputEnabled(true);
        }
    }
    
    setInputEnabled(enabled) {
        this.userInput.disabled = !enabled;
        this.sendButton.disabled = !enabled;
    }

    addMessage(text, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        
        if (type === 'user') {
            avatar.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                </svg>
            `;
        } else {
            avatar.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                    <path d="M2 17l10 5 10-5"/>
                    <path d="M2 12l10 5 10-5"/>
                </svg>
            `;
        }

        const content = document.createElement('div');
        content.className = 'message-content';
        content.innerHTML = `<p>${this.escapeHtml(text)}</p>`;

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);

        this.messagesArea.appendChild(messageDiv);
        this.scrollToBottom();
    }

    showTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message bot-message';
        typingDiv.id = 'typingIndicator';

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
            </svg>
        `;

        const content = document.createElement('div');
        content.className = 'message-content';
        content.innerHTML = `
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;

        typingDiv.appendChild(avatar);
        typingDiv.appendChild(content);

        this.messagesArea.appendChild(typingDiv);
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    addBotMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message';

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
            </svg>
        `;

        const content = document.createElement('div');
        content.className = 'message-content';
        
        // Convert markdown-like formatting to HTML
        const formattedMessage = this.formatMarkdown(message);
        content.innerHTML = formattedMessage;

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);

        this.messagesArea.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    formatMarkdown(text) {
        // Convert markdown-style formatting to HTML
        // Bold: **text** -> <strong>text</strong>
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Lists: lines starting with • or -
        text = text.replace(/^[•\-]\s+(.+)$/gm, '<li>$1</li>');
        
        // Wrap consecutive <li> items in <ul>
        text = text.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
        
        // Line breaks
        text = text.replace(/\n\n/g, '</p><p>');
        text = text.replace(/\n/g, '<br>');
        
        // Wrap in paragraph if not already wrapped
        if (!text.startsWith('<')) {
            text = `<p>${text}</p>`;
        }
        
        return text;
    }
    
    addProgressMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message progress-message';
        const messageId = 'progress-' + Date.now();
        messageDiv.id = messageId;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
            </svg>
        `;

        const content = document.createElement('div');
        content.className = 'message-content progress-content';
        content.innerHTML = `
            <div class="progress-indicator">
                <div class="spinner"></div>
                <span class="progress-text">${message}</span>
            </div>
        `;

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);

        this.messagesArea.appendChild(messageDiv);
        this.scrollToBottom();
        
        return messageId;
    }
    
    updateProgressMessage(messageId, newMessage) {
        const messageDiv = document.getElementById(messageId);
        if (messageDiv) {
            const progressText = messageDiv.querySelector('.progress-text');
            if (progressText) {
                progressText.textContent = newMessage;
            }
        }
    }
    
    removeProgressMessage(messageId) {
        const messageDiv = document.getElementById(messageId);
        if (messageDiv) {
            messageDiv.remove();
        }
    }
    
    displayResults(htmlContent) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message results-message';

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
            </svg>
        `;

        const content = document.createElement('div');
        content.className = 'message-content results-content';
        content.innerHTML = htmlContent;

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);

        this.messagesArea.appendChild(messageDiv);
        this.scrollToBottom();
    }

    scrollToBottom() {
        this.messagesArea.scrollTop = this.messagesArea.scrollHeight;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the chatbot UI when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new ChatbotUI();
});
