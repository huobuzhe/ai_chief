// frontend/js/app.js - 应用主逻辑（阶段 5）
// 负责：启动初始化、登录/登出、发送消息、上传图片、会话管理

let currentThreadId = '';                                       // 当前会话 ID
let currentThread = null;                                       // 当前会话对象

// ---------- 初始化 ----------
window.addEventListener('DOMContentLoaded', () => {
    initTopbar();
    initAuthModal();
    initChat();
    initSidebar();
});

// ---------- 顶部用户条 ----------
function initTopbar() {
    document.getElementById('btn-show-login').addEventListener('click', () => showAuthModal('login'));
    document.getElementById('btn-logout').addEventListener('click', handleLogout);
    refreshTopbar();
}

function refreshTopbar() {
    const user = Api.getUser();
    if (user) {
        document.getElementById('user-info').classList.remove('hidden');
        document.getElementById('btn-show-login').classList.add('hidden');
        document.getElementById('username').textContent = user.username;
    } else {
        document.getElementById('user-info').classList.add('hidden');
        document.getElementById('btn-show-login').classList.remove('hidden');
    }
}

// ---------- 登录弹窗 ----------
let authMode = 'login';                                          // 'login' 或 'register'

function initAuthModal() {
    document.getElementById('close-modal').addEventListener('click', hideAuthModal);
    document.getElementById('btn-submit-auth').addEventListener('click', handleAuthSubmit);
    document.getElementById('link-to-register').addEventListener('click', () => showAuthModal('register'));

    // 用户名/密码框按回车直接提交
    ['auth-username', 'auth-password'].forEach(id => {
        document.getElementById(id).addEventListener('keydown', e => {
            if (e.key === 'Enter') handleAuthSubmit();
        });
    });
}

function showAuthModal(mode) {
    authMode = mode;
    document.getElementById('modal-title').textContent = mode === 'login' ? '登录' : '注册';
    document.getElementById('btn-submit-auth').textContent = mode === 'login' ? '登录' : '注册';
    document.getElementById('link-to-register').textContent = mode === 'login' ? '立即注册' : '去登录';
    document.getElementById('auth-error').textContent = '';
    document.getElementById('auth-modal').classList.remove('hidden');
    document.getElementById('auth-username').focus();
}

function hideAuthModal() {
    document.getElementById('auth-modal').classList.add('hidden');
    document.getElementById('auth-password').value = '';
}

async function handleAuthSubmit() {
    const username = document.getElementById('auth-username').value.trim();
    const password = document.getElementById('auth-password').value;
    const errorEl = document.getElementById('auth-error');
    if (!username || !password) { errorEl.textContent = '请填写用户名和密码'; return; }
    if (password.length < 8) { errorEl.textContent = '密码至少 8 位'; return; }

    errorEl.textContent = '';
    const btn = document.getElementById('btn-submit-auth');
    btn.disabled = true;
    try {
        let data;
        if (authMode === 'login') {
            data = await Api.login(username, password);
        } else {
            await Api.register(username, password);
            data = await Api.login(username, password);
        }
        // 后端 /auth/login 只返回 token，没有完整用户信息，需要再调 /users/me
        Api.setAuth(data.access_token, data.refresh_token, { username });
        const me = await Api.fetchMe();
        Api.setAuth(data.access_token, data.refresh_token, {
            id: me.id, username: me.username, email: me.email,
        });
        hideAuthModal();
        refreshTopbar();
        History.render(currentThreadId, switchThread, deleteThread);
    } catch (e) {
        errorEl.textContent = e.detail || e.message;
    } finally {
        btn.disabled = false;
    }
}

async function handleLogout() {
    try { await Api.logout(); } catch (e) { /* 即便失败也清本地状态 */ }
    Api.clearAuth();
    refreshTopbar();
    currentThreadId = '';
    currentThread = null;
    ChatUI.clearMessages();
    History.render(currentThreadId, switchThread, deleteThread);
}

// ---------- 对话区 ----------
function initChat() {
    const btnSend = document.getElementById('btn-send');
    const textarea = document.getElementById('input-text');
    btnSend.addEventListener('click', handleSend);
    textarea.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
    });
    document.getElementById('btn-upload').addEventListener('click', () => {
        if (!Api.getAccessToken()) { showAuthModal('login'); return; }
        document.getElementById('image-input').click();
    });
    document.getElementById('image-input').addEventListener('change', handleImageUpload);
}

async function handleSend() {
    if (!Api.getAccessToken()) { showAuthModal('login'); return; }
    const textarea = document.getElementById('input-text');
    const text = textarea.value.trim();
    if (!text) return;
    textarea.value = '';

    if (!currentThreadId) startNewThread();
    ChatUI.showMessages();
    ChatUI.addUserMessage(text);
    currentThread.messages.push({ role: 'user', content: text });
    saveCurrentThread();

    await generateResponse(text);
}

async function handleImageUpload(e) {
    if (!Api.getAccessToken()) { showAuthModal('login'); return; }
    const file = e.target.files[0];
    if (!file) return;
    if (!currentThreadId) startNewThread();
    ChatUI.showMessages();

    const btnSend = document.getElementById('btn-send');
    btnSend.disabled = true;
    let imageUrl;
    try {
        imageUrl = await Api.uploadImage(file);
    } catch (err) {
        alert('图片上传失败：' + (err.detail || err.message));
        btnSend.disabled = false;
        return;
    }
    btnSend.disabled = false;

    ChatUI.addUserMessage('（上传了一张图片）', imageUrl);
    currentThread.messages.push({ role: 'user', content: '（上传了一张图片）', imageUrl });
    saveCurrentThread();

    await generateResponse('识别图片里的食材，推荐对应的菜谱', imageUrl);
}

async function generateResponse(message, imageUrl = null) {
    const bubble = ChatUI.createAssistantBubble();
    ChatUI.showTyping();

    let fullText = '';
    try {
        const user = Api.getUser();
        // /users/me 返回的 id 是 int，后端 ChatRequest.user_id 是 str，必须 String() 转换
        for await (const chunk of Api.streamChat({
            message,
            imageUrl,
            threadId: currentThreadId,
            userId: user ? String(user.id) : null,
        })) {
            fullText = chunk;                                    // chunk 是累积的全部内容
            ChatUI.updateAssistantBubble(bubble, fullText);
        }
    } catch (e) {
        fullText += `\n\n**错误**：${e.detail || e.message}`;
        ChatUI.updateAssistantBubble(bubble, fullText);
    } finally {
        ChatUI.hideTyping();
        currentThread.messages.push({ role: 'assistant', content: fullText });
        saveCurrentThread();
        refreshThreadTitle();
    }
}

// ---------- 侧栏 ----------
function initSidebar() {
    document.getElementById('btn-new-chat').addEventListener('click', startNewThread);
    History.render(currentThreadId, switchThread, deleteThread);
}

function startNewThread() {
    currentThreadId = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    currentThread = {
        id: currentThreadId,
        title: '新会话',
        messages: [],
        userId: Api.getUser()?.id,
    };
    ChatUI.clearMessages();
    History.render(currentThreadId, switchThread, deleteThread);
}

function deleteThread(threadId) {
    if (!confirm('确认删除这个会话？')) return;
    History.remove(threadId);
    if (currentThreadId === threadId) {
        currentThreadId = '';
        currentThread = null;
        ChatUI.clearMessages();
    }
    History.render(currentThreadId, switchThread, deleteThread);
}

function switchThread(threadId) {
    const thread = History.load().find(t => t.id === threadId);
    if (!thread) return;
    currentThreadId = threadId;
    currentThread = thread;
    ChatUI.clearMessages();
    ChatUI.showMessages();
    thread.messages.forEach(m => {
        if (m.role === 'user') ChatUI.addUserMessage(m.content, m.imageUrl);
        else ChatUI.addAssistantMessage(m.content);
    });
    History.render(currentThreadId, switchThread, deleteThread);
}

function saveCurrentThread() {
    if (!currentThread) return;
    History.upsert(currentThread);
}

function refreshThreadTitle() {
    if (currentThread && currentThread.messages.length >= 1) {
        const firstUser = currentThread.messages.find(m => m.role === 'user');
        if (firstUser) {
            currentThread.title = firstUser.content.slice(0, 20);
            History.upsert(currentThread);
            History.render(currentThreadId, switchThread, deleteThread);
        }
    }
}
