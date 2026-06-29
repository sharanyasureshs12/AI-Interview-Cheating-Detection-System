// ═══════════════════════════════════════════════════════════
//  ProctorAI v3 — Frontend Controller
//  Features: Face · Phone · Tab Switch · Copy-Paste · Audio
// ═══════════════════════════════════════════════════════════

const STATE = {
  monitoring:     false,
  stream:         null,
  frameInterval:  null,
  statsInterval:  null,
  clockInterval:  null,
  sessionStart:   null,
  fpsFrames:      0,
  fpsTimer:       null,
  timelineData:   [],
  sessionId:      null,
  violationCount: 0,

  // Copy-paste counters
  copyCount:      0,
  pasteCount:     0,
  cutCount:       0,

  // Audio
  audioCtx:       null,
  audioAnalyser:  null,
  audioSource:    null,
  audioInterval:  null,
  audioSamples:   0,
  audioPeakDb:    -100,
  waveBuffer:     new Float32Array(256),
  waveAnimId:     null,
};

// ─────────────────────────────────────────────────────────────
//  INIT
// ─────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  updateClock();
  STATE.clockInterval = setInterval(updateClock, 1000);
  STATE.sessionId = 'S-' + Math.random().toString(36).substr(2,6).toUpperCase();
  document.getElementById('sessionId').textContent = STATE.sessionId;

  setupTabDetection();
  setupCopyPasteDetection();
  drawTimeline();
  setInterval(drawTimeline, 1000);
});

// ─────────────────────────────────────────────────────────────
//  CLOCK
// ─────────────────────────────────────────────────────────────
function updateClock() {
  const n = new Date();
  document.getElementById('clock').textContent =
    pad(n.getHours()) + ':' + pad(n.getMinutes()) + ':' + pad(n.getSeconds());
  if (STATE.sessionStart) {
    const e = Math.floor((Date.now() - STATE.sessionStart) / 1000);
    document.getElementById('footerDuration').textContent =
      pad(Math.floor(e/60)) + ':' + pad(e%60);
  }
}
const pad = n => String(n).padStart(2,'0');

// ─────────────────────────────────────────────────────────────
//  TAB SWITCH DETECTION
// ─────────────────────────────────────────────────────────────
function setupTabDetection() {
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && STATE.monitoring) logTabSwitch();
  });
  window.addEventListener('blur', () => {
    if (STATE.monitoring) logTabSwitch();
  });
}

let lastTabSwitch = 0;
function logTabSwitch() {
  const now = Date.now();
  if (now - lastTabSwitch < 3000) return;
  lastTabSwitch = now;
  fetch('/api/tab_switch', { method:'POST', headers:{'Content-Type':'application/json'} })
    .then(r => r.json())
    .then(() => {
      showAlert('🔀 Tab/Window switch detected!', 'warning');
      STATE.timelineData.push({ t: Date.now(), type: 'tab' });
    });
}

// ─────────────────────────────────────────────────────────────
//  COPY-PASTE DETECTION
// ─────────────────────────────────────────────────────────────
function setupCopyPasteDetection() {
  // Listen globally on document
  document.addEventListener('copy',  e => handleClipboard('copy',  e));
  document.addEventListener('paste', e => handleClipboard('paste', e));
  document.addEventListener('cut',   e => handleClipboard('cut',   e));

  // Also intercept keyboard shortcuts
  document.addEventListener('keydown', e => {
    if (e.ctrlKey || e.metaKey) {
      const k = e.key.toLowerCase();
      if (k === 'c') handleClipboard('copy', e);
      if (k === 'v') handleClipboard('paste', e);
      if (k === 'x') handleClipboard('cut', e);
    }
  });
}

let lastCPEvent = {};   // debounce per type
function handleClipboard(evType, e) {
  if (!STATE.monitoring) return;

  const now = Date.now();
  if (lastCPEvent[evType] && now - lastCPEvent[evType] < 800) return; // debounce 800ms
  lastCPEvent[evType] = now;

  // Try to get text length
  let textLen = 0;
  if (evType === 'paste' && e.clipboardData) {
    const txt = e.clipboardData.getData('text') || '';
    textLen = txt.length;
  } else if ((evType === 'copy' || evType === 'cut') && window.getSelection) {
    const sel = window.getSelection();
    textLen = sel ? sel.toString().length : 0;
  }

  // Update local counters
  if (evType === 'copy')  STATE.copyCount++;
  if (evType === 'paste') STATE.pasteCount++;
  if (evType === 'cut')   STATE.cutCount++;

  updateCPUI(evType);

  // Fire row animation
  const rowMap = { copy:'cpCopyRow', paste:'cpPasteRow', cut:'cpCutRow' };
  const row = document.getElementById(rowMap[evType]);
  if (row) {
    row.classList.add('fired');
    setTimeout(() => row.classList.remove('fired'), 600);
  }

  // Push to timeline
  STATE.timelineData.push({ t: now, type: 'cp' });

  // Show alert for paste (most suspicious)
  if (evType === 'paste') {
    showAlert(`📋 PASTE detected! ${textLen > 0 ? textLen + ' chars' : ''} — Possible external content!`, 'critical');
    animateStatCard('scCP', 'scCPVal');
  } else {
    showAlert(`📄 ${evType.toUpperCase()} detected in interview window`, 'warning');
  }

  // Log to backend
  fetch('/api/copy_paste', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event: evType, text_length: textLen })
  }).catch(() => {});
}

function updateCPUI(lastEvent) {
  document.getElementById('cpCopyCount').textContent  = STATE.copyCount;
  document.getElementById('cpPasteCount').textContent = STATE.pasteCount;
  document.getElementById('cpCutCount').textContent   = STATE.cutCount;
}

// ─────────────────────────────────────────────────────────────
//  AUDIO MONITORING
// ─────────────────────────────────────────────────────────────
async function startAudioMonitoring(stream) {
  try {
    STATE.audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    STATE.audioAnalyser = STATE.audioCtx.createAnalyser();
    STATE.audioAnalyser.fftSize = 2048;
    STATE.audioAnalyser.smoothingTimeConstant = 0.5;

    STATE.audioSource = STATE.audioCtx.createMediaStreamSource(stream);
    STATE.audioSource.connect(STATE.audioAnalyser);

    document.getElementById('waveformOverlay').classList.add('hidden');
    document.getElementById('audioStatusPill').textContent = 'ACTIVE';
    document.getElementById('audioStatusPill').classList.add('active');
    document.getElementById('footerAudio').textContent = '🎙 ACTIVE';
    document.getElementById('footerAudio').style.color = 'var(--teal)';
    document.getElementById('audioOverlay').style.display = 'flex';

    // Waveform animation
    drawWaveform();

    // Send audio chunks to backend every 2 seconds
    STATE.audioInterval = setInterval(sendAudioChunk, 2000);

  } catch (err) {
    console.warn('Audio monitoring failed:', err.message);
  }
}

function stopAudioMonitoring() {
  if (STATE.audioCtx) {
    clearInterval(STATE.audioInterval);
    cancelAnimationFrame(STATE.waveAnimId);
    STATE.audioCtx.close().catch(() => {});
    STATE.audioCtx = null;
    STATE.audioAnalyser = null;
    STATE.audioSource = null;
  }
  document.getElementById('audioStatusPill').textContent = 'OFF';
  document.getElementById('audioStatusPill').classList.remove('active','alert');
  document.getElementById('footerAudio').textContent = '● STANDBY';
  document.getElementById('footerAudio').style.color = 'var(--text2)';
  document.getElementById('audioOverlay').style.display = 'none';
  document.getElementById('waveformOverlay').classList.remove('hidden');
}

function drawWaveform() {
  if (!STATE.audioAnalyser) return;
  const canvas = document.getElementById('waveformCanvas');
  const W = canvas.offsetWidth || 260;
  const H = canvas.height || 60;
  canvas.width = W;
  const ctx = canvas.getContext('2d');
  const buf = new Float32Array(STATE.audioAnalyser.frequencyBinCount);

  function frame() {
    STATE.waveAnimId = requestAnimationFrame(frame);
    STATE.audioAnalyser.getFloatTimeDomainData(buf);

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'var(--bg3, #141820)';
    ctx.fillRect(0, 0, W, H);

    // RMS for colour
    const rms = Math.sqrt(buf.reduce((s,v) => s + v*v, 0) / buf.length);
    const dbVal = 20 * Math.log10(rms + 1e-9);
    const color = dbVal < -45 ? '#3d4a5c'
                : dbVal < -25 ? '#00d4d4'
                : dbVal < -10 ? '#ffd447'
                : '#ff3b5c';

    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    const sliceW = W / buf.length;
    for (let i = 0; i < buf.length; i++) {
      const x = i * sliceW;
      const y = (buf[i] * 0.9 + 1) / 2 * H;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Volume bar overlay update
    updateVolumeMeter(dbVal);
  }
  frame();
}

function updateVolumeMeter(dbVal) {
  // Map -60 dB..0 dB → 0%..100%
  const pct = Math.max(0, Math.min(100, ((dbVal + 60) / 60) * 100));
  document.getElementById('volFill').style.width = pct + '%';
  document.getElementById('volDb').textContent = dbVal.toFixed(1) + ' dB';
  document.getElementById('aoDb').textContent  = dbVal.toFixed(0) + ' dB';
  document.getElementById('aoBarFill').style.width = pct + '%';

  if (STATE.audioPeakDb < dbVal) {
    STATE.audioPeakDb = dbVal;
    document.getElementById('astPeak').textContent = dbVal.toFixed(1);
  }
}

async function sendAudioChunk() {
  if (!STATE.audioAnalyser) return;
  const buf = new Float32Array(STATE.audioAnalyser.fftSize);
  STATE.audioAnalyser.getFloatTimeDomainData(buf);
  STATE.audioSamples++;
  document.getElementById('astSamples').textContent = STATE.audioSamples;

  const samples = Array.from(buf);

  try {
    const res = await fetch('/api/audio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ samples, sample_rate: 16000 })
    });
    const data = await res.json();
    if (data.error) return;

    // Update voice dots
    const voices = data.suspected_voices || 0;
    document.getElementById('vfVoices').textContent = voices;
    document.getElementById('voiceCount').textContent = voices || '--';
    updateVoiceDots(voices);

    if (data.suspicious) {
      document.getElementById('audioStatusPill').classList.add('alert');
      document.getElementById('footerAudio').textContent = '⚠ ALERT';
      document.getElementById('footerAudio').style.color = 'var(--red)';
      document.getElementById('aoIcon').textContent = '🔴';
      showAlert(
        voices >= 2
          ? `🎙️ Multiple voices detected (${voices} voices) — Possible assistance!`
          : `🔊 Loud audio detected (${data.volume_db?.toFixed(0)} dB)`,
        'critical'
      );
      animateStatCard('scAudio', 'scAudioVal');
      STATE.timelineData.push({ t: Date.now(), type: 'audio' });
    } else {
      document.getElementById('audioStatusPill').classList.remove('alert');
      document.getElementById('aoIcon').textContent = '🎙️';
      if (STATE.monitoring) {
        document.getElementById('footerAudio').textContent = '🎙 ACTIVE';
        document.getElementById('footerAudio').style.color = 'var(--teal)';
      }
    }

    if (data.stats) {
      document.getElementById('astAlerts').textContent = data.stats.audio_alert_count || 0;
      updateStatsUI(data.stats);
    }

  } catch (e) {
    console.warn('Audio send error:', e);
  }
}

function updateVoiceDots(count) {
  ['vd1','vd2','vd3'].forEach((id, i) => {
    const el = document.getElementById(id);
    el.className = 'vd';
    if (i < count) {
      el.classList.add(count === 1 ? 'lit-1' : count === 2 ? 'lit-2' : 'lit-3');
    }
  });
}

// ─────────────────────────────────────────────────────────────
//  MONITORING START / STOP
// ─────────────────────────────────────────────────────────────
async function startMonitoring() {
  try {
    STATE.stream = await navigator.mediaDevices.getUserMedia({
      video: { width:{ideal:640}, height:{ideal:480}, facingMode:'user' },
      audio: true    // request mic for audio monitoring
    });

    const video = document.getElementById('videoFeed');
    video.srcObject = STATE.stream;

    document.getElementById('videoOverlay').classList.add('hidden');
    document.getElementById('processedFeed').style.display = 'block';
    document.getElementById('faceBadge').style.display = 'flex';
    document.getElementById('recIndicator').style.display = 'flex';

    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled  = false;
    setStatus('MONITORING', true);

    STATE.monitoring    = true;
    STATE.sessionStart  = Date.now();
    document.getElementById('footerSessionStart').textContent = new Date().toLocaleTimeString();

    // FPS counter
    STATE.fpsTimer = setInterval(() => {
      document.getElementById('vfFPS').textContent = STATE.fpsFrames;
      STATE.fpsFrames = 0;
    }, 1000);

    // Video analysis
    STATE.frameInterval = setInterval(captureAndAnalyze, 500);
    // Stats refresh
    STATE.statsInterval = setInterval(fetchStats, 2000);

    // Audio
    await startAudioMonitoring(STATE.stream);

  } catch (err) {
    // If camera works but mic denied, restart with video only
    if (err.name === 'NotAllowedError' || err.name === 'NotFoundError') {
      try {
        STATE.stream = await navigator.mediaDevices.getUserMedia({ video:true, audio:false });
        document.getElementById('videoFeed').srcObject = STATE.stream;
        document.getElementById('videoOverlay').classList.add('hidden');
        document.getElementById('processedFeed').style.display = 'block';
        document.getElementById('faceBadge').style.display = 'flex';
        document.getElementById('recIndicator').style.display = 'flex';
        document.getElementById('startBtn').disabled = true;
        document.getElementById('stopBtn').disabled  = false;
        setStatus('MONITORING (no mic)', true);
        STATE.monitoring   = true;
        STATE.sessionStart = Date.now();
        STATE.fpsTimer     = setInterval(() => { document.getElementById('vfFPS').textContent = STATE.fpsFrames; STATE.fpsFrames = 0; }, 1000);
        STATE.frameInterval = setInterval(captureAndAnalyze, 500);
        STATE.statsInterval = setInterval(fetchStats, 2000);
        document.getElementById('footerAudio').textContent = '✕ NO MIC';
        document.getElementById('footerAudio').style.color = 'var(--text3)';
      } catch (e2) {
        alert('Camera access denied: ' + e2.message);
      }
    } else {
      alert('Could not start monitoring: ' + err.message);
    }
  }
}

function stopMonitoring() {
  STATE.monitoring = false;
  if (STATE.stream) {
    STATE.stream.getTracks().forEach(t => t.stop());
    STATE.stream = null;
  }
  clearInterval(STATE.frameInterval);
  clearInterval(STATE.statsInterval);
  clearInterval(STATE.fpsTimer);
  stopAudioMonitoring();

  document.getElementById('videoOverlay').classList.remove('hidden');
  document.getElementById('videoOverlay').innerHTML = '<div class="overlay-icon">⏹</div><div>Session Ended</div>';
  document.getElementById('processedFeed').style.display = 'none';
  document.getElementById('faceBadge').style.display = 'none';
  document.getElementById('recIndicator').style.display = 'none';
  document.getElementById('startBtn').disabled = false;
  document.getElementById('stopBtn').disabled  = true;
  setStatus('STOPPED', false);
}

async function resetSession() {
  stopMonitoring();
  await fetch('/api/reset', { method:'POST' });
  STATE.timelineData   = [];
  STATE.violationCount = 0;
  STATE.copyCount = STATE.pasteCount = STATE.cutCount = 0;
  STATE.audioPeakDb = -100; STATE.audioSamples = 0;
  document.getElementById('cpCopyCount').textContent  = '0';
  document.getElementById('cpPasteCount').textContent = '0';
  document.getElementById('cpCutCount').textContent   = '0';
  document.getElementById('astAlerts').textContent    = '0';
  document.getElementById('astPeak').textContent      = '--';
  document.getElementById('astSamples').textContent   = '0';
  document.getElementById('violationLog').innerHTML = `
    <div class="log-empty">
      <div class="log-empty-icon">🛡️</div>
      <div>No violations detected</div>
      <div class="log-empty-sub">Start monitoring to begin</div>
    </div>`;
  document.getElementById('logCount').textContent = '0 events';
  updateVoiceDots(0);
  updateStatsUI({ violation_score:0, no_face_count:0, multiple_face_count:0,
                  tab_switch_count:0, phone_count:0, copy_paste_count:0,
                  audio_alert_count:0, total_frames:0 });
  dismissAlert();
  document.getElementById('videoOverlay').innerHTML = '<div class="overlay-icon">📷</div><div>Click START to begin monitoring</div>';
  document.getElementById('footerDuration').textContent = '00:00';
  STATE.sessionStart = null;
  setStatus('INITIALIZING', false);
}

// ─────────────────────────────────────────────────────────────
//  FRAME CAPTURE
// ─────────────────────────────────────────────────────────────
const _canvas = document.createElement('canvas');
const _ctx    = _canvas.getContext('2d');

async function captureAndAnalyze() {
  const video = document.getElementById('videoFeed');
  if (!video.videoWidth || !STATE.monitoring) return;
  _canvas.width  = video.videoWidth;
  _canvas.height = video.videoHeight;
  _ctx.drawImage(video, 0, 0);
  STATE.fpsFrames++;

  try {
    const res  = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frame: _canvas.toDataURL('image/jpeg', 0.8) })
    });
    const data = await res.json();
    if (data.error) return;

    if (data.processed_frame) {
      document.getElementById('processedFeed').src = data.processed_frame;
    }

    const fc = data.face_count;
    document.getElementById('vfFaces').textContent = fc;
    document.getElementById('faceIcon').textContent  = fc===0 ? '🚫' : fc===1 ? '✅' : '⚠️';
    document.getElementById('faceLabel').textContent = fc===0 ? 'NO FACE' : fc===1 ? '1 FACE OK' : fc+' FACES!';
    document.getElementById('faceBadge').classList.toggle('alert-badge', fc!==1);

    if (data.alert) {
      showAlert(data.alert, data.severity);
      const type = fc===0 ? 'noface' : data.phone_detected ? 'phone' : 'multi';
      STATE.timelineData.push({ t: Date.now(), type });
    }

    if (data.stats) updateStatsUI(data.stats);
    document.getElementById('vfFrames').textContent = data.stats?.total_frames || 0;

    if (data.yolo_active !== undefined) {
      const el = document.getElementById('yoloStatus');
      el.textContent  = data.yolo_active ? '✓ YOLOv8' : '⚠ FALLBACK';
      el.style.color  = data.yolo_active ? 'var(--green)' : 'var(--yellow)';
    }
  } catch (e) { console.warn('Frame error:', e); }
}

// ─────────────────────────────────────────────────────────────
//  STATS
// ─────────────────────────────────────────────────────────────
async function fetchStats() {
  try {
    const res  = await fetch('/api/stats');
    const data = await res.json();
    updateStatsUI(data.stats);
    updateViolationLog(data.violations);
  } catch (e) {}
}

function updateStatsUI(s) {
  if (!s) return;
  const score = Math.min(s.violation_score || 0, 100);
  document.getElementById('arcScore').textContent = score;
  const arc = document.getElementById('arcFill');
  arc.style.strokeDashoffset = 251.2 - (score/100)*251.2;

  let color, label, cls;
  if      (score < 20) { color='var(--green)';  label='CLEAN';     cls=''; }
  else if (score < 40) { color='var(--yellow)'; label='CAUTION';   cls='medium'; }
  else if (score < 70) { color='var(--orange)'; label='HIGH RISK'; cls='high'; }
  else                 { color='var(--red)';    label='CRITICAL';  cls='critical'; }
  arc.style.stroke = color;
  const rl = document.getElementById('riskLabel');
  rl.textContent = label; rl.className = 'risk-label ' + cls;
  document.getElementById('footerIntegrity').textContent =
    score < 20 ? '✓ SECURE' : score < 40 ? '⚠ CAUTION' : '✗ AT RISK';
  document.getElementById('footerIntegrity').style.color = color;

  const total = Math.max(s.total_frames, 1);
  setBar('rbNoFace', 'rbNoFaceVal', s.no_face_count,       Math.min((s.no_face_count/total)*500, 100));
  setBar('rbMulti',  'rbMultiVal',  s.multiple_face_count,  Math.min((s.multiple_face_count/total)*1000, 100));
  setBar('rbPhone',  'rbPhoneVal',  s.phone_count,           Math.min((s.phone_count/total)*800, 100));
  setBar('rbCP',     'rbCPVal',     s.copy_paste_count,      Math.min(s.copy_paste_count * 12, 100));
  setBar('rbAudio',  'rbAudioVal',  s.audio_alert_count,     Math.min(s.audio_alert_count * 10, 100));
  setBar('rbTab',    'rbTabVal',    s.tab_switch_count,       Math.min(s.tab_switch_count * 10, 100));

  animateStatCard('scNoFace', 'scNoFaceVal', s.no_face_count);
  animateStatCard('scMulti',  'scMultiVal',  s.multiple_face_count);
  animateStatCard('scPhone',  'scPhoneVal',  s.phone_count);
  animateStatCard('scCP',     'scCPVal',     s.copy_paste_count);
  animateStatCard('scAudio',  'scAudioVal',  s.audio_alert_count);
  animateStatCard('scTab',    'scTabVal',    s.tab_switch_count);
  document.getElementById('vfFrames').textContent = s.total_frames;
}

function setBar(barId, valId, val, pct) {
  document.getElementById(barId).style.width = (pct||0) + '%';
  document.getElementById(valId).textContent  = val || 0;
}

function animateStatCard(cardId, valId, newVal) {
  const el  = document.getElementById(valId);
  const old = parseInt(el.textContent) || 0;
  if ((newVal||0) > old) {
    document.getElementById(cardId).classList.add('fired');
    setTimeout(() => document.getElementById(cardId).classList.remove('fired'), 800);
  }
  el.textContent = newVal || 0;
}

// ─────────────────────────────────────────────────────────────
//  VIOLATION LOG
// ─────────────────────────────────────────────────────────────
const ICONS = {
  NO_FACE:           '🙈',
  MULTIPLE_FACES:    '👥',
  TAB_SWITCH:        '🔀',
  PHONE_DETECTED:    '📱',
  COPY_PASTE:        '📋',
  AUDIO_MULTIPLE_VOICES: '🎙️',
  AUDIO_LOUD:        '🔊',
};

function updateViolationLog(violations) {
  if (!violations || violations.length === STATE.violationCount) return;
  STATE.violationCount = violations.length;
  document.getElementById('logCount').textContent = violations.length + ' events';
  document.getElementById('violationLog').innerHTML = violations.map(v => `
    <div class="log-entry ${v.severity}">
      <span class="le-id">#${v.id}</span>
      <span class="le-time">${v.timestamp}</span>
      <span class="le-icon">${ICONS[v.type] || '⚠️'}</span>
      <div class="le-content">
        <div class="le-type ${v.severity}">${v.type.replace(/_/g,' ')}</div>
        <div class="le-msg">${v.message}</div>
      </div>
    </div>`).join('');
}

function clearLog() {
  fetch('/api/reset', { method:'POST' }).then(() => {
    document.getElementById('violationLog').innerHTML = `
      <div class="log-empty"><div class="log-empty-icon">🛡️</div><div>Log cleared</div></div>`;
    document.getElementById('logCount').textContent = '0 events';
    STATE.violationCount = 0;
  });
}

function exportLog() {
  fetch('/api/violations').then(r => r.json()).then(data => {
    const csv = ['ID,Time,Type,Message,Severity',
      ...data.map(v => `${v.id},${v.timestamp},${v.type},"${v.message}",${v.severity}`)
    ].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type:'text/csv' }));
    a.download = `proctor_${STATE.sessionId}_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  });
}

// ─────────────────────────────────────────────────────────────
//  ALERT
// ─────────────────────────────────────────────────────────────
let alertTO;
function showAlert(msg, severity='warning') {
  const b = document.getElementById('alertBanner');
  document.getElementById('alertText').textContent = msg;
  b.classList.add('show');
  b.style.background         = severity==='critical' ? 'var(--red-dim)'    : 'var(--yellow-dim)';
  b.style.borderBottomColor  = severity==='critical' ? 'var(--red)'        : 'var(--yellow)';
  document.getElementById('alertText').style.color = severity==='critical' ? 'var(--red)' : 'var(--yellow)';
  document.querySelector('.pulse-dot').className = 'pulse-dot alert';
  clearTimeout(alertTO);
  alertTO = setTimeout(dismissAlert, 6000);
}
function dismissAlert() {
  document.getElementById('alertBanner').classList.remove('show');
  if (STATE.monitoring) document.querySelector('.pulse-dot').className = 'pulse-dot active';
}

// ─────────────────────────────────────────────────────────────
//  STATUS
// ─────────────────────────────────────────────────────────────
function setStatus(text, active) {
  document.getElementById('statusText').textContent = text;
  document.querySelector('.pulse-dot').className = 'pulse-dot' + (active ? ' active' : '');
}

// ─────────────────────────────────────────────────────────────
//  TIMELINE CHART
// ─────────────────────────────────────────────────────────────
function drawTimeline() {
  const canvas = document.getElementById('timelineChart');
  const W = canvas.offsetWidth || 300;
  const H = canvas.offsetHeight || 80;
  canvas.width  = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, W, H);

  // Grid
  ctx.strokeStyle = 'rgba(30,37,48,0.8)'; ctx.lineWidth = 1;
  for (let i=0; i<=4; i++) {
    ctx.beginPath(); ctx.moveTo(0,H*i/4); ctx.lineTo(W,H*i/4); ctx.stroke();
  }

  const now = Date.now(), WINDOW = 30000, BS = 1000;
  const N = WINDOW / BS;
  const buckets = Array.from({length:N}, () => ({noface:0,multi:0,tab:0,phone:0,cp:0,audio:0}));

  STATE.timelineData.forEach(ev => {
    if (ev.t < now - WINDOW) return;
    const idx = Math.floor((ev.t - (now-WINDOW)) / BS);
    if (idx < 0 || idx >= N) return;
    buckets[idx][ev.type === 'noface' ? 'noface'
                : ev.type === 'multi'  ? 'multi'
                : ev.type === 'phone'  ? 'phone'
                : ev.type === 'cp'     ? 'cp'
                : ev.type === 'audio'  ? 'audio'
                : 'tab']++;
  });
  STATE.timelineData = STATE.timelineData.filter(ev => ev.t > now - WINDOW*2);

  const bW = W / N;
  buckets.forEach((b, i) => {
    const x = i * bW;
    if (b.noface > 0) {
      ctx.fillStyle = 'rgba(255,59,92,0.85)';
      ctx.fillRect(x+1, H*0.05, bW-2, H*0.95);
    } else if (b.phone > 0) {
      ctx.fillStyle = 'rgba(176,109,255,0.85)';
      ctx.fillRect(x+1, H*0.1, bW-2, H*0.9);
    } else if (b.audio > 0) {
      ctx.fillStyle = 'rgba(0,212,212,0.85)';
      ctx.fillRect(x+1, H*0.15, bW-2, H*0.85);
    } else if (b.cp > 0) {
      ctx.fillStyle = 'rgba(77,159,255,0.85)';
      ctx.fillRect(x+1, H*0.2, bW-2, H*0.8);
    } else if (b.multi > 0) {
      ctx.fillStyle = 'rgba(255,122,47,0.8)';
      ctx.fillRect(x+1, H*0.3, bW-2, H*0.7);
    } else if (b.tab > 0) {
      ctx.fillStyle = 'rgba(255,212,71,0.6)';
      ctx.fillRect(x+1, H*0.5, bW-2, H*0.5);
    } else if (STATE.monitoring) {
      ctx.fillStyle = 'rgba(0,229,160,0.12)';
      ctx.fillRect(x+1, H*0.88, bW-2, H*0.12);
    }
  });

  // Now marker
  ctx.strokeStyle = 'rgba(0,229,160,0.5)'; ctx.lineWidth=1.5;
  ctx.setLineDash([3,3]);
  ctx.beginPath(); ctx.moveTo(W-1,0); ctx.lineTo(W-1,H); ctx.stroke();
  ctx.setLineDash([]);
}
