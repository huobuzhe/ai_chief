// 在 Node 里加载 frontend/js/ws.js，验证：URL 拼接、真实连接、事件回调、状态回调
'use strict';
const path = require('path');

const API = 'http://127.0.0.1:9002';
const USER = 'stage8_wsjs_' + Date.now();

global.window = global;
global.location = { href: API + '/x.html', origin: API };
global.document = {
  createElement: () => ({ style: {}, textContent: '', parentNode: null }),
  body: { appendChild() {}, removeChild() {} },
};
global.WS_BASE = API;   // 让 ws.js 用这个地址（而不是默认推导）

(async () => {
  await fetch(API + '/auth/register', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: 'wsjs-pass-123', email: USER + '@t.local' }),
  });
  const lr = await fetch(API + '/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: 'wsjs-pass-123' }),
  });
  global.WS_TOKEN = (await lr.json()).access_token;
  console.log('[0] 登录成功');

  require(path.join(__dirname, 'frontend', 'js', 'ws.js'));
  console.log('[1] ws.js 已加载，方法：', Object.keys(window.Notify).join(', '));

  const events = [];
  let opened = null;
  const openedPromise = new Promise((res) => { opened = res; });
  const donePromise = new Promise((res) => { global.__done = res; });

  window.Notify.on((ev) => {
    if (ev.type === 'status') {
      console.log('[2] 状态:', ev.state, ev.message || '');
      if (ev.state === 'open') opened();
      if (ev.state === 'error') global.__done && global.__done();
      return;
    }
    if (ev.type === 'task') {
      events.push(ev.status);
      console.log('[4] 收到任务推送:', ev.status, '|', ev.name);
      if (ev.status === 'SUCCESS' || ev.status === 'FAILURE') global.__done && global.__done();
    }
  });

  window.Notify.connect();
  await Promise.race([openedPromise, new Promise((r) => setTimeout(r, 8000))]);
  console.log('[3] isOpen() =', window.Notify.isOpen());

  const sub = await fetch(API + '/tasks/nutrition-report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + global.WS_TOKEN },
    body: JSON.stringify({ ingredients: ['鸡蛋 100克', '西兰花 200克'] }),
  });
  console.log('[3.5] 提交任务 HTTP', sub.status, JSON.stringify(await sub.json()));

  await Promise.race([donePromise, new Promise((r) => setTimeout(r, 60000))]);
  window.Notify.close();

  console.log('[5] 事件序列:', JSON.stringify(events));
  const ok = events[0] === 'STARTED' && events[events.length - 1] === 'SUCCESS';
  console.log(ok ? '[OK] ws.js 行为正确' : '[FAIL] 未收到预期事件');
  process.exit(ok ? 0 : 1);
})().catch((e) => { console.error('异常:', e); process.exit(1); });