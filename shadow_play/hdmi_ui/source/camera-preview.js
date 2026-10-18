/* A real local camera preview. Pose landmarks only come from updatePose(). */
(function () {
  'use strict';
  function create(options) {
    options = options || {};
    const video = options.video, canvas = options.canvas, empty = options.empty;
    if (!video || !canvas || typeof canvas.getContext !== 'function') throw new TypeError('ShadowCameraPreview.create needs video and canvas elements.');
    const doc = video.ownerDocument || document, win = doc.defaultView || window;
    const view = video.closest('.shadow-camera-view') || video.parentElement;
    const screen = video.closest('[data-screen="body"]');
    const ctx = canvas.getContext('2d', { alpha: true });
    const board = options.board || null;
    const boardImage = board ? doc.createElement('img') : null;
    if (boardImage) { boardImage.className = 'shadow-board-frame'; boardImage.alt = '板端相机实时画面'; boardImage.hidden = true; video.after(boardImage); }
    let boardActive = false, frameTimer = 0, frameExpiry = 0, frameKey = '', lastFrameAt = 0;
    let state = 'off', stream = null, pendingStart = null, serial = 0, destroyed = false;
    let pose = null, poseTimer = 0, sourceWidth = 640, sourceHeight = 480;
    let logicalWidth = 0, logicalHeight = 0, pixelRatio = 1;
    let trackListeners = [];
    video.muted = true; video.autoplay = true; video.playsInline = true;
    canvas.style.pointerEvents = 'none'; canvas.setAttribute('aria-hidden', 'true');

    function stopTracks(mediaStream) {
      if (!mediaStream || typeof mediaStream.getTracks !== 'function') return;
      for (const track of mediaStream.getTracks()) { try { track.stop(); } catch (_) {} }
    }
    function removeTrackListeners() {
      for (const [track, listener] of trackListeners) track.removeEventListener('ended', listener);
      trackListeners = [];
    }
    function clearOverlay() {
      if (!ctx) return;
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.restore();
    }
    function clearPose() {
      const hadPose = !!pose;
      pose = null;
      if (poseTimer) win.clearTimeout(poseTimer);
      poseTimer = 0; clearOverlay();
      if (hadPose && typeof options.onPose === 'function') options.onPose(null);
    }
    function updateUI(next, message) {
      if (view) view.dataset.cameraState = next;
      video.hidden = !!board || next !== 'live';
      if (boardImage) boardImage.hidden = next !== 'live';
      if (empty) {
        empty.hidden = next === 'live';
        const label = empty.querySelector('[data-camera-message]');
        if (label) label.textContent = message;
      }
    }
    function emit(next, message) {
      state = next; updateUI(next, message);
      if (!destroyed && typeof options.onState === 'function') options.onState(next, message);
    }
    function release() {
      win.clearTimeout(frameTimer); win.clearTimeout(frameExpiry); frameTimer = 0; frameExpiry = 0;
      if (boardImage) { boardImage.hidden = true; boardImage.removeAttribute('src'); }
      removeTrackListeners();
      const previous = stream; stream = null;
      try { video.pause(); } catch (_) {}
      try { video.srcObject = null; } catch (_) {}
      stopTracks(previous); clearPose();
    }
    function permittedScreen() { return !doc.hidden && (!screen || (!screen.hidden && !screen.closest('[hidden]'))); }
    function failureMessage(error) {
      const name = error && error.name;
      if (name === 'NotFoundError' || name === 'DevicesNotFoundError') return '未找到可用摄像头';
      if (name === 'NotReadableError' || name === 'TrackStartError') return '摄像头被占用或无法读取';
      if (name === 'OverconstrainedError') return '摄像头不支持当前采集设置';
      if (name === 'AbortError') return '摄像头开启中断，请重试';
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
        let blocked = false;
        try {
          const policy = doc.permissionsPolicy || doc.featurePolicy;
          blocked = win.location.origin === 'null' || win.isSecureContext === false || Boolean(policy && typeof policy.allowsFeature === 'function' && !policy.allowsFeature('camera'));
        } catch (_) { blocked = true; }
        return blocked ? '当前预览无法访问摄像头' : '摄像头访问被拒绝';
      }
      return '当前预览无法访问摄像头';
    }
    function draw() {
      if (destroyed || !ctx) return;
      const box = canvas.getBoundingClientRect();
      const width = Math.max(0, box.width), height = Math.max(0, box.height);
      const ratio = Math.min(2, Math.max(1, win.devicePixelRatio || 1));
      if (width >= 1 && height >= 1 && (width !== logicalWidth || height !== logicalHeight || ratio !== pixelRatio)) {
        logicalWidth = width; logicalHeight = height; pixelRatio = ratio;
        canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      }
      clearOverlay();
      if (state !== 'live' || !pose || width < 1 || height < 1) return;
      ctx.save(); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const frameWidth = board ? sourceWidth : video.videoWidth || sourceWidth, frameHeight = board ? sourceHeight : video.videoHeight || sourceHeight;
      const contain = board || win.getComputedStyle(video).objectFit === 'contain';
      const cover = (contain ? Math.min : Math.max)(width / frameWidth, height / frameHeight);
      const offsetX = (width - frameWidth * cover) / 2, offsetY = (height - frameHeight * cover) / 2;
      const projected = {};
      for (const [key, point] of Object.entries(pose)) projected[key] = [point[0] * frameWidth * cover + offsetX, point[1] * frameHeight * cover + offsetY];
      // No fabricated shoulders or preset skeleton: draw only supplied pairs.
      const connections = [['leftShoulder','rightShoulder'],['leftShoulder','leftElbow'],['leftElbow','leftWrist'],['rightShoulder','rightElbow'],['rightElbow','rightWrist'],['neck','head'],['neck','leftShoulder'],['neck','rightShoulder'],['leftShoulder','leftHip'],['rightShoulder','rightHip'],['leftHip','rightHip']];
      ctx.strokeStyle = '#596f54'; ctx.lineWidth = 2; ctx.lineCap = 'round';
      for (const [a, b] of connections) if (projected[a] && projected[b]) { ctx.beginPath(); ctx.moveTo(...projected[a]); ctx.lineTo(...projected[b]); ctx.stroke(); }
      for (const point of Object.values(projected)) {
        ctx.beginPath(); ctx.arc(point[0], point[1], 3.5, 0, Math.PI * 2); ctx.fillStyle = '#f0ead4'; ctx.fill();
        ctx.beginPath(); ctx.arc(point[0], point[1], 2.2, 0, Math.PI * 2); ctx.fillStyle = '#3d5941'; ctx.fill();
      }
      ctx.restore();
    }
    function updatePose(value) {
      if (destroyed || state !== 'live' || !value || typeof value !== 'object') { clearPose(); return false; }
      const next = {};
      for (const [key, point] of Object.entries(value)) {
        const x = Array.isArray(point) ? point[0] : point && point.x, y = Array.isArray(point) ? point[1] : point && point.y;
        if (Number.isFinite(x) && Number.isFinite(y) && x >= 0 && x <= 1 && y >= 0 && y <= 1) next[key] = [x, y];
      }
      if (!Object.keys(next).length) { clearPose(); return false; }
      clearPose(); pose = next; draw();
      // A stopped device feed must not leave stale landmarks over live video.
      poseTimer = win.setTimeout(clearPose, 1200);
      if (typeof options.onPose === 'function') options.onPose(Object.fromEntries(Object.entries(next).map(([key, point]) => [key, point.slice()])));
      return true;
    }
    function updateFrame(frame) {
      if (destroyed || !frame || typeof frame !== 'object') return false;
      if (Number.isFinite(frame.width) && frame.width > 0 && Number.isFinite(frame.height) && frame.height > 0) { sourceWidth = frame.width; sourceHeight = frame.height; }
      if (frame.pose) return updatePose(frame.pose);
      clearPose();
      draw(); return state === 'live';
    }
    function invalidateFrame(message) {
      clearPose();
      if (boardImage) { boardImage.hidden = true; boardImage.removeAttribute('src'); }
      emit('waiting', message);
    }
    async function pollBoard(run) {
      if (run !== serial || destroyed || !boardActive || !permittedScreen()) return;
      const requestedAt = performance.now();
      try {
        const frame = await board.frame();
        if (run !== serial || destroyed || !boardActive) return;
        if (!Number.isFinite(frame.captured_age_ms) || frame.captured_age_ms < 0 || frame.captured_age_ms > 1200 || !Number.isInteger(frame.sequence) || typeof frame.session_id !== 'string' || !frame.session_id || !Number.isFinite(frame.width) || frame.width <= 0 || !Number.isFinite(frame.height) || frame.height <= 0 || typeof frame.jpeg_base64 !== 'string' || !frame.jpeg_base64) throw new Error('相机画面过期或无效');
        const key = frame.session_id + ':' + frame.sequence;
        if (key === frameKey) {
          if (performance.now() - lastFrameAt > 1200) invalidateFrame('等待新的实拍画面…');
        } else {
          const image = new win.Image();
          image.src = 'data:image/jpeg;base64,' + frame.jpeg_base64;
          await image.decode();
          if (run !== serial || destroyed || !boardActive || !permittedScreen()) return;
          const remaining = 1200 - frame.captured_age_ms - (performance.now() - requestedAt);
          if (remaining <= 0) throw new Error('相机帧在传输中已过期');
          if (!image.naturalWidth || image.naturalWidth !== frame.width || image.naturalHeight !== frame.height) throw new Error('相机帧尺寸不匹配');
          boardImage.src = image.src;
          frameKey = key; lastFrameAt = performance.now();
          sourceWidth = frame.width; sourceHeight = frame.height;
          emit('live', frame.pose && Object.keys(frame.pose).length ? '板端实拍 · 实际姿态关键点' : '板端实拍 · 暂未检测到人体');
          updateFrame(frame);
          win.clearTimeout(frameExpiry);
          frameExpiry = win.setTimeout(() => { if (run === serial && boardActive) invalidateFrame('实拍画面已过期，请检查相机'); }, remaining);
        }
      } catch (error) {
        if (run !== serial || destroyed || !boardActive) return;
        invalidateFrame(error.name === 'AbortError' ? '相机连接超时，等待恢复…' : '等待板端画面：' + error.message);
      }
      // Include request/decode time in the interval; never stack another full
      // delay on top of a slow board response, and never overlap requests.
      if (run === serial && !destroyed && boardActive) frameTimer = win.setTimeout(() => pollBoard(run), Math.max(0, 1000/15 - (performance.now()-requestedAt)));
    }
    async function startBoard() {
      if (destroyed || !permittedScreen()) return false;
      if (boardActive) return true;
      const run = ++serial; boardActive = true; frameKey = ''; lastFrameAt = 0;
      release(); emit('starting', '正在启动板端姿态识别…');
      try {
        await board.startCamera();
        if (run !== serial || destroyed || !boardActive || !permittedScreen()) return false;
        emit('waiting', '姿态识别启动中，等待首帧…');
        pollBoard(run); return true;
      } catch (error) {
        if (run !== serial || destroyed) return false;
        boardActive = false; release();
        // A lost start response does not prove the board failed to start.
        board.stopCamera().catch(() => {});
        emit('error', error.name === 'AbortError' ? '板端启动超时，已请求停止' : error.message); return false;
      }
    }
    function stop() {
      if (destroyed) return;
      const alreadyOff = state === 'off' && !stream && !pendingStart;
      serial++; pendingStart = null; release();
      if (boardActive) { boardActive = false; board.stopCamera().catch(error => board.message('相机停止请求未确认：' + error.message, true)); }
      if (!alreadyOff) emit('off', '摄像头未开启');
      else updateUI('off', '摄像头未开启');
    }
    function start() {
      if (board) return startBoard();
      if (destroyed) return Promise.resolve(false);
      if (state === 'live' && stream) return Promise.resolve(true);
      if (pendingStart) return pendingStart;
      if (!permittedScreen()) { emit('off', '摄像头未开启'); return Promise.resolve(false); }
      const run = ++serial; clearPose(); emit('starting', '正在开启摄像头…');
      const task = (async function () {
        // Defer one microtask so synchronous browser rejection is also tracked.
        await Promise.resolve();
        let acquired = null;
        try {
          const media = win.navigator.mediaDevices;
          if (!media || typeof media.getUserMedia !== 'function') {
            if (run === serial && !destroyed) emit('error', '当前预览无法访问摄像头');
            return false;
          }
          acquired = await media.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
          if (destroyed || run !== serial || !permittedScreen()) { stopTracks(acquired); return false; }
          const tracks = typeof acquired.getVideoTracks === 'function' ? acquired.getVideoTracks() : acquired.getTracks().filter(track => track.kind === 'video');
          if (!tracks.length) { stopTracks(acquired); const error = new Error('No camera video track'); error.name = 'NotReadableError'; throw error; }
          stream = acquired; video.srcObject = acquired;
          const settings = typeof tracks[0].getSettings === 'function' ? tracks[0].getSettings() : {};
          sourceWidth = settings.width || 640; sourceHeight = settings.height || 480;
          for (const track of tracks) {
            const ended = function () {
              if (destroyed || run !== serial || !stream) return;
              if (tracks.every(item => item.readyState === 'ended')) { serial++; pendingStart = null; release(); emit('error', '摄像头已断开，请重新开启'); }
            };
            track.addEventListener('ended', ended); trackListeners.push([track, ended]);
          }
          emit('live', '摄像头已开启'); draw();
          const playback = video.play(); if (playback && typeof playback.then === 'function') await playback;
          if (destroyed || run !== serial || !permittedScreen()) { stopTracks(acquired); return false; }
          return true;
        } catch (error) {
          if (destroyed || run !== serial) { stopTracks(acquired); return false; }
          release(); stopTracks(acquired); emit('error', failureMessage(error)); return false;
        }
      })();
      pendingStart = task;
      task.then(function () { if (pendingStart === task) pendingStart = null; }, function () { if (pendingStart === task) pendingStart = null; });
      return task;
    }
    function onVisibility() { if (doc.hidden) stop(); }
    function onMetadata() { draw(); }
    function onScreenChange() { if (!permittedScreen() && (state !== 'off' || stream || pendingStart)) stop(); }
    const resizeObserver = typeof win.ResizeObserver === 'function' ? new win.ResizeObserver(draw) : null;
    if (resizeObserver && view) resizeObserver.observe(view);
    const screenObserver = screen && typeof win.MutationObserver === 'function' ? new win.MutationObserver(onScreenChange) : null;
    if (screenObserver) screenObserver.observe(screen, { attributes: true, attributeFilter: ['hidden', 'style', 'class', 'aria-hidden'] });
    doc.addEventListener('visibilitychange', onVisibility);
    win.addEventListener('pagehide', stop);
    video.addEventListener('loadedmetadata', onMetadata); video.addEventListener('resize', onMetadata);
    updateUI('off', '摄像头未开启'); clearOverlay();
    return {
      start, stop, draw, updatePose, updateFrame,
      get state() { return state; },
      destroy: function () {
        if (destroyed) return;
        stop();
        destroyed = true; serial++; pendingStart = null; release(); state = 'off'; updateUI('off', '摄像头未开启');
        if (boardImage) boardImage.remove();
        if (resizeObserver) resizeObserver.disconnect(); if (screenObserver) screenObserver.disconnect();
        doc.removeEventListener('visibilitychange', onVisibility); win.removeEventListener('pagehide', stop);
        video.removeEventListener('loadedmetadata', onMetadata); video.removeEventListener('resize', onMetadata);
      },
    };
  }
  window.ShadowCameraPreview = { create };
})();
