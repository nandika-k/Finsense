// Chatbot UI Script with FastAPI Backend Integration

// Use local backend for development, deployed backend for production
const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? 'http://localhost:8000' 
    : 'https://finsense-ktp7.onrender.com'; 

const AUTH0_CONFIG = window.FINSENSE_AUTH0 || {
    domain: '',
    clientId: '',
    audience: ''
};

// Check for Flask auth mode
const FLASK_AUTH_MODE = window.FINSENSE_AUTH_MODE === 'flask';
const FLASK_USER = window.FINSENSE_USER || null;

function hasAuthConfig() {
    // If Flask auth mode, consider auth enabled if user is present
    if (FLASK_AUTH_MODE) {
        return true;
    }
    return Boolean(AUTH0_CONFIG.domain && AUTH0_CONFIG.clientId && AUTH0_CONFIG.audience);
}

function buildAuthHeaders(accessToken) {
    const headers = {
        'Content-Type': 'application/json',
    };

    if (accessToken) {
        headers.Authorization = `Bearer ${accessToken}`;
    }

    return headers;
}

class ChatbotUI {
    constructor() {
        this.messagesArea = document.getElementById('messagesArea');
        this.userInput = document.getElementById('userInput');
        this.sendButton = document.getElementById('sendButton');
        this.loginButton = document.getElementById('loginButton');
        this.logoutButton = document.getElementById('logoutButton');
        this.authStatus = document.getElementById('authStatus');
        
        // Modal elements (may not exist in Flask mode)
        this.loginModal = document.getElementById('loginModal');
        this.modalCloseBtn = document.getElementById('modalCloseBtn');
        this.popupLoginBtn = document.getElementById('popupLoginBtn');
        this.guestContinueBtn = document.getElementById('guestContinueBtn');
        this.loginStatus = document.getElementById('loginStatus');
        
        this.sessionId = null;
        this.currentState = 'initial';
        this.progressMessageId = null;
        this.auth0Client = null;
        this.accessToken = null;
        this.userId = null;
        this.isAuthenticated = false;
        this.isGuest = false;
        this.authEnabled = hasAuthConfig();
        
        this.initializeEventListeners();
        this.adjustTextareaHeight();

        this.setInputEnabled(false);

        this.initialize().catch(error => {
            console.error('Error loading welcome message:', error);
            this.addBotMessage('Welcome! Unable to connect to server. Please check your connection and try again.');
        });
    }

    async initialize() {
        await this.initializeAuth();

        if (!this.authEnabled || this.isAuthenticated) {
            await this.loadWelcomeMessage();
            return;
        }

        this.addBotMessage('Please log in to start using Finsense.');
    }

    async initializeAuth() {
        // Flask session-based auth
        if (FLASK_AUTH_MODE && FLASK_USER) {
            this.isAuthenticated = true;
            this.userId = FLASK_USER.sub;
            this.setInputEnabled(true);
            console.log('Flask auth: User authenticated as', FLASK_USER.name);
            return;
        }
        
        if (!this.authEnabled) {
            if (this.authStatus) this.authStatus.textContent = 'Auth disabled (dev mode)';
            this.loginButton.style.display = 'none';
            this.logoutButton.style.display = 'none';
            this.setInputEnabled(true);
            return;
        }

        if (typeof window.createAuth0Client !== 'function') {
            this.authStatus.textContent = 'Auth unavailable';
            throw new Error('Auth0 SDK failed to load');
        }

        this.auth0Client = await window.createAuth0Client({
            domain: AUTH0_CONFIG.domain,
            clientId: AUTH0_CONFIG.clientId,
            authorizationParams: {
                audience: AUTH0_CONFIG.audience,
                redirect_uri: `${window.location.origin}${window.location.pathname}`,
            },
            cacheLocation: 'localstorage',
            useRefreshTokens: true,
        });

        const query = window.location.search;
        if (query.includes('code=') && query.includes('state=')) {
            await this.auth0Client.handleRedirectCallback();
            window.history.replaceState({}, document.title, window.location.pathname);
        }

        this.isAuthenticated = await this.auth0Client.isAuthenticated();
        if (this.isAuthenticated) {
            this.accessToken = await this.auth0Client.getTokenSilently();
        }

        this.updateAuthUI();
    }

    updateAuthUI() {
        if (!this.authEnabled) {
            return;
        }

        const showLogin = !this.isAuthenticated && !this.isGuest;
        const showLogout = this.isAuthenticated;
        
        this.loginButton.style.display = showLogin ? 'inline-block' : 'none';
        this.logoutButton.style.display = showLogout ? 'inline-block' : 'none';
        
        if (this.isAuthenticated) {
            this.authStatus.textContent = 'Signed in';
        } else if (this.isGuest) {
            this.authStatus.textContent = 'Guest mode';
        } else {
            this.authStatus.textContent = 'Signed out';
        }
        
        this.setInputEnabled(this.isAuthenticated || this.isGuest);
    }

    async login() {
        // Open the login modal instead of redirecting
        this.openLoginModal();
    }
    
    openLoginModal() {
        if (this.loginModal) {
            this.loginModal.style.display = 'flex';
            this.setLoginStatus('', '');
        }
    }
    
    closeLoginModal() {
        if (this.loginModal) {
            this.loginModal.style.display = 'none';
            this.setLoginStatus('', '');
        }
    }
    
    setLoginStatus(message, type) {
        if (this.loginStatus) {
            this.loginStatus.textContent = message;
            this.loginStatus.className = 'login-status' + (type ? ' ' + type : '');
        }
    }
    
    async loginWithPopup() {
        if (!this.auth0Client) {
            this.setLoginStatus('Authentication not available', 'error');
            return;
        }
        
        // Disable the login button and show loading
        if (this.popupLoginBtn) {
            this.popupLoginBtn.disabled = true;
            this.popupLoginBtn.innerHTML = '<span class="modal-spinner"></span> Signing in...';
        }
        this.setLoginStatus('Opening login window...', 'loading');
        
        try {
            await this.auth0Client.loginWithPopup({
                authorizationParams: {
                    audience: AUTH0_CONFIG.audience,
                },
            });
            
            // Get user info and token
            this.isAuthenticated = await this.auth0Client.isAuthenticated();
            
            if (this.isAuthenticated) {
                this.accessToken = await this.auth0Client.getTokenSilently();
                const user = await this.auth0Client.getUser();
                this.userId = user?.sub || null;
                
                this.setLoginStatus('Login successful!', 'success');
                this.updateAuthUI();
                
                // Close modal after a brief delay to show success message
                setTimeout(() => {
                    this.closeLoginModal();
                    this.loadWelcomeMessage();
                    this.loadChatHistory();
                }, 800);
            }
        } catch (error) {
            console.error('Popup login failed:', error);
            
            if (error.message?.includes('Popup closed')) {
                this.setLoginStatus('Login cancelled', 'error');
            } else if (error.message?.includes('popup')) {
                this.setLoginStatus('Popup blocked. Please allow popups and try again.', 'error');
            } else {
                this.setLoginStatus('Login failed. Please try again.', 'error');
            }
        } finally {
            // Re-enable the login button
            if (this.popupLoginBtn) {
                this.popupLoginBtn.disabled = false;
                this.popupLoginBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
                        <polyline points="10 17 15 12 10 7"/>
                        <line x1="15" y1="12" x2="3" y2="12"/>
                    </svg>
                    Continue with Auth0
                `;
            }
        }
    }
    
    async continueAsGuest() {
        this.isGuest = true;
        this.userId = 'guest-' + Date.now();
        this.updateAuthUI();
        this.closeLoginModal();
        await this.loadWelcomeMessage();
    }
    
    async loadChatHistory() {
        if (!this.isAuthenticated || !this.accessToken) {
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE_URL}/api/history`, {
                method: 'GET',
                headers: this.getHeaders(),
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.messages && data.messages.length > 0) {
                    // Display historical messages
                    for (const msg of data.messages) {
                        if (msg.role === 'user') {
                            this.addMessage(msg.message, 'user');
                        } else {
                            this.addBotMessage(msg.message, false); // false = no animation
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Failed to load chat history:', error);
        }
    }

    async logout() {
        if (!this.auth0Client) {
            return;
        }

        this.auth0Client.logout({
            logoutParams: {
                returnTo: `${window.location.origin}${window.location.pathname}`,
            },
        });
    }

    getHeaders() {
        // Flask auth mode doesn't need Bearer token - session-based
        if (FLASK_AUTH_MODE) {
            return { 'Content-Type': 'application/json' };
        }
        
        if (this.authEnabled && !this.accessToken && !this.isGuest) {
            throw new Error('Please log in first.');
        }

        return buildAuthHeaders(this.accessToken);
    }
    
    async loadWelcomeMessage() {
        try {
            // Send empty message to get welcome with timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
            
            const response = await fetch(`${API_BASE_URL}/api/chat`, {
                method: 'POST',
                headers: this.getHeaders(),
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
        // Auth buttons (may not exist in Flask mode)
        if (this.loginButton) {
            this.loginButton.addEventListener('click', () => this.login());
        }
        if (this.logoutButton) {
            this.logoutButton.addEventListener('click', () => this.logout());
        }

        // Modal event listeners
        if (this.modalCloseBtn) {
            this.modalCloseBtn.addEventListener('click', () => this.closeLoginModal());
        }
        if (this.popupLoginBtn) {
            this.popupLoginBtn.addEventListener('click', () => this.loginWithPopup());
        }
        if (this.guestContinueBtn) {
            this.guestContinueBtn.addEventListener('click', () => this.continueAsGuest());
        }
        // Close modal when clicking outside
        if (this.loginModal) {
            this.loginModal.addEventListener('click', (e) => {
                if (e.target === this.loginModal) {
                    this.closeLoginModal();
                }
            });
        }

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
            headers: this.getHeaders(),
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
                headers: this.getHeaders(),
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

    addBotMessage(message, animate = true) {
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
        
        if (animate) {
            // Animate the message appearing line by line
            this.animateMessage(content, message);
        } else {
            // Instant display for history messages
            content.innerHTML = this.formatMarkdown(message);
            this.scrollToBottom();
        }
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
