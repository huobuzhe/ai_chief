// frontend/js/api.js - API 封装层（阶段 5）
// 把所有后端调用、token 管理、流式接收都收拢到 Api 对象里

// 开发期后端地址，必须写 8002；生产期若走 Nginx 反代可改为 '' 或 '/' 
//const API_BASE = 'http://127.0.0.1:8002';
const API_BASE = location.port === '9000' ? 'http://127.0.0.1:9002' : '';   // 开发模式直连后端，部署模式同源
// 统一错误对象：带 HTTP 状态码和后端返回的 detail
class ApiError extends Error {
    constructor(status, detail) {
        super(detail || `HTTP ${status}`);
        this.status = status;
        this.detail = detail;
    }
}

// localStorage 键名，避免和其他项目冲突
const TOKEN_KEY = 'ai_sichu.access_token';
const REFRESH_KEY = 'ai_sichu.refresh_token';
const USER_KEY = 'ai_sichu.user';

const Api = {
    // ---------- token 管理 ----------
    getAccessToken: () => localStorage.getItem(TOKEN_KEY) || '',
    getRefreshToken: () => localStorage.getItem(REFRESH_KEY) || '',
    getUser: () => {
        const s = localStorage.getItem(USER_KEY);
        return s ? JSON.parse(s) : null;
    },
    setAuth(access, refresh, user) {
        localStorage.setItem(TOKEN_KEY, access);
        localStorage.setItem(REFRESH_KEY, refresh);
        localStorage.setItem(USER_KEY, JSON.stringify(user));
    },
    clearAuth() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
        localStorage.removeItem(USER_KEY);
    },

    // ---------- 通用 fetch 封装 ----------
    // 自动加 Authorization 头、自动把普通对象 body 序列化为 JSON
    async request(path, options = {}) {
        const headers = { ...options.headers };                 // 复制一份，避免污染调用方传的对象
        const token = Api.getAccessToken();                      // 读本地 token
        if (token) headers['Authorization'] = `Bearer ${token}`; // 有 token 就带上

        // 仅当 body 是普通对象时才加 Content-Type 并 JSON 序列化
        // FormData / Blob 不能 JSON.stringify，它们的 Content-Type 由浏览器或 OSS 决定
        if (options.body && typeof options.body === 'object'
            && !(options.body instanceof FormData)
            && !(options.body instanceof Blob)) {
            headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(options.body);
        }

        const res = await fetch(API_BASE + path, { ...options, headers }); // 真正发请求

        if (!res.ok) {                                           // 状态码不在 200-299 之间
            let detail;
            try {
                const data = await res.json();
                detail = data.detail;                            // FastAPI 错误一般在 detail 字段
            } catch {
                detail = res.statusText;                         // 解析失败就用状态码文本兜底
            }
            if (res.status === 401) Api.clearAuth();             // token 失效时清本地登录态
            throw new ApiError(res.status, detail);
        }
        return res;                                              // 返回原始 Response，让调用方决定要不要 json()
    },

    // ---------- 认证接口 ----------
    async login(username, password) {
        const res = await Api.request('/auth/login', {
            method: 'POST',
            body: { username, password },
        });
        return res.json();
    },

    async register(username, password, email) {
        const res = await Api.request('/auth/register', {
            method: 'POST',
            body: { username, password, email },
        });
        return res.json();
    },

    async logout() {
        // /auth/logout 不在白名单，必须带 token 才能撤销服务端黑名单
        await Api.request('/auth/logout', { method: 'POST' });
    },

    async fetchMe() {
        const res = await Api.request('/users/me');
        return res.json();
    },

    // ---------- 流式对话 ----------
    // 后端 /chat/stream 直接 yield 字符串，不是 SSE data: 协议
    // 所以前端用 fetch + reader.read() 累积拼接，每收到一段就 yield
    async *streamChat({ message, imageUrl = null, threadId = '', userId = null }) {
        const body = {
            message,
            image_url: imageUrl ? [imageUrl] : [],                // 后端要求数组
            thread_id: threadId,
            user_id: userId,
        };

        const res = await fetch(API_BASE + '/chat/stream', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${Api.getAccessToken()}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        if (!res.ok) {                                           // 流式接口的错误在 headers 阶段返回
            let detail;
            try { detail = (await res.json()).detail; } catch { detail = res.statusText; }
            if (res.status === 401) Api.clearAuth();
            throw new ApiError(res.status, detail);
        }

        const reader = res.body.getReader();                     // 拿到响应体的字节流读取器
        const decoder = new TextDecoder('utf-8');                // 把 Uint8Array 解码成字符串
        let buffer = '';                                         // 累积已解码的字符串

        while (true) {
            const { done, value } = await reader.read();          // value 是 Uint8Array
            if (done) break;                                     // 后端关闭连接

            // stream: true 让 decoder 内部缓存跨 chunk 的多字节字符，中文不会乱码
            buffer += decoder.decode(value, { stream: true });
            yield buffer;                                        // 把累积内容交出去给 UI
            buffer = '';                                         // 清空，下一次从头累积
        }

        // 流结束，再 flush 一次 decoder 残留
        const tail = decoder.decode();
        if (tail) yield buffer + tail;
    },

    // ---------- OSS 预签名 + 直传 ----------
    async presign(filename) {
        const res = await Api.request(`/oss/presign?filename=${encodeURIComponent(filename)}`);
        return res.json();
    },

    async uploadImage(file) {
        const { uploadUrl, accessUrl, contentType } = await Api.presign(file.name);
        const putRes = await fetch(uploadUrl, {
            method: 'PUT',
            body: file,
            headers: { 'Content-Type': contentType },             // OSS 需要这个头
        });
        if (!putRes.ok) throw new ApiError(putRes.status, '图片上传 OSS 失败');
        return accessUrl;
    },
};
