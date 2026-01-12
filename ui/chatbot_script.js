// Chatbot UI Script
// This handles the front-end interactions - backend integration to be implemented later

class ChatbotUI {
    constructor() {
        this.messagesArea = document.getElementById('messagesArea');
        this.userInput = document.getElementById('userInput');
        this.sendButton = document.getElementById('sendButton');
        
        this.initializeEventListeners();
        this.adjustTextareaHeight();
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

    handleSendMessage() {
        const message = this.userInput.value.trim();
        
        if (!message) return;

        // Add user message to chat
        this.addMessage(message, 'user');

        // Clear input
        this.userInput.value = '';
        this.adjustTextareaHeight();

        // Show typing indicator
        this.showTypingIndicator();

        // Simulate bot response (backend integration to be implemented)
        setTimeout(() => {
            this.hideTypingIndicator();
            this.addBotResponse(message);
        }, 1500);
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

    addBotResponse(userMessage) {
        // Placeholder response - backend integration to be implemented
        let response = this.generatePlaceholderResponse(userMessage);
        
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
        content.innerHTML = `<p>${response}</p>`;

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);

        this.messagesArea.appendChild(messageDiv);
        this.scrollToBottom();
    }

    generatePlaceholderResponse(userMessage) {
        // Temporary placeholder responses until backend is integrated
        const lowerMessage = userMessage.toLowerCase();
        
        if (lowerMessage.includes('market') || lowerMessage.includes('trend')) {
            return 'I can help you analyze market trends. This feature will be connected to real-time market data once the backend integration is complete.';
        } else if (lowerMessage.includes('risk')) {
            return 'Risk analysis is one of my key features. Once integrated with the backend, I\'ll provide detailed risk assessments for your portfolio.';
        } else if (lowerMessage.includes('news')) {
            return 'I can fetch the latest financial news for you. The news feed integration is ready and will be activated when the backend is connected.';
        } else if (lowerMessage.includes('stock') || lowerMessage.includes('aapl') || lowerMessage.includes('ticker')) {
            return 'I can analyze specific stocks and provide insights. This functionality will be available once we connect to the market data API.';
        } else {
            return 'Thank you for your question. I\'m currently in demo mode. Once the backend integration is complete, I\'ll be able to provide detailed analysis of markets, news, and risk assessments.';
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
