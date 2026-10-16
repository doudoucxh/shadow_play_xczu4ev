/* Same-origin board API. No reconnect ever replays a movement request. */
(() => {
  'use strict';
  function create({root, onStatus} = {}) {
    let status = null, token = '', cameraQueue = Promise.resolve();
    const bar = document.createElement('div');
    bar.className = 'shadow-board-bar';
    const label = document.createElement('span'); label.setAttribute('role', 'status');
    const button = document.createElement('button'); button.type = 'button'; button.textContent = '检查连接';
    bar.append(label, button); root.querySelector('.shadow-app').append(bar);
    function message(text, error = false) { label.textContent = text; label.title = text; bar.dataset.error = String(error); }
    async function request(path, payload, timeout = 4000) {
      const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeout);
      try {
        const response = await fetch(path, {method: payload === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', signal: controller.signal, keepalive: path === '/api/camera/stop',
          ...(payload === undefined ? {} : {headers: {'Content-Type': 'application/json', 'X-Shadow-Token': token}, body: JSON.stringify(payload)})});
        const data = await response.json();
        if (!response.ok || data.ok === false) throw new Error(data.error || '板端请求失败（' + response.status + '）');
        return data;
      } finally { clearTimeout(timer); }
    }
    async function check() {
      button.disabled = true;
      try {
        const next = await request('/api/status');
        if (next.app !== 'shadow-theatre-board' || typeof next.token !== 'string' || !next.token) throw new Error('未找到皮影板端服务');
        status = next; token = next.token;
        message('界面服务已连接 · ' + (next.camera?.configured ? '姿态相机可开启' : '姿态相机未配置') + ' · ' + (next.motion?.ready ? '实控已就绪' : '实控未就绪'));
      } catch (error) { status = null; token = ''; message('板端服务未连接 · 仅屏幕预览', true); }
      finally { button.disabled = false; onStatus?.(status); }
      return status;
    }
    async function control(payload) {
      if (!status) { message('板端服务未连接；仅更新屏幕预览，未发送动作', true); return false; }
      const capability = {rail:'rails',pose:'puppet',classic:'classic'}[payload.kind];
      if (!status.motion?.ready || !status.motion?.[capability]) {
        message('实控未就绪：' + (status.motion?.reason || '硬件路线尚未核验') + '；仅屏幕预览', true); return false;
      }
      try {
        const result = await request('/api/control', payload);
        if (result.ok !== true) throw new Error('板端未确认接收');
        message('板端已接收请求 · 以现场结果为准'); return true;
      } catch (error) { message(error.name === 'AbortError' ? '控制请求超时，执行状态未知；不会自动重发' : error.message, true); return false; }
    }
    function cameraCommand(action) {
      // Preserve start/stop order even when a start request has not returned yet.
      cameraQueue = cameraQueue.catch(() => {}).then(async () => {
        if (action === 'start' && !await check()) throw new Error('板端服务未连接');
        if (action === 'start' && !status.camera?.configured) throw new Error(status.camera?.error || '板端姿态相机未配置');
        if (!token) return;
        return request('/api/camera/' + action, {}, action === 'start' ? 15000 : 4000);
      });
      return cameraQueue;
    }
    button.addEventListener('click', check);
    message('正在检查板端连接…');
    return {check, control, message, startCamera: () => cameraCommand('start'), stopCamera: () => cameraCommand('stop'),
      frame: () => request('/api/camera/frame'), get status() { return status; }};
  }
  window.ShadowBoardClient = {create};
})();
