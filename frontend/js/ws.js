// frontend/js/ws.js —— v3 阶段 8：WebSocket 实时通知客户端
// 职责：连上 /ws/notifications，收到任务事件就回调；断线自动重连；定时心跳保活；右下角 toast。
// 依赖：可选 api.js（提供 Api.getAccessToken()）。没加载就用 window.WS_TOKEN。
(function (global) {
    'use strict';

    var MAX_DELAY = 15000;    // 重连退避上限（15 秒）
    var BASE_DELAY = 1000;    // 首次重连等待 1 秒
    var HEARTBEAT_MS = 25000; // 心跳间隔：比常见 30/60 秒的空闲超时短一点，防止被中间设备掐断

    var socket = null;        // 当前 WebSocket 实例
    var retryCount = 0;       // 已连续重连次数（用来算退避时长）
    var heartbeatTimer = null;// 心跳定时器
    var reconnectTimer = null;// 重连定时器
    var manualClosed = false; // 主动 close() 时置真，避免把"用户主动断开"也当成掉线去重连
    var listeners = [];       // 事件回调列表

    // 计算后端地址：优先 window.WS_BASE，其次 api.js 的 API_BASE，最后同源
    function backendBase() {
        if (global.WS_BASE) return global.WS_BASE;
        if (typeof API_BASE !== 'undefined' && API_BASE) return API_BASE;
        return global.location.origin;
    }

    // 取 token：优先 api.js，其次 window.WS_TOKEN
    function currentToken() {
        if (typeof Api !== 'undefined' && Api.getAccessToken) {
            var t = Api.getAccessToken();
            if (t) return t;
        }
        return global.WS_TOKEN || '';
    }

    // 拼出 ws(s)://host/ws/notifications?token=xxxx
    // 🔴 token 只能走查询参数：浏览器原生 WebSocket 不支持自定义请求头
    function buildUrl() {
        var base = backendBase().replace(/\/+$/, '');
        var url = new URL(base + '/ws/notifications', global.location.href);
        url.protocol = (url.protocol === 'https:') ? 'wss:' : 'ws:';
        url.search = '?token=' + encodeURIComponent(currentToken());
        return url.toString();
    }

    function emit(event) {
        for (var i = 0; i < listeners.length; i++) {
            try { listeners[i](event); } catch (e) { console.error('[ws] 回调异常', e); }
        }
    }

    function startHeartbeat() {
        stopHeartbeat();
        heartbeatTimer = global.setInterval(function () {
            if (socket && socket.readyState === 1) {
                try { socket.send('ping'); } catch (e) { /* 发失败就让 onclose 走重连 */ }
            }
        }, HEARTBEAT_MS);
    }

    function stopHeartbeat() {
        if (heartbeatTimer) { global.clearInterval(heartbeatTimer); heartbeatTimer = null; }
    }

    function scheduleReconnect() {
        if (manualClosed) return;
        if (reconnectTimer) return;                     // 已经在等重连了，别叠加
        var delay = Math.min(BASE_DELAY * Math.pow(2, retryCount), MAX_DELAY); // 1s,2s,4s...最多 15s
        retryCount++;
        emit({ type: 'status', state: 'reconnecting', delay: delay, attempt: retryCount });
        reconnectTimer = global.setTimeout(function () {
            reconnectTimer = null;
            connect();
        }, delay);
    }

    function connect() {
        if (socket && (socket.readyState === 0 || socket.readyState === 1)) return; // 连着呢
        manualClosed = false;
        var url = buildUrl();
        if (!currentToken()) {
            emit({ type: 'status', state: 'error', message: '没有 token，无法连接（请先登录）' });
            return;
        }

        try {
            socket = new WebSocket(url);
        } catch (e) {
            emit({ type: 'status', state: 'error', message: '创建 WebSocket 失败：' + e.message });
            scheduleReconnect();
            return;
        }

        socket.onopen = function () {
            retryCount = 0;                              // 连上了就重置退避
            startHeartbeat();
            emit({ type: 'status', state: 'open' });
        };

        socket.onmessage = function (evt) {
            var data;
            try { data = JSON.parse(evt.data); } catch (e) { return; } // 非 JSON（如 pong）忽略
            if (data && data.type === 'pong') return;                  // 心跳应答不用上抛
            emit(data);
        };

        socket.onclose = function (evt) {
            stopHeartbeat();
            socket = null;
            if (manualClosed) { emit({ type: 'status', state: 'closed' }); return; }
            // 1008 = 服务端因鉴权失败主动关闭：重连也没用，直接报错让人去重新登录
            if (evt && evt.code === 1008) {
                emit({ type: 'status', state: 'error', message: '鉴权失败（token 无效或已过期），请重新登录' });
                return;
            }
            emit({ type: 'status', state: 'closed', code: evt && evt.code });
            scheduleReconnect();
        };

        socket.onerror = function () {
            // onerror 之后浏览器一定会调 onclose，重连逻辑交给 onclose，这里只报状态
            emit({ type: 'status', state: 'error', message: '连接出错' });
        };
    }

    function close() {
        manualClosed = true;
        stopHeartbeat();
        if (reconnectTimer) { global.clearTimeout(reconnectTimer); reconnectTimer = null; }
        if (socket) { try { socket.close(1000, 'client close'); } catch (e) {} }
    }

    // 右下角 toast：不依赖任何 CSS 文件，直接内联样式，放哪都能用
    function toast(text, kind) {
        var color = kind === 'error' ? '#d93025' : (kind === 'success' ? '#1a7f37' : '#1f6feb');
        var box = global.document.createElement('div');
        box.style.cssText = [
            'position:fixed', 'right:16px', 'bottom:16px', 'z-index:99999',
            'max-width:340px', 'padding:12px 14px', 'border-radius:10px',
            'background:#fff', 'color:#111', 'font:13px/1.5 sans-serif',
            'box-shadow:0 6px 24px rgba(0,0,0,.18)', 'border-left:4px solid ' + color,
            'white-space:pre-wrap', 'word-break:break-all'
        ].join(';');
        box.textContent = text;
        global.document.body.appendChild(box);
        global.setTimeout(function () { if (box.parentNode) box.parentNode.removeChild(box); }, 6000);
    }

    global.Notify = {
        connect: connect,
        close: close,
        toast: toast,
        on: function (fn) { listeners.push(fn); return fn; },
        off: function (fn) { listeners = listeners.filter(function (f) { return f !== fn; }); },
        isOpen: function () { return !!socket && socket.readyState === 1; }
    };
})(window);