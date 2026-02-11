// Chatbot UI Script with FastAPI Backend Integration

// Use local backend for development, deployed backend for production
const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? 'http://localhost:8000' 
    : 'https://finsense-ktp7.onrender.com'; 

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
        
        // Load welcome message (async but fire-and-forget with error handling)
        this.loadWelcomeMessage().catch(error => {
            console.error('Error loading welcome message:', error);
            // Ensure fallback message shows even if promise rejection isn't caught
            this.addBotMessage('Welcome! Unable to connect to server. Please check your connection and try again.');
        });
    }
    
    async loadWelcomeMessage() {
        try {
            // Send empty message to get welcome with timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
            
            const response = await fetch(`${API_BASE_URL}/api/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    message: ''
                }),
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (!data || !data.bot_message) {
                throw new Error('Invalid response from server');
            }
            
            this.sessionId = data.session_id;
            this.currentState = data.state;
            this.addBotMessage(data.bot_message);
        } catch (error) {
            // If API fails, throw error to be caught by constructor's catch handler
            console.error('Welcome message API error:', error);
            throw error;
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
            // Simulate realistic progress updates
            await new Promise(resolve => setTimeout(resolve, 300));
            this.updateProgressMessage(this.progressMessageId, 'Pulling market data...');
            
            await new Promise(resolve => setTimeout(resolve, 400));
            this.updateProgressMessage(this.progressMessageId, 'Analyzing sector performance...');
            
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
            
            // Show risk analysis progress
            this.updateProgressMessage(this.progressMessageId, 'Evaluating risk profiles...');
            await new Promise(resolve => setTimeout(resolve, 300));
            
            const result = await response.json();
            
            // Update progress based on what was analyzed
            this.updateProgressMessage(this.progressMessageId, 'Analyzing market news & trends...');
            await new Promise(resolve => setTimeout(resolve, 400));
            
            this.updateProgressMessage(this.progressMessageId, 'Finding stock opportunities...');
            await new Promise(resolve => setTimeout(resolve, 400));
            
            this.updateProgressMessage(this.progressMessageId, 'Generating AI insights...');
            await new Promise(resolve => setTimeout(resolve, 500));
            
            // Remove progress message
            this.removeProgressMessage(this.progressMessageId);
            
            // Display results
            await this.displayResults(result.results.html);
            
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

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);
        this.messagesArea.appendChild(messageDiv);
        
        // User messages appear instantly, bot messages animate
        if (type === 'user') {
            content.innerHTML = `<p>${this.escapeHtml(text)}</p>`;
            this.scrollToBottom();
        } else {
            this.animateMessage(content, text);
        }
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
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);
        this.messagesArea.appendChild(messageDiv);
        
        // Animate the message appearing line by line
        this.animateMessage(content, message);
    }
    
    async animateMessage(contentElement, message) {
        // Convert markdown-like formatting to HTML
        const formattedMessage = this.formatMarkdown(message);
        
        // Create a temporary element to parse the HTML
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = formattedMessage;
        
        // Split into lines/paragraphs for line-by-line display
        const elements = Array.from(tempDiv.children);
        
        if (elements.length === 0) {
            // Simple text without block elements
            contentElement.innerHTML = formattedMessage;
            this.scrollToBottom();
            return;
        }
        
        // Display each element with a delay
        for (let i = 0; i < elements.length; i++) {
            const element = elements[i].cloneNode(true);
            element.style.opacity = '0';
            element.style.transform = 'translateY(10px)';
            element.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            
            contentElement.appendChild(element);
            
            // Trigger animation
            await new Promise(resolve => setTimeout(resolve, 50));
            element.style.opacity = '1';
            element.style.transform = 'translateY(0)';
            
            this.scrollToBottom();
            
            // Wait before showing next line (shorter delay for list items)
            const delay = element.tagName === 'LI' ? 100 : 200;
            await new Promise(resolve => setTimeout(resolve, delay));
        }
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
        
        // Fade in animation
        messageDiv.style.opacity = '0';
        messageDiv.style.transform = 'translateY(10px)';
        messageDiv.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        
        setTimeout(() => {
            messageDiv.style.opacity = '1';
            messageDiv.style.transform = 'translateY(0)';
            this.scrollToBottom();
        }, 50);
        
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
    
    async displayResults(htmlContent) {
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

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);
        this.messagesArea.appendChild(messageDiv);
        
        // Parse HTML and animate sections
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = htmlContent;
        
        // Get all result-section divs
        const sections = tempDiv.querySelectorAll('.result-section');
        
        if (sections.length === 0) {
            // No sections, display all at once with simple fade
            content.innerHTML = htmlContent;
            this.scrollToBottom();
            return;
        }
        
        // Display each section with a delay
        for (let section of sections) {
            section.style.opacity = '0';
            section.style.transform = 'translateY(10px)';
            section.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            
            content.appendChild(section);
            
            // Trigger animation
            await new Promise(resolve => setTimeout(resolve, 50));
            section.style.opacity = '1';
            section.style.transform = 'translateY(0)';
            
            this.scrollToBottom();
            
            // Wait before showing next section
            await new Promise(resolve => setTimeout(resolve, 300));
        }
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
