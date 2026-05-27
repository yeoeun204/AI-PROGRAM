// ─── Config ───────────────────────────────────
const API = 'https://ai-program.onrender.com/api';

// ─── State ────────────────────────────────────
let currentLectureId = null;
let allQuizzes = [];
let quizTimers = {};   // quiz_id → { seconds, intervalId }

// ─── Init ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadLectures();
  setupDropZone();
  setupNavigation();
});

// ─── Navigation ───────────────────────────────
function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      navigateTo(item.dataset.page);
    });
  });
}

function navigateTo(page) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelector(`[data-page="${page}"]`)?.classList.add('active');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(`page-${page}`)?.classList.add('active');

  if (page === 'weakness' && currentLectureId) loadWeakNodes(currentLectureId);
}

// ─── 강의 목록 ────────────────────────────────
async function loadLectures() {
  try {
    const res = await fetch(`${API}/lectures`);
    const lectures = await res.json();
    renderLectureList(lectures);
  } catch (e) { console.error(e); }
}

function renderLectureList(lectures) {
  const el = document.getElementById('lectureList');
  if (!lectures.length) {
    el.innerHTML = '<p style="padding:10px 14px;font-size:.82rem;color:var(--text-muted);">아직 없음</p>';
    return;
  }
  el.innerHTML = lectures.map(l => `
    <div class="lecture-item ${l.id === currentLectureId ? 'active' : ''}"
         onclick="selectLecture(${l.id}, '${escHtml(l.title)}')">
      ${escHtml(l.title)}
    </div>`).join('');
}

async function selectLecture(id, title) {
  currentLectureId = id;
  document.querySelectorAll('.lecture-item').forEach(el => el.classList.remove('active'));
  event?.currentTarget?.classList.add('active');
  await Promise.all([loadGraph(id), loadQuizzes(id)]);
  showToast(`"${title}" 선택됨`, 'success');
  navigateTo('graph');
}

// ─── 업로드 ───────────────────────────────────
function setupDropZone() {
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault(); dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) { fileInput.files = e.dataTransfer.files; showFileName(e.dataTransfer.files[0].name); }
  });
  fileInput.addEventListener('change', () => { if (fileInput.files[0]) showFileName(fileInput.files[0].name); });
}
function showFileName(name) { document.getElementById('fileName').textContent = `✓ ${name}`; }

async function uploadLecture() {
  const title = document.getElementById('lectureTitle').value.trim();
  const file  = document.getElementById('fileInput').files[0];
  const text  = document.getElementById('textContent').value.trim();

  if (!title) { showToast('강의 제목을 입력하세요.', 'error'); return; }
  if (!file && !text) { showToast('파일 또는 텍스트를 입력하세요.', 'error'); return; }

  const fd = new FormData();
  fd.append('title', title);
  if (file) fd.append('file', file);
  if (text) fd.append('text_content', text);

  showLoading('AI가 지식 그래프와 퀴즈를 생성 중입니다... (30초~1분)');
  document.getElementById('uploadBtn').disabled = true;

  try {
    const res = await fetch(`${API}/lectures/upload`, { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '업로드 실패');

    showToast(`✅ 완료! 개념 ${data.node_count}개, 퀴즈 ${data.quiz_count}개 생성됨`, 'success');
    currentLectureId = data.lecture_id;
    await loadLectures();
    await Promise.all([loadGraph(data.lecture_id), loadQuizzes(data.lecture_id)]);

    document.getElementById('lectureTitle').value = '';
    document.getElementById('textContent').value = '';
    document.getElementById('fileInput').value = '';
    document.getElementById('fileName').textContent = '';
    navigateTo('graph');
  } catch (e) {
    showToast(`오류: ${e.message}`, 'error');
  } finally {
    hideLoading();
    document.getElementById('uploadBtn').disabled = false;
  }
}

// ─── 지식 그래프 ──────────────────────────────
async function loadGraph(lectureId) {
  try {
    const res = await fetch(`${API}/lectures/${lectureId}/graph`);
    if (!res.ok) throw new Error();
    renderGraph(await res.json());
  } catch {
    document.getElementById('graphEmpty').style.display = 'block';
    document.getElementById('graphTree').style.display  = 'none';
  }
}

function renderGraph(nodes) {
  const tree  = document.getElementById('graphTree');
  const empty = document.getElementById('graphEmpty');
  if (!nodes.length) { empty.style.display = 'block'; tree.style.display = 'none'; return; }
  empty.style.display = 'none'; tree.style.display = 'block';
  tree.innerHTML = nodes.map(renderNode).join('');
}

function renderNode(node) {
  const imp = Math.round(node.importance_score * 100);
  const children = node.children?.length
    ? `<div class="tree-children">${node.children.map(renderNode).join('')}</div>` : '';
  return `
    <div class="tree-node">
      <div class="tree-node-content level-${node.level}" onclick="toggleDesc(this)">
        <div class="node-concept">${escHtml(node.concept)}
          <span style="font-size:.7rem;color:var(--text-muted);font-weight:400;margin-left:6px;">중요도 ${imp}%</span>
        </div>
        <div class="node-desc" style="display:none">${escHtml(node.description)}</div>
      </div>
      ${children}
    </div>`;
}

function toggleDesc(el) {
  const d = el.querySelector('.node-desc');
  d.style.display = d.style.display === 'none' ? 'block' : 'none';
}

// ─── 퀴즈 ────────────────────────────────────
async function loadQuizzes(lectureId) {
  try {
    const res = await fetch(`${API}/lectures/${lectureId}/quizzes`);
    if (!res.ok) throw new Error();
    allQuizzes = await res.json();
    renderQuizzes(allQuizzes);
  } catch {
    document.getElementById('quizList').innerHTML =
      '<div class="graph-empty"><p>퀴즈를 불러오지 못했습니다.</p></div>';
  }
}

function renderQuizzes(quizzes) {
  const container = document.getElementById('quizList');
  if (!quizzes.length) {
    container.innerHTML = '<div class="graph-empty"><p>퀴즈가 없습니다.</p></div>';
    return;
  }
  container.innerHTML = quizzes.map((q, i) => `
    <div class="quiz-card" data-difficulty="${q.difficulty}" id="quiz-card-${q.id}">
      <div class="quiz-meta">
        <span class="quiz-num">Q${i + 1}</span>
        <span class="difficulty-badge ${q.difficulty}">${diffLabel(q.difficulty)}</span>
        <span style="font-size:.75rem;color:var(--text-muted);margin-left:auto;">권장 ${q.recommended_time}초</span>
      </div>
      <p class="quiz-question">${escHtml(q.question)}</p>

      <div class="quiz-answer-area">
        <textarea id="answer-${q.id}" placeholder="여기에 답변을 작성해보세요..."></textarea>
      </div>

      <div class="quiz-submit-row">
        <span class="timer" id="timer-${q.id}">00:00</span>
        <button class="btn-submit" id="submit-btn-${q.id}"
                onclick="submitAnswer(${q.id}, ${q.recommended_time})">
          채점하기
        </button>
        <button class="reveal-btn" onclick="toggleAnswer(this, ${q.id})">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          모범 답안 보기
        </button>
      </div>

      <!-- 채점 결과 -->
      <div class="result-box" id="result-${q.id}"></div>

      <!-- 모범 답안 -->
      <div class="model-answer" id="model-answer-${q.id}">
        <div class="model-answer-label">모범 답안</div>
        <div class="model-answer-text">${escHtml(q.model_answer)}</div>
        <div class="key-points">
          ${q.key_points.map(k => `<span class="key-point">${escHtml(k)}</span>`).join('')}
        </div>
      </div>
    </div>`).join('');

  // 타이머 시작
  quizzes.forEach(q => startTimer(q.id, q.recommended_time));
}

// ─── 타이머 ───────────────────────────────────
function startTimer(quizId, recTime) {
  let secs = 0;
  const el = document.getElementById(`timer-${quizId}`);
  if (!el) return;
  const id = setInterval(() => {
    secs++;
    const m = String(Math.floor(secs / 60)).padStart(2, '0');
    const s = String(secs % 60).padStart(2, '0');
    if (el) {
      el.textContent = `${m}:${s}`;
      el.className = 'timer' + (secs > recTime * 1.5 ? ' danger' : secs > recTime ? ' warning' : '');
    }
  }, 1000);
  quizTimers[quizId] = { seconds: () => secs, intervalId: id };
}

function stopTimer(quizId) {
  if (quizTimers[quizId]) {
    clearInterval(quizTimers[quizId].intervalId);
  }
}

function getElapsedTime(quizId) {
  return quizTimers[quizId] ? quizTimers[quizId].seconds() : 0;
}

// ─── 답변 제출 ────────────────────────────────
async function submitAnswer(quizId, recTime) {
  const userAnswer = document.getElementById(`answer-${quizId}`)?.value.trim();
  if (!userAnswer) { showToast('답변을 입력하세요.', 'error'); return; }

  const timeSpent = getElapsedTime(quizId);
  stopTimer(quizId);

  const submitBtn = document.getElementById(`submit-btn-${quizId}`);
  submitBtn.disabled = true;
  submitBtn.textContent = '채점 중...';

  const fd = new FormData();
  fd.append('user_answer', userAnswer);
  fd.append('time_spent', timeSpent);

  try {
    const res = await fetch(`${API}/quizzes/${quizId}/submit`, { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '채점 실패');

    renderResult(quizId, data);
    submitBtn.textContent = '재채점';
    submitBtn.disabled = false;

    // 오답이면 취약점 자동 갱신
    if (data.evaluation.status !== 'correct' && currentLectureId) {
      setTimeout(() => loadWeakNodes(currentLectureId), 500);
    }
  } catch (e) {
    showToast(`오류: ${e.message}`, 'error');
    submitBtn.textContent = '채점하기';
    submitBtn.disabled = false;
  }
}

function renderResult(quizId, data) {
  const box = document.getElementById(`result-${quizId}`);
  if (!box) return;

  const ev = data.evaluation;
  const color = ev.color || 'red';
  const statusLabel = { correct: '✅ 정답', warning: '⚠️ 근접', error: '❌ 오답' }[ev.status] || '오답';

  let scoreHtml = '';
  if (ev.cosine_similarity !== undefined) {
    scoreHtml = `
      <div class="score-row">
        <div class="score-item">코사인 유사도 <strong>${(ev.cosine_similarity * 100).toFixed(1)}%</strong></div>
        <div class="score-item">키워드 <strong>${ev.matched_keywords}/${ev.total_keywords}</strong></div>
        <div class="score-item">최종 점수 <strong>${(ev.final_score * 100).toFixed(1)}%</strong></div>
        ${ev.is_slip ? '<div class="score-item" style="color:var(--medium);">단순 실수(Slip) 판정</div>' : ''}
      </div>`;
  } else if (ev.relative_error !== undefined) {
    scoreHtml = `
      <div class="score-row">
        <div class="score-item">상대오차 <strong>${(ev.relative_error * 100).toFixed(2)}%</strong></div>
        <div class="score-item">최종 점수 <strong>${(ev.final_score * 100).toFixed(1)}%</strong></div>
      </div>`;
  }

  let analysisHtml = '';
  if (data.llm_analysis) {
    const la = data.llm_analysis;
    const typeLabel = { mistake: '📚 개념 오해', slip: '✏️ 단순 실수', language: '📖 용어 오해' }[la.error_type] || la.error_type;
    analysisHtml = `
      <div class="analysis-section">
        <div class="analysis-label">오류 유형: ${typeLabel}</div>
        <div class="analysis-text">${escHtml(la.feedback)}</div>
      </div>`;
  }

  let causalHtml = '';
  if (data.causal_analysis) {
    const ca = data.causal_analysis;
    causalHtml = `
      <div class="causal-box">
        <div class="causal-cause">📍 원인: ${escHtml(ca.cause)}</div>
        <div class="causal-desc">${escHtml(ca.description)}</div>
      </div>`;
  }

  box.className = `result-box show ${color}`;
  box.innerHTML = `
    <div class="result-header">
      <span class="result-badge ${color}">${statusLabel}</span>
    </div>
    ${scoreHtml}
    ${analysisHtml}
    ${causalHtml}`;
}

function toggleAnswer(btn, quizId) {
  const el = document.getElementById(`model-answer-${quizId}`);
  const shown = el.classList.contains('show');
  el.classList.toggle('show');
  btn.innerHTML = shown
    ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg> 모범 답안 보기`
    : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24M1 1l22 22"/></svg> 답안 숨기기`;
}

function filterQuiz(difficulty, btn) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const filtered = difficulty === 'all' ? allQuizzes : allQuizzes.filter(q => q.difficulty === difficulty);
  renderQuizzes(filtered);
}

// ─── 취약점 분석 ──────────────────────────────
async function loadWeakNodes(lectureId) {
  try {
    const res = await fetch(`${API}/lectures/${lectureId}/weak-nodes`);
    if (!res.ok) throw new Error();
    const nodes = await res.json();
    renderWeakNodes(nodes);
  } catch {
    document.getElementById('weaknessContent').innerHTML =
      '<div class="graph-empty"><p>취약점 데이터가 없습니다. 퀴즈를 먼저 풀어보세요.</p></div>';
  }
}

function renderWeakNodes(nodes) {
  const container = document.getElementById('weaknessContent');
  if (!nodes.length) {
    container.innerHTML = '<div class="graph-empty"><p>아직 퀴즈 기록이 없습니다.</p></div>';
    return;
  }
  container.innerHTML = nodes.map((n, i) => {
    const barWidth = Math.round(n.final_weight * 100);
    const scoreColor = n.avg_score >= 0.90 ? 'var(--easy)' : n.avg_score >= 0.85 ? 'var(--medium)' : 'var(--hard)';
    return `
      <div class="weak-node-card">
        <div class="weak-rank">#${i + 1}</div>
        <div class="weak-info">
          <div class="weak-concept">${escHtml(n.concept)}</div>
          <div class="weak-desc">${escHtml(n.description)}</div>
          <div style="margin-top:6px;font-size:.78rem;color:var(--text-muted);">
            시도 ${n.attempt_count}회 &nbsp;·&nbsp;
            평균 <span style="color:${scoreColor};font-weight:600;">${(n.avg_score * 100).toFixed(1)}점</span>
          </div>
        </div>
        <div class="weak-stats">
          <div class="weight-bar-wrap">
            <div class="weight-bar" style="width:${barWidth}%"></div>
          </div>
          <div class="weight-val">위험도 ${barWidth}%</div>
        </div>
      </div>`;
  }).join('');
}

// ─── 공통 유틸 ────────────────────────────────
function diffLabel(d) {
  return { easy: '🟢 쉬움', medium: '🟡 보통', hard: '🔴 어려움' }[d] || d;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showLoading(text = 'AI가 분석 중입니다...') {
  document.getElementById('loadingText').textContent = text;
  document.getElementById('loadingOverlay').classList.add('show');
}
function hideLoading() { document.getElementById('loadingOverlay').classList.remove('show'); }

let toastTimer;
function showToast(msg, type = 'success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type} show`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 4000);
}
