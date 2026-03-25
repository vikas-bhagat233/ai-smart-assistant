const API_BASE_URL = 'http://localhost:5000/api';
let currentChatId = null;
let currentMessages = [];
let currentChatTitle = 'New Chat';
let chatHistoryCache = [];
let currentSearch = '';
let isTyping = false;
let activeAbortController = null;
let uploadedDocument = null;
let responseTimerInterval = null;
let responseStartTime = null;
let groupsCache = [];
let currentGroupId = null;
let currentGroupName = '';
let lastAssistantReply = '';
let speechRecognition = null;
let isVoiceListening = false;
let socket = null;
const renderedGroupMessageIds = new Set();

const user = JSON.parse(localStorage.getItem('user') || '{}');
document.getElementById('usernameDisplay').textContent = user.username || 'User';

const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const newChatBtn = document.getElementById('newChatBtn');
const logoutBtn = document.getElementById('logoutBtn');
const themeToggle = document.getElementById('themeToggle');
const stopBtn = document.getElementById('stopBtn');
const regenerateBtn = document.getElementById('regenerateBtn');
const chatSearchInput = document.getElementById('chatSearchInput');
const attachDocBtn = document.getElementById('attachDocBtn');
const docInput = document.getElementById('docInput');
const uploadGroupImageBtn = document.getElementById('uploadGroupImageBtn');
const groupImageInput = document.getElementById('groupImageInput');
const createGroupBtn = document.getElementById('createGroupBtn');
const joinGroupBtn = document.getElementById('joinGroupBtn');
const exitGroupBtn = document.getElementById('exitGroupBtn');
const deleteGroupBtn = document.getElementById('deleteGroupBtn');
const groupList = document.getElementById('groupList');
const chatThemeSelect = document.getElementById('chatThemeSelect');
const createImageBtn = document.getElementById('createImageBtn');
const voiceInputBtn = document.getElementById('voiceInputBtn');
const voiceReadBtn = document.getElementById('voiceReadBtn');
const responseTimer = document.getElementById('responseTimer');
const responseTimerValue = document.getElementById('responseTimerValue');
const mobileMenuBtn = document.getElementById('mobileMenuBtn');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const sidebar = document.querySelector('.sidebar');

async function refreshAccessToken() {
    const refreshToken = localStorage.getItem('refreshToken');
    if (!refreshToken) {
        return false;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ refresh_token: refreshToken })
        });

        const data = await response.json();
        if (!response.ok) {
            return false;
        }

        localStorage.setItem('token', data.token);
        localStorage.setItem('refreshToken', data.refresh_token);
        localStorage.setItem('sessionId', data.session_id);
        localStorage.setItem('user', JSON.stringify(data.user));
        return true;
    } catch (error) {
        return false;
    }
}

async function authenticatedFetch(url, options = {}) {
    const token = localStorage.getItem('token');
    const headers = {
        ...(options.headers || {}),
        'Authorization': `Bearer ${token}`
    };

    const firstResponse = await fetch(url, {
        ...options,
        headers
    });

    if (firstResponse.status !== 401) {
        return firstResponse;
    }

    const refreshed = await refreshAccessToken();
    if (!refreshed) {
        return firstResponse;
    }

    const newToken = localStorage.getItem('token');
    const retryHeaders = {
        ...(options.headers || {}),
        'Authorization': `Bearer ${newToken}`
    };

    return fetch(url, {
        ...options,
        headers: retryHeaders
    });
}

async function verifySession() {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = 'login.html';
        return false;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/auth/verify`);

        if (!response.ok) {
            localStorage.removeItem('token');
            localStorage.removeItem('refreshToken');
            localStorage.removeItem('sessionId');
            localStorage.removeItem('user');
            window.location.href = 'login.html';
            return false;
        }

        return true;
    } catch (error) {
        showToast('Unable to verify session', 'error');
        return false;
    }
}

async function loadChatHistory(searchQuery = currentSearch) {
    try {
        currentSearch = searchQuery;
        const query = searchQuery ? `?q=${encodeURIComponent(searchQuery)}` : '';
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/history${query}`);

        const data = await response.json();
        if (data.success) {
            chatHistoryCache = data.history || [];
            displayChatHistory(chatHistoryCache);
        }
    } catch (error) {
        showToast('Failed to load chat history', 'error');
    }
}

function displayChatHistory(history) {
    const historyList = document.getElementById('chatHistoryList');
    historyList.innerHTML = '';

    if (!history.length) {
        const emptyState = document.createElement('div');
        emptyState.className = 'chat-history-empty';
        emptyState.innerHTML = currentSearch
            ? 'No chats match your search.'
            : 'No chats yet. Start with <b>New Chat</b> or ask your first question.';
        historyList.appendChild(emptyState);
        return;
    }

    history.forEach(chat => {
        const chatItem = document.createElement('div');
        chatItem.className = 'chat-history-item';
        if (currentChatId === chat.id) {
            chatItem.classList.add('active');
        }

        const titleRow = document.createElement('div');
        titleRow.className = 'chat-history-title-row';

        const title = document.createElement('div');
        title.className = 'chat-history-title';
        title.textContent = chat.title || 'Untitled Chat';

        const pinBtn = document.createElement('button');
        pinBtn.className = 'chat-icon-btn';
        pinBtn.title = chat.is_pinned ? 'Unpin chat' : 'Pin chat';
        pinBtn.innerHTML = chat.is_pinned
            ? '<i class="fas fa-star"></i>'
            : '<i class="far fa-star"></i>';
        pinBtn.onclick = (event) => {
            event.stopPropagation();
            togglePin(chat);
        };

        titleRow.appendChild(title);
        titleRow.appendChild(pinBtn);

        const footer = document.createElement('div');
        footer.className = 'chat-history-footer';

        const date = document.createElement('div');
        date.className = 'chat-history-date';
        const rawDate = chat.updated_at || chat.created_at;
        date.textContent = rawDate ? new Date(rawDate).toLocaleString() : 'Just now';

        const actions = document.createElement('div');
        actions.className = 'chat-history-actions';

        const renameBtn = document.createElement('button');
        renameBtn.className = 'chat-icon-btn';
        renameBtn.title = 'Rename chat';
        renameBtn.innerHTML = '<i class="fas fa-pen"></i>';
        renameBtn.onclick = (event) => {
            event.stopPropagation();
            renameChat(chat);
        };

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'chat-icon-btn delete';
        deleteBtn.title = 'Archive chat';
        deleteBtn.innerHTML = '<i class="fas fa-trash"></i>';
        deleteBtn.onclick = (event) => {
            event.stopPropagation();
            deleteChat(chat.id);
        };

        actions.appendChild(renameBtn);
        actions.appendChild(deleteBtn);
        footer.appendChild(date);
        footer.appendChild(actions);

        chatItem.appendChild(titleRow);
        chatItem.appendChild(footer);
        chatItem.onclick = () => {
            loadChat(chat);
            closeMobileSidebar();
        };
        historyList.appendChild(chatItem);
    });
}

function loadChat(chat) {
    if (socket && currentGroupId) {
        socket.emit('leave_group', { group_id: currentGroupId });
    }
    currentGroupId = null;
    currentGroupName = '';
    currentChatId = chat.id;
    currentChatTitle = chat.title || 'New Chat';
    currentMessages = chat.messages || [];
    displayMessages();
    displayChatHistory(chatHistoryCache);
    displayGroupList(groupsCache);
}

function displayGroupList(groups) {
    if (!groupList) {
        return;
    }

    groupList.innerHTML = '';
    if (!groups.length) {
        const empty = document.createElement('div');
        empty.className = 'chat-history-empty';
        empty.textContent = 'No groups yet';
        groupList.appendChild(empty);
        return;
    }

    groups.forEach((group) => {
        const groupItem = document.createElement('div');
        groupItem.className = 'chat-history-item';
        if (currentGroupId === group.id) {
            groupItem.classList.add('active');
        }

        const ownerBadge = group.owner_id === user.id ? '<span title="Owner"><i class="fas fa-crown"></i></span>' : '';

        groupItem.innerHTML = `
            <div class="chat-history-title-row">
                <div class="chat-history-title">${group.name} ${ownerBadge}</div>
                <button class="chat-icon-btn" title="Invite link">
                    <i class="fas fa-link"></i>
                </button>
            </div>
            <div class="chat-history-footer">
                <div class="chat-history-date">${group.member_count} members</div>
            </div>
        `;

        const inviteBtn = groupItem.querySelector('button');
        inviteBtn.onclick = async (event) => {
            event.stopPropagation();
            await createGroupInvite(group.id);
        };

        groupItem.onclick = async () => {
            await openGroup(group.id, group.name);
            closeMobileSidebar();
        };

        groupList.appendChild(groupItem);
    });

    refreshGroupActionButtons();
}

function getCurrentGroupMeta() {
    return groupsCache.find((group) => group.id === currentGroupId) || null;
}

function refreshGroupActionButtons() {
    if (!exitGroupBtn || !deleteGroupBtn) {
        return;
    }

    const currentGroup = getCurrentGroupMeta();
    const hasSelection = !!currentGroup;
    const isOwner = hasSelection && currentGroup.owner_id === user.id;

    exitGroupBtn.disabled = !hasSelection || isOwner;
    deleteGroupBtn.disabled = !hasSelection || !isOwner;
}

async function loadGroups() {
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups`);

        const data = await response.json();
        if (response.ok && data.success) {
            groupsCache = data.groups || [];
            displayGroupList(groupsCache);
        }
    } catch (error) {
        showToast('Failed to load groups', 'error');
    }
}

async function openGroup(groupId, groupName) {
    try {
        if (socket && currentGroupId && currentGroupId !== groupId) {
            socket.emit('leave_group', { group_id: currentGroupId });
        }

        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups/${groupId}/messages`);

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Unable to load group');
        }

        currentGroupId = groupId;
        currentGroupName = groupName;
        currentChatId = null;
        renderedGroupMessageIds.clear();
        currentMessages = (data.messages || []).map((msg) => {
            if (msg.id) {
                renderedGroupMessageIds.add(msg.id);
            }

            if (msg.message_type === 'image' && msg.image_url) {
                return {
                    role: 'assistant',
                    content: `### ${msg.sender_name} sent an image\n\n![Group image](${msg.image_url})`
                };
            }

            return {
                role: msg.sender_id === user.id ? 'user' : 'assistant',
                content: `${msg.sender_name}: ${msg.content}`
            };
        });

        displayMessages();
        displayChatHistory(chatHistoryCache);
        displayGroupList(groupsCache);
        refreshGroupActionButtons();

        if (socket) {
            socket.emit('join_group', { group_id: groupId });
        }
    } catch (error) {
        showToast(error.message || 'Unable to open group', 'error');
    }
}

function appendRealtimeGroupMessage(message) {
    if (!message || !message.id) {
        return;
    }

    if (renderedGroupMessageIds.has(message.id)) {
        return;
    }

    renderedGroupMessageIds.add(message.id);

    if (message.message_type === 'image' && message.image_url) {
        const imageContent = `### ${message.sender_name} sent an image\n\n![Group image](${message.image_url})`;
        addMessageToUI(imageContent, 'assistant');
        currentMessages.push({ role: 'assistant', content: imageContent });
        return;
    }

    const role = message.sender_id === user.id ? 'user' : 'assistant';
    const content = `${message.sender_name}: ${message.content}`;
    addMessageToUI(content, role);
    currentMessages.push({ role, content });
}

async function createGroup() {
    const name = prompt('Enter group name');
    if (!name || !name.trim()) {
        return;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups/create`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name: name.trim() })
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to create group');
        }

        await loadGroups();
        copyToClipboard(data.invite_url);
        showToast('Group created. Invite link copied.', 'success');
        await openGroup(data.group.id, data.group.name);
    } catch (error) {
        showToast(error.message || 'Failed to create group', 'error');
    }
}

async function createGroupInvite(groupId) {
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups/${groupId}/invite`, {
            method: 'POST'
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to create invite');
        }

        copyToClipboard(data.invite_url);
        showToast('Invite link copied', 'success');
    } catch (error) {
        showToast(error.message || 'Failed to create invite', 'error');
    }
}

async function joinGroup() {
    const inviteCode = prompt('Paste invite code or full invite link');
    if (!inviteCode || !inviteCode.trim()) {
        return;
    }

    const raw = inviteCode.trim();
    let code = raw;
    if (raw.includes('groupInvite=')) {
        try {
            const parsed = new URL(raw);
            code = parsed.searchParams.get('groupInvite') || '';
        } catch (error) {
            code = '';
        }
    }

    if (!code) {
        showToast('Invalid invite link', 'error');
        return;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups/join`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ invite_code: code })
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to join group');
        }

        await loadGroups();
        await openGroup(data.group.id, data.group.name);
        showToast(`Joined ${data.group.name}`, 'success');
    } catch (error) {
        showToast(error.message || 'Failed to join group', 'error');
    }
}

async function exitCurrentGroup() {
    if (!currentGroupId) {
        showToast('Select a group first', 'error');
        return;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups/${currentGroupId}/leave`, {
            method: 'POST'
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to leave group');
        }

        if (socket) {
            socket.emit('leave_group', { group_id: currentGroupId });
        }

        newChat();
        await loadGroups();
        showToast('You left the group', 'success');
    } catch (error) {
        showToast(error.message || 'Failed to leave group', 'error');
    }
}

async function deleteCurrentGroup() {
    if (!currentGroupId) {
        showToast('Select a group first', 'error');
        return;
    }

    const currentGroup = getCurrentGroupMeta();
    if (!currentGroup || currentGroup.owner_id !== user.id) {
        showToast('Only group owner can delete group', 'error');
        return;
    }

    const ok = window.confirm(`Delete group "${currentGroup.name}"? This removes it for everyone.`);
    if (!ok) {
        return;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups/${currentGroupId}`, {
            method: 'DELETE'
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to delete group');
        }

        if (socket) {
            socket.emit('leave_group', { group_id: currentGroupId });
        }

        newChat();
        await loadGroups();
        showToast('Group deleted for all members', 'success');
    } catch (error) {
        showToast(error.message || 'Failed to delete group', 'error');
    }
}

function displayMessages() {
    chatMessages.innerHTML = '';

    if (currentMessages.length === 0) {
        chatMessages.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <i class="fas fa-robot"></i>
                </div>
                <h3>Welcome to AI Smart Assistant</h3>
                <p>Try a suggested prompt or upload a document to ask questions about it.</p>
                <div class="quick-actions">
                    <button class="quick-prompt" data-prompt="Summarize my latest conversation in bullet points.">Summarize chat</button>
                    <button class="quick-prompt" data-prompt="Help me write a polished email response.">Draft an email</button>
                    <button class="quick-prompt" data-prompt="Give me a step-by-step plan to solve my current problem.">Create a plan</button>
                </div>
            </div>
        `;
        bindQuickPromptButtons();
        return;
    }

    currentMessages.forEach(message => {
        addMessageToUI(message.content, message.role);
    });

    scrollToBottom();
}

function renderMessageContent(contentDiv, content, role) {
    if (role !== 'assistant') {
        contentDiv.textContent = content;
        return;
    }

    function escapeHtml(raw) {
        return String(raw)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function inlineFormat(text) {
        return text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>');
    }

    function renderMarkdownLikeText(rawText) {
        const lines = String(rawText).split('\n');
        let html = '';
        let listOpen = false;

        const closeList = () => {
            if (listOpen) {
                html += '</ul>';
                listOpen = false;
            }
        };

        lines.forEach((line) => {
            const trimmed = line.trim();

            if (!trimmed) {
                closeList();
                return;
            }

            const imageMatch = trimmed.match(/^!\[(.*?)\]\((.+)\)$/);
            if (imageMatch) {
                closeList();
                const alt = inlineFormat(escapeHtml(imageMatch[1] || 'Generated image'));
                const src = escapeHtml((imageMatch[2] || '').trim());
                html += `<figure class="assistant-image-wrap"><img src="${src}" alt="${alt}" class="assistant-generated-image"></figure>`;
                return;
            }

            if (trimmed.startsWith('### ')) {
                closeList();
                html += `<h5>${inlineFormat(escapeHtml(trimmed.slice(4)))}</h5>`;
                return;
            }

            if (trimmed.startsWith('## ')) {
                closeList();
                html += `<h4>${inlineFormat(escapeHtml(trimmed.slice(3)))}</h4>`;
                return;
            }

            if (trimmed.startsWith('# ')) {
                closeList();
                html += `<h3>${inlineFormat(escapeHtml(trimmed.slice(2)))}</h3>`;
                return;
            }

            if (/^[-*]\s+/.test(trimmed)) {
                if (!listOpen) {
                    html += '<ul>';
                    listOpen = true;
                }
                html += `<li>${inlineFormat(escapeHtml(trimmed.replace(/^[-*]\s+/, '')))}</li>`;
                return;
            }

            closeList();
            html += `<p class="assistant-text">${inlineFormat(escapeHtml(trimmed))}</p>`;
        });

        closeList();
        return html;
    }

    const parts = String(content).split(/```/g);
    if (parts.length === 1) {
        contentDiv.classList.add('assistant-rich');
        contentDiv.innerHTML = renderMarkdownLikeText(content);
        return;
    }

    contentDiv.innerHTML = '';

    parts.forEach((part, index) => {
        if (index % 2 === 0) {
            if (part.trim()) {
                const textWrapper = document.createElement('div');
                textWrapper.className = 'assistant-rich';
                textWrapper.innerHTML = renderMarkdownLikeText(part.trim());
                contentDiv.appendChild(textWrapper);
            }
            return;
        }

        const firstBreak = part.indexOf('\n');
        const language = firstBreak > -1 ? part.slice(0, firstBreak).trim() : '';
        const code = firstBreak > -1 ? part.slice(firstBreak + 1) : part;

        const wrapper = document.createElement('div');
        wrapper.className = 'code-block-wrap';

        const meta = document.createElement('div');
        meta.className = 'code-block-meta';

        const langLabel = document.createElement('span');
        langLabel.textContent = language || 'code';

        const copyBtn = document.createElement('button');
        copyBtn.className = 'copy-code-btn';
        copyBtn.textContent = 'Copy';
        copyBtn.onclick = () => copyToClipboard(code);

        meta.appendChild(langLabel);
        meta.appendChild(copyBtn);

        const pre = document.createElement('pre');
        pre.className = 'assistant-code';
        const codeEl = document.createElement('code');
        codeEl.textContent = code.trimEnd();
        pre.appendChild(codeEl);

        wrapper.appendChild(meta);
        wrapper.appendChild(pre);
        contentDiv.appendChild(wrapper);
    });
}

function addMessageToUI(content, role) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    renderMessageContent(contentDiv, content, role);

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(contentDiv);

    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

function showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message assistant typing';
    typingDiv.id = 'typingIndicator';

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = '<i class="fas fa-robot"></i>';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = `
        <div class="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;

    typingDiv.appendChild(avatar);
    typingDiv.appendChild(contentDiv);
    chatMessages.appendChild(typingDiv);
    scrollToBottom();
}

function hideTypingIndicator() {
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

function startResponseTimer() {
    responseStartTime = performance.now();
    responseTimer.hidden = false;
    responseTimerValue.textContent = '0.0s';

    responseTimerInterval = setInterval(() => {
        const elapsed = (performance.now() - responseStartTime) / 1000;
        responseTimerValue.textContent = `${elapsed.toFixed(1)}s`;
    }, 100);
}

function stopResponseTimer() {
    if (responseTimerInterval) {
        clearInterval(responseTimerInterval);
        responseTimerInterval = null;
    }
    responseTimer.hidden = true;
}

function setGeneratingState(generating) {
    isTyping = generating;
    stopBtn.disabled = !generating;
    sendBtn.disabled = generating;
    regenerateBtn.disabled = generating;
}

async function persistCurrentChat() {
    if (!currentMessages.length) {
        return;
    }

    const firstUserMessage = currentMessages.find(message => message.role === 'user');
    if (!currentChatTitle || currentChatTitle === 'New Chat') {
        const fallbackTitle = firstUserMessage ? firstUserMessage.content : 'New Chat';
        currentChatTitle = fallbackTitle.substring(0, 30) + (fallbackTitle.length > 30 ? '...' : '');
    }

    const response = await authenticatedFetch(`${API_BASE_URL}/chat/save`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            chat_data: {
                id: currentChatId,
                title: currentChatTitle,
                messages: currentMessages
            }
        })
    });

    const data = await response.json();
    if (data.success) {
        currentChatId = String(data.chat_id);
        await loadChatHistory(currentSearch);
    }
}

async function sendMessage() {
    const message = userInput.value.trim();
    if (!message || isTyping) return;
    userInput.value = '';

    if (currentGroupId) {
        await sendGroupMessage(message);
        return;
    }

    await requestAssistantResponse(message, { addUserMessage: true });
}

async function sendGroupMessage(message) {
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups/${currentGroupId}/message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message })
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to send group message');
        }

        appendRealtimeGroupMessage(data.message);
        if (data.assistant_message) {
            appendRealtimeGroupMessage(data.assistant_message);
        }

        await loadGroups();
    } catch (error) {
        showToast(error.message || 'Failed to send group message', 'error');
    }
}

async function requestAssistantResponse(prompt, options = {}) {
    const { addUserMessage = true, contextOverride = null } = options;

    if (addUserMessage) {
        addMessageToUI(prompt, 'user');
        currentMessages.push({ role: 'user', content: prompt });
    }

    userInput.value = '';
    showTypingIndicator();
    startResponseTimer();
    setGeneratingState(true);
    activeAbortController = new AbortController();

    const context = contextOverride || currentMessages;
    const preparedPrompt = uploadedDocument
        ? `Use the document context if relevant.\n\n[DOCUMENT: ${uploadedDocument.filename}]\n${uploadedDocument.content}\n\n[QUESTION]\n${prompt}`
        : prompt;

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            signal: activeAbortController.signal,
            body: JSON.stringify({
                prompt: preparedPrompt,
                chat_id: currentChatId,
                context
            })
        });

        const data = await response.json();

        hideTypingIndicator();
        stopResponseTimer();
        setGeneratingState(false);
        activeAbortController = null;

        if (data.success) {
            addMessageToUI(data.response, 'assistant');
            currentMessages.push({ role: 'assistant', content: data.response });
            lastAssistantReply = data.response;
            await persistCurrentChat();
        } else {
            showToast(data.error || 'Failed to generate response', 'error');
        }
    } catch (error) {
        hideTypingIndicator();
        stopResponseTimer();
        setGeneratingState(false);
        activeAbortController = null;

        if (error.name === 'AbortError') {
            showToast('Generation stopped', 'success');
            return;
        }

        showToast('Network error. Please try again.', 'error');
    }
}

async function uploadDocument(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/upload`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            showToast(data.error || 'Failed to upload document', 'error');
            return;
        }

        uploadedDocument = {
            filename: data.filename,
            content: data.content
        };

        showToast(
            data.truncated
                ? `${data.filename} uploaded (trimmed for size).`
                : `${data.filename} uploaded. Ask a question about it.`,
            'success'
        );
    } catch (error) {
        showToast('Failed to upload document', 'error');
    }
}

async function uploadGroupImage(file) {
    if (!currentGroupId) {
        showToast('Open a group chat first', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups/${currentGroupId}/upload-image`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to upload image');
        }

        appendRealtimeGroupMessage(data.message);
        await loadGroups();
    } catch (error) {
        showToast(error.message || 'Failed to upload image', 'error');
    }
}

async function renameChat(chat) {
    const updatedTitle = prompt('Rename chat', chat.title || 'Untitled Chat');
    if (!updatedTitle || !updatedTitle.trim()) {
        return;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/rename/${chat.id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                title: updatedTitle.trim()
            })
        });

        const data = await response.json();
        if (data.success) {
            if (currentChatId === chat.id) {
                currentChatTitle = updatedTitle.trim();
            }
            await loadChatHistory(currentSearch);
            showToast('Chat renamed', 'success');
        } else {
            showToast(data.error || 'Failed to rename chat', 'error');
        }
    } catch (error) {
        showToast('Failed to rename chat', 'error');
    }
}

async function togglePin(chat) {
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/pin/${chat.id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                is_pinned: !chat.is_pinned
            })
        });

        const data = await response.json();
        if (data.success) {
            await loadChatHistory(currentSearch);
        } else {
            showToast(data.error || 'Failed to update favorite', 'error');
        }
    } catch (error) {
        showToast('Failed to update favorite', 'error');
    }
}

async function deleteChat(chatId) {
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/delete/${chatId}`, {
            method: 'DELETE'
        });

        const data = await response.json();
        if (data.success) {
            if (currentChatId === chatId) {
                newChat();
            }
            await loadChatHistory(currentSearch);
            showToast('Chat archived', 'success');
        } else {
            showToast(data.error || 'Failed to delete chat', 'error');
        }
    } catch (error) {
        showToast('Failed to delete chat', 'error');
    }
}

function stopGenerating() {
    if (activeAbortController) {
        activeAbortController.abort();
    }
}

async function regenerateLastResponse() {
    if (isTyping || currentMessages.length === 0) {
        return;
    }

    const lastAssistantIndex = [...currentMessages]
        .reverse()
        .findIndex(message => message.role === 'assistant');

    if (lastAssistantIndex === -1) {
        showToast('No assistant response to regenerate', 'error');
        return;
    }

    const actualAssistantIndex = currentMessages.length - 1 - lastAssistantIndex;
    const previousMessage = currentMessages[actualAssistantIndex - 1];

    if (!previousMessage || previousMessage.role !== 'user') {
        showToast('Could not find the original prompt', 'error');
        return;
    }

    currentMessages.splice(actualAssistantIndex, 1);
    displayMessages();
    await requestAssistantResponse(previousMessage.content, {
        addUserMessage: false,
        contextOverride: currentMessages
    });
}

function newChat() {
    if (socket && currentGroupId) {
        socket.emit('leave_group', { group_id: currentGroupId });
    }
    currentGroupId = null;
    currentGroupName = '';
    currentChatId = null;
    currentChatTitle = 'New Chat';
    currentMessages = [];
    uploadedDocument = null;
    displayMessages();
    displayChatHistory(chatHistoryCache);
    displayGroupList(groupsCache);
    userInput.focus();
}

async function createImageFromPrompt() {
    const promptText = userInput.value.trim() || prompt('Describe the image you want to create');
    if (!promptText) {
        return;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/generate-image`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ prompt: promptText })
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Image generation failed');
        }

        const primaryUrl = data.image_url;
        const finalUrl = resolveImageUrl(primaryUrl);
        if (!finalUrl) {
            throw new Error('Image provider did not return a renderable image');
        }

        const imageMarkdown = `Generated image for: ${promptText}\n\n![AI generated image](${finalUrl})`;
        addMessageToUI(imageMarkdown, 'assistant');
        currentMessages.push({ role: 'assistant', content: imageMarkdown });
        lastAssistantReply = `Generated image for: ${promptText}`;

        if (!currentGroupId) {
            await persistCurrentChat();
        }
    } catch (error) {
        showToast(error.message || 'Image generation failed', 'error');
    }
}

function resolveImageUrl(primaryUrl) {
    if (!primaryUrl) {
        return null;
    }

    // Avoid false negatives from cross-origin probe failures.
    return primaryUrl;
}

function initVoiceRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        return;
    }

    speechRecognition = new SpeechRecognition();
    speechRecognition.lang = 'en-US';
    speechRecognition.interimResults = false;
    speechRecognition.maxAlternatives = 1;

    speechRecognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript || '';
        if (transcript) {
            userInput.value = transcript;
            userInput.focus();
        }
    };

    speechRecognition.onstart = () => {
        isVoiceListening = true;
        voiceInputBtn.classList.add('stop');
        showToast('Listening...', 'success');
    };

    speechRecognition.onend = () => {
        isVoiceListening = false;
        voiceInputBtn.classList.remove('stop');
    };
}

function toggleVoiceInput() {
    if (!speechRecognition) {
        showToast('Voice input is not supported in this browser', 'error');
        return;
    }

    if (isVoiceListening) {
        speechRecognition.stop();
    } else {
        speechRecognition.start();
    }
}

function speakLastReply() {
    if (!lastAssistantReply) {
        showToast('No assistant reply to read', 'error');
        return;
    }

    if (!window.speechSynthesis) {
        showToast('Speech synthesis is not supported in this browser', 'error');
        return;
    }

    const utterance = new SpeechSynthesisUtterance(lastAssistantReply.replace(/[#*`]/g, ''));
    utterance.lang = 'en-US';
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
}

async function joinGroupFromInviteParam() {
    const params = new URLSearchParams(window.location.search);
    const inviteCode = params.get('groupInvite');
    if (!inviteCode) {
        return;
    }

    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/chat/groups/join`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ invite_code: inviteCode })
        });

        const data = await response.json();
        if (response.ok && data.success) {
            await loadGroups();
            await openGroup(data.group.id, data.group.name);
            showToast(`Joined ${data.group.name}`, 'success');
        }
    } catch (error) {
        showToast('Unable to join group from invite link', 'error');
    } finally {
        window.history.replaceState({}, document.title, window.location.pathname);
    }
}

function connectSocket() {
    if (typeof io === 'undefined') {
        return;
    }

    const token = localStorage.getItem('token');
    if (!token) {
        return;
    }

    if (socket && socket.connected) {
        return;
    }

    socket = io('http://localhost:5000', {
        auth: {
            token
        },
        transports: ['polling']
    });

    socket.on('connect_error', () => {
        showToast('Realtime channel unavailable', 'error');
    });

    socket.on('group_message', (payload) => {
        if (!payload || payload.group_id !== currentGroupId) {
            return;
        }

        appendRealtimeGroupMessage(payload.message);
    });
}

async function logout() {
    try {
        const refreshToken = localStorage.getItem('refreshToken');
        if (refreshToken) {
            await fetch(`${API_BASE_URL}/auth/logout`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
        }
    } catch (error) {
        // ignore logout API failures and clear local session anyway
    }

    if (socket) {
        socket.disconnect();
    }

    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('sessionId');
    localStorage.removeItem('user');
    window.location.href = 'index.html';
}

function toggleTheme() {
    document.body.classList.toggle('light-theme');
    const isLight = document.body.classList.contains('light-theme');
    localStorage.setItem('themeMode', isLight ? 'light' : 'dark');

    const icon = themeToggle.querySelector('i');
    if (isLight) {
        icon.className = 'fas fa-moon';
        themeToggle.querySelector('span').textContent = 'Dark Mode';
    } else {
        icon.className = 'fas fa-sun';
        themeToggle.querySelector('span').textContent = 'Light Mode';
    }
}

function applyChatTheme(themeName) {
    const themes = ['indigo', 'ocean', 'forest', 'sunset', 'mono'];
    document.body.classList.remove(...themes.map((theme) => `theme-${theme}`));

    const selected = themes.includes(themeName) ? themeName : 'indigo';
    document.body.classList.add(`theme-${selected}`);
    localStorage.setItem('chatColorTheme', selected);

    if (chatThemeSelect) {
        chatThemeSelect.value = selected;
    }
}

function openMobileSidebar() {
    sidebar.classList.add('active');
    sidebarOverlay.classList.add('active');
}

function closeMobileSidebar() {
    sidebar.classList.remove('active');
    sidebarOverlay.classList.remove('active');
}

function bindQuickPromptButtons() {
    document.querySelectorAll('.quick-prompt').forEach((button) => {
        button.addEventListener('click', () => {
            userInput.value = button.dataset.prompt || '';
            userInput.focus();
        });
    });
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

userInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

let searchDebounceTimer = null;
chatSearchInput.addEventListener('input', (event) => {
    clearTimeout(searchDebounceTimer);
    const query = event.target.value.trim();
    searchDebounceTimer = setTimeout(() => {
        loadChatHistory(query);
    }, 250);
});

attachDocBtn.addEventListener('click', () => {
    docInput.click();
});

uploadGroupImageBtn.addEventListener('click', () => {
    if (!currentGroupId) {
        showToast('Open a group chat to upload image', 'error');
        return;
    }
    groupImageInput.click();
});

docInput.addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) {
        return;
    }
    await uploadDocument(file);
    docInput.value = '';
});

groupImageInput.addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) {
        return;
    }

    await uploadGroupImage(file);
    groupImageInput.value = '';
});

mobileMenuBtn.addEventListener('click', openMobileSidebar);
sidebarOverlay.addEventListener('click', closeMobileSidebar);

sendBtn.addEventListener('click', sendMessage);
newChatBtn.addEventListener('click', newChat);
logoutBtn.addEventListener('click', logout);
themeToggle.addEventListener('click', toggleTheme);
stopBtn.addEventListener('click', stopGenerating);
regenerateBtn.addEventListener('click', regenerateLastResponse);
createGroupBtn.addEventListener('click', createGroup);
joinGroupBtn.addEventListener('click', joinGroup);
exitGroupBtn.addEventListener('click', exitCurrentGroup);
deleteGroupBtn.addEventListener('click', deleteCurrentGroup);
createImageBtn.addEventListener('click', createImageFromPrompt);
voiceInputBtn.addEventListener('click', toggleVoiceInput);
voiceReadBtn.addEventListener('click', speakLastReply);

if (chatThemeSelect) {
    chatThemeSelect.addEventListener('change', (event) => {
        applyChatTheme(event.target.value);
    });
}

setGeneratingState(false);
initVoiceRecognition();
verifySession().then((valid) => {
    if (!valid) {
        return;
    }
    connectSocket();
    loadChatHistory();
    loadGroups();
    joinGroupFromInviteParam();
    bindQuickPromptButtons();
});

const savedTheme = localStorage.getItem('themeMode');
if (savedTheme === 'light') {
    toggleTheme();
} else {
    themeToggle.querySelector('i').className = 'fas fa-sun';
    themeToggle.querySelector('span').textContent = 'Light Mode';
}

applyChatTheme(localStorage.getItem('chatColorTheme') || 'indigo');
refreshGroupActionButtons();
