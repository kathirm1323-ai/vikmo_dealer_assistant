/**
 * VIKMO Dealer Assistant — Frontend Logic
 *
 * Handles:
 * - Session management (UUID)
 * - Chat message rendering with markdown, timestamps
 * - Custom rendering for product cards and order confirmations
 * - API communication
 * - Auto-scroll, loading states
 * - Sidebar mobile toggle
 */

// ---------------------------------------------------------------------------
// Config & State
// ---------------------------------------------------------------------------
const API_BASE = window.location.origin;
let sessionId = generateUUID();
let isLoading = false;

// ---------------------------------------------------------------------------
// DOM Elements
// ---------------------------------------------------------------------------
const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('btn-send');
const welcomeScreen = document.getElementById('welcome-screen');
const newChatBtn = document.getElementById('btn-new-chat');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Advanced markdown-to-HTML converter
 * Detects patterns like "Stock Check Result:" and formats them as cards
 */
function renderMarkdown(text) {
    let html = escapeHtml(text);

    // 1. Detect and parse Product/Stock Cards
    // Example: Stock Check Result:
    // - SKU: SKU001
    // - Product: Premium Brake Pad
    // - Available Stock: 120 units
    // - Status: In Stock
    const stockRegex = /Stock Check Result:\n-\s*SKU:\s*(.+)\n-\s*Product:\s*(.+)\n-\s*Available Stock:\s*(.+)\n-\s*Status:\s*(.+)/g;
    html = html.replace(stockRegex, (match, sku, product, stock, status) => {
        const isOut = status.toLowerCase().includes('out');
        const badgeClass = isOut ? 'out-of-stock' : 'in-stock';
        const badgeIcon = isOut ? '⚠️' : '✅';
        return `
            <div class="product-card">
                <div class="product-card-header">
                    <span class="product-card-name">${product}</span>
                    <span class="product-card-sku">${sku}</span>
                </div>
                <div class="product-card-details">
                    <span class="stock-badge ${badgeClass}">${badgeIcon} ${status} (${stock})</span>
                </div>
            </div>
        `;
    });

    // Detect general products in lists
    // Example: - [IN STOCK] Premium Brake Pad (SKU: SKU001) \n Brand: Brembo | Category: Brake | Price: Rs.850 | Stock: 120 units
    const productListRegex = /-\s*\[(IN STOCK|OUT OF STOCK)\]\s*(.+?)\s*\(SKU:\s*(.+?)\)\n\s*Brand:\s*(.+?)\s*\|\s*Category:\s*(.+?)\s*\|\s*Price:\s*(.+?)\s*\|\s*Stock:\s*(.+?)(?=\n|$)/g;
    html = html.replace(productListRegex, (match, statusStr, name, sku, brand, category, price, stock) => {
        const isOut = statusStr === 'OUT OF STOCK';
        const badgeClass = isOut ? 'out-of-stock' : 'in-stock';
        const badgeIcon = isOut ? '⚠️' : '✅';
        return `
            <div class="product-card">
                <div class="product-card-header">
                    <span class="product-card-name">${name}</span>
                    <span class="product-card-sku">${sku}</span>
                </div>
                <div class="product-card-details">
                    <span class="product-card-price">${price}</span>
                    <span class="stock-badge ${badgeClass}">${badgeIcon} ${stock}</span>
                </div>
                <div style="font-size: var(--font-xs); color: var(--text-muted); margin-top: 8px;">
                    ${brand} • ${category}
                </div>
            </div>
        `;
    });

    // 2. Detect and parse Order Confirmation
    const orderRegex = /Order Confirmed!\n-\s*Order ID:\s*(.+)\n-\s*Dealer:\s*(.+)\n-\s*Status:\s*(.+)\nItems:((?:\n\s+-.*)+)\nTotal Amount:\s*(.+)/g;
    html = html.replace(orderRegex, (match, orderId, dealer, status, itemsText, total) => {
        let itemsHtml = itemsText.split('\n')
            .filter(line => line.trim().startsWith('-'))
            .map(line => `<li>${line.trim().substring(1).trim()}</li>`)
            .join('');
        
        return `
            <div class="order-confirmation">
                <div class="order-confirmation-header">
                    <div class="order-confirmation-icon">🎉</div>
                    <div class="order-confirmation-title">Order Confirmed</div>
                </div>
                <div style="font-size: var(--font-sm); margin-bottom: 12px;">
                    <strong>ID:</strong> ${orderId} <br>
                    <strong>Dealer:</strong> ${dealer}
                </div>
                <ul style="font-size: var(--font-sm); margin-bottom: 12px; margin-top: 0;">
                    ${itemsHtml}
                </ul>
                <div style="font-size: var(--font-md); font-weight: 700; color: var(--text-primary);">
                    Total: ${total}
                </div>
            </div>
        `;
    });

    // Basic Markdown
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Bullet lists (only if not already converted to cards)
    html = html.replace(/^[\s]*[-*]\s+(?!<div)(.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    html = html.replace(/<\/ul>\s*<ul>/g, '');

    // Paragraphs
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';
    html = html.replace(/\n/g, '<br>');
    
    // Clean up empty paragraphs
    html = html.replace(/<p>\s*<\/p>/g, '');
    html = html.replace(/<p><br>/g, '<p>');

    return html;
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    });
}

function showInputInWelcome() {
    const welcomeScreen = document.getElementById('welcome-screen');
    const inputArea = document.getElementById('chat-input-area');
    const welcomeCards = document.querySelector('.welcome-cards');
    if (welcomeScreen && inputArea && welcomeCards) {
        welcomeScreen.insertBefore(inputArea, welcomeCards);
        inputArea.classList.add('welcome-layout');
    }
}

function showInputAtBottom() {
    const chatMain = document.querySelector('.chat-main');
    const inputArea = document.getElementById('chat-input-area');
    if (chatMain && inputArea && inputArea.parentNode !== chatMain) {
        chatMain.appendChild(inputArea);
        inputArea.classList.remove('welcome-layout');
    }
}

// ---------------------------------------------------------------------------
// Message Rendering
// ---------------------------------------------------------------------------

function addMessage(role, content, sources = []) {
    if (welcomeScreen && welcomeScreen.style.display !== 'none') {
        showInputAtBottom();
        welcomeScreen.style.display = 'none';
    }

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.textContent = role === 'user' ? 'U' : 'V';

    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'message-bubble';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (role === 'user') {
        contentDiv.innerHTML = `<p>${escapeHtml(content)}</p>`;
    } else {
        contentDiv.innerHTML = renderMarkdown(content);
    }

    if (sources && sources.length > 0 && role === 'assistant') {
        const sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'sources-badge';
        sourcesDiv.innerHTML = `📋 Sources: ${sources.join(', ')}`;
        contentDiv.appendChild(sourcesDiv);
    }

    bubbleDiv.appendChild(contentDiv);

    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-timestamp';
    timeDiv.textContent = getCurrentTime();
    bubbleDiv.appendChild(timeDiv);

    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(bubbleDiv);
    chatMessages.appendChild(msgDiv);

    scrollToBottom();
    return msgDiv;
}

function addTypingIndicator() {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message assistant';
    msgDiv.id = 'typing-indicator';

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.textContent = 'V';

    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'message-bubble';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content typing-indicator';
    contentDiv.innerHTML = `
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
    `;

    bubbleDiv.appendChild(contentDiv);
    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(bubbleDiv);
    chatMessages.appendChild(msgDiv);

    scrollToBottom();
    return msgDiv;
}

function removeTypingIndicator() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
}

function addErrorMessage(text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message assistant error';

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.textContent = '!';

    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'message-bubble';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = `<p>${escapeHtml(text)}</p>`;

    bubbleDiv.appendChild(contentDiv);
    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(bubbleDiv);
    chatMessages.appendChild(msgDiv);

    scrollToBottom();
}

// ---------------------------------------------------------------------------
// API Communication
// ---------------------------------------------------------------------------

async function sendMessage(text) {
    if (isLoading || !text.trim()) return;

    isLoading = true;
    sendBtn.disabled = true;

    addMessage('user', text.trim());
    const typingEl = addTypingIndicator();

    try {
        const response = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                message: text.trim(),
            }),
        });

        removeTypingIndicator();

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Server error (${response.status})`);
        }

        const data = await response.json();
        addMessage('assistant', data.response, data.sources);
    } catch (error) {
        removeTypingIndicator();
        addErrorMessage(`Failed to get response: ${error.message}. Make sure the backend is running.`);
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

// ---------------------------------------------------------------------------
// Event Handlers
// ---------------------------------------------------------------------------

sendBtn.addEventListener('click', () => {
    const text = messageInput.value;
    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendMessage(text);
});

messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const text = messageInput.value;
        messageInput.value = '';
        messageInput.style.height = 'auto';
        sendMessage(text);
    }
});

messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
});
if (newChatBtn) {
    newChatBtn.addEventListener('click', async () => {
        try {
            await fetch(`${API_BASE}/api/reset`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId }),
            });
        } catch (e) {}

        sessionId = generateUUID();
        chatMessages.innerHTML = '';
        
        if (welcomeScreen) {
            chatMessages.appendChild(welcomeScreen);
            welcomeScreen.style.display = '';
            showInputInWelcome();
        }

        messageInput.value = '';
        messageInput.focus();
    });
}

document.querySelectorAll('.action-card').forEach((btn) => {
    btn.addEventListener('click', () => {
        const prompt = btn.getAttribute('data-prompt');
        if (prompt) {
            messageInput.value = '';
            sendMessage(prompt);
            if (window.innerWidth <= 900) {
                closeSidebar();
            }
        }
    });
});

document.querySelectorAll('.welcome-card').forEach((card) => {
    card.addEventListener('click', () => {
        const prompt = card.getAttribute('data-prompt');
        if (prompt) {
            messageInput.value = '';
            sendMessage(prompt);
        }
    });
});

document.querySelectorAll('.category-item').forEach((item) => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.category-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        const text = item.textContent.trim();
        messageInput.value = '';
        sendMessage(`Show me parts in the ${text} category`);
    });
});

// Sidebar Mobile Toggle
function openSidebar() {
    sidebar.classList.add('open');
    sidebarOverlay.classList.add('visible');
}

function closeSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('visible');
}

if (sidebarToggle) sidebarToggle.addEventListener('click', openSidebar);
if (sidebarOverlay) sidebarOverlay.addEventListener('click', closeSidebar);

// ---------------------------------------------------------------------------
// Initialize
// ---------------------------------------------------------------------------
showInputInWelcome();
messageInput.focus();
console.log('🚀 VIKMO Dealer Assistant loaded (Redesigned). Session:', sessionId);
