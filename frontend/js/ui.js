// frontend/js/ui.js - UI 工具层（阶段 5）
// DOM 创建、Markdown 渲染、历史侧栏、消息气泡等纯 UI 逻辑

// 把 Markdown 文本转成 HTML 字符串
function renderMarkdown(text) {
    if (typeof marked === 'undefined') {                         // CDN 加载失败时降级
        const div = document.createElement('div');
        div.textContent = text;
        div.style.whiteSpace = 'pre-wrap';                       // 保留换行
        return div.innerHTML;
    }
    marked.setOptions({ breaks: true, gfm: true, headerIds: false, mangle: false });
    return marked.parse(text);                                   // 生成 HTML
}

// 创建 DOM 元素的辅助函数
// 示例：el('div', {class:'message user'}, ['你好'])
// children 可以是数组，也可以是单个字符串/元素，统一包成数组处理
function el(tag, props = {}, children = []) {
    const e = document.createElement(tag);
    if (!Array.isArray(children)) children = [children];           // 单个元素也包成数组
    Object.entries(props).forEach(([k, v]) => {
        if (k === 'class') e.className = v;                       // class 是 JS 保留字，单独处理
        else if (k === 'dataset') Object.entries(v).forEach(([dk, dv]) => e.dataset[dk] = dv);
        else if (k.startsWith('on')) e.addEventListener(k.slice(2).toLowerCase(), v);
        else e.setAttribute(k, v);
    });
    children.forEach(c => e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c));
    return e;
}

function scrollToBottom(container) {
    container.scrollTop = container.scrollHeight;
}

// ---------- 历史侧栏 ----------
const History = {
    KEY: 'ai_sichu.history',                                     // localStorage 键名

    load() {
        const s = localStorage.getItem(History.KEY);
        return s ? JSON.parse(s) : [];                            // 首次访问返回空数组
    },

    save(list) {
        localStorage.setItem(History.KEY, JSON.stringify(list));
    },

    upsert(thread) {
        const list = History.load();
        const idx = list.findIndex(t => t.id === thread.id);
        if (idx >= 0) list[idx] = thread;                          // 已有就更新
        else list.unshift(thread);                                 // 新会话放最上面
        History.save(list);
    },

    remove(threadId) {
        const list = History.load().filter(t => t.id !== threadId);
        History.save(list);
    },

    render(activeId, onSwitch, onDelete) {
        const ul = document.getElementById('history-list');
        ul.innerHTML = '';                                         // 先清空旧列表
        History.load().forEach(thread => {
            const li = el('li', {
                class: thread.id === activeId ? 'active' : '',
                dataset: { id: thread.id },
            }, [
                el('span', { class: 'title', title: thread.title }, thread.title),
                el('span', { class: 'del', onclick: (e) => { e.stopPropagation(); onDelete(thread.id); } }, '×'),
            ]);
            li.addEventListener('click', () => onSwitch(thread.id));
            ul.appendChild(li);
        });
    },
};

// ---------- 对话区渲染 ----------
const ChatUI = {
    addUserMessage(text, imageUrl = null) {
        const div = el('div', { class: 'message user' });
        if (text) div.appendChild(document.createTextNode(text));
        if (imageUrl) {                                            // 有图片就追加 img
            const img = el('img', { src: imageUrl, alt: '用户上传' });
            div.appendChild(img);
        }
        document.getElementById('messages').appendChild(div);
        scrollToBottom(document.getElementById('messages'));
    },

    addAssistantMessage(markdown) {
        const div = el('div', { class: 'message assistant' });
        div.innerHTML = renderMarkdown(markdown);
        const container = document.getElementById('messages');
        container.appendChild(div);
        scrollToBottom(container);
    },

    // 流式场景：先创建占位元素，之后每收到一段就更新它
    createAssistantBubble() {
        const div = el('div', { class: 'message assistant' });
        div.innerHTML = renderMarkdown('');
        document.getElementById('messages').appendChild(div);
        return div;
    },

    updateAssistantBubble(div, markdown) {
        div.innerHTML = renderMarkdown(markdown);
        scrollToBottom(document.getElementById('messages'));
    },

    showTyping() { document.getElementById('typing').classList.remove('hidden'); },
    hideTyping() { document.getElementById('typing').classList.add('hidden'); },

    clearMessages() {
        document.getElementById('messages').innerHTML = '';
        document.getElementById('messages').classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
    },

    showMessages() {
        document.getElementById('empty-state').classList.add('hidden');
        document.getElementById('messages').classList.remove('hidden');
    },
};
