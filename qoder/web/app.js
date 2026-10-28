/* WenGu frontend: hash-routed, dependency-free, all content escaped. */

const root = document.getElementById('root');
const modalRoot = document.getElementById('modal-root');
const drawerRoot = document.getElementById('drawer-root');
const toastRoot = document.getElementById('toast-root');
const TZ = 'Asia/Shanghai';

const S = {
  slug: localStorage.getItem('wengu.slug') || 'demo',
  bootstrap: null,
  view: null,
  scope: null,
  route: 'home',
  includeEarly: false,
  library: { query: '', kind: 'all', topic: 'all', hits: null },
  memory: { q: '', kind: '', state: '', data: null, changes: [] },
  review: null,
  usage: null,
  feedback: [],
  proof: null,
  busy: false,
};

const ROUTES = {
  home: { title: '今日接力', sub: '接着上次，往下学' },
  library: { title: '知识库', sub: '卡片与原始笔记' },
  review: { title: '复习', sub: '一次只处理一张' },
  memory: { title: '记忆中心', sub: 'PowerContext 里的一切' },
  growth: { title: '成长与反馈', sub: '真实使用记录' },
  about: { title: '关于温故', sub: '它如何记住你' },
};

const NAV = [
  ['home', 'home', '今日接力'],
  ['library', 'book', '知识库'],
  ['review', 'repeat', '复习'],
  ['memory', 'database', '记忆中心'],
  ['growth', 'chart', '成长与反馈'],
  ['about', 'info', '关于温故'],
];

const RATING_META = [
  { value: 0, label: '忘记', hint: '完全想不起来' },
  { value: 1, label: '模糊', hint: '有印象但说不清' },
  { value: 2, label: '掌握', hint: '基本能讲明白' },
  { value: 3, label: '熟练', hint: '能举例、能迁移' },
];

const KIND_LABELS = {
  profile: '学习画像',
  knowledge: '知识卡片',
  review: '复习记录',
  struggle: '卡点记忆',
  session: '学习会话',
  feedback: '使用反馈',
};

const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-6h6v6"/>',
  book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v18H6.5A2.5 2.5 0 0 1 4 18.5z"/><path d="M4 5.5v13"/><path d="M8 7h8"/>',
  repeat: '<path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  chart: '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M12 16V4"/><path d="m6 10 6-6 6 6"/><path d="M4 20h16"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  arrow: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  spark: '<path d="m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6v14H5V6"/><path d="M10 11v6M14 11v6"/>',
  external: '<path d="M14 3h7v7"/><path d="M21 3 10 14"/><path d="M21 14v7H3V3h7"/>',
  download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M4 21h16"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14-4L4 9"/><path d="M4 4v5h5"/><path d="M4 13a8 8 0 0 0 14 4l2-2"/><path d="M20 20v-5h-5"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
  play: '<path d="m8 5 11 7-11 7z"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  link: '<path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9"/><path d="m17 6 3 3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  flag: '<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>',
  eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
};

function icon(name, cls = '') {
  const path = ICONS[name] || '';
  return `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}

/* ------------------------------------------------------------------ */
/* Utilities                                                           */
/* ------------------------------------------------------------------ */

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char];
  });
}

function pct(value, total) {
  if (!total) return 0;
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)));
}

function fmtDate(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: TZ,
    year: date.getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
    month: 'numeric',
    day: 'numeric',
  }).format(date);
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: TZ,
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function dateKey(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const get = (type) => parts.find((part) => part.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

function todayKey() {
  return dateKey(new Date().toISOString());
}

function relTime(iso) {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(diff)) return '—';
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.round(hours / 24);
  if (days === 1) return '昨天';
  if (days < 30) return `${days} 天前`;
  return fmtDate(iso);
}

function todayLong() {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: TZ,
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(new Date());
}

function clip(value, limit) {
  const text = String(value ?? '').trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function humanText(value) {
  return String(value ?? '')
    .replace(/(?:\\n|\n)§meta§ \{(?:[^\\}]|\\.)*?\}/g, '')
    .trim();
}

function stars(value) {
  const n = Math.max(0, Math.min(5, Number(value) || 0));
  return '★'.repeat(n) + '☆'.repeat(5 - n);
}

function statusBadge(status, label) {
  return `<span class="badge ${esc(status)}"><span class="dot"></span>${esc(label)}</span>`;
}

function loadingHTML() {
  return `<div class="loading" aria-busy="true">
    <div class="skeleton h1"></div>
    <div class="skeleton block"></div>
    <div class="skeleton block"></div>
  </div>`;
}

function emptyHTML(iconName, title, body, action = '') {
  return `<div class="empty">
    ${icon(iconName)}
    <h3>${esc(title)}</h3>
    <p>${esc(body)}</p>
    ${action ? `<div style="margin-top:16px">${action}</div>` : ''}
  </div>`;
}

async function api(path, { method = 'GET', body } = {}) {
  const response = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!response.ok) {
    const error = new Error((data && data.detail) || `请求失败（${response.status}）`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function learnerPath(path) {
  return `/api/learners/${encodeURIComponent(S.slug)}${path}`;
}

function toast(message, type = 'ok') {
  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : ''}`;
  el.innerHTML = `${icon(type === 'error' ? 'info' : 'check')}<span>${esc(message)}</span>`;
  toastRoot.appendChild(el);
  window.setTimeout(() => el.remove(), 4200);
}

function handleError(error) {
  console.error(error);
  toast(error?.message || '操作失败，请稍后重试', 'error');
}

/* ------------------------------------------------------------------ */
/* Overlays                                                            */
/* ------------------------------------------------------------------ */

function lockBody() {
  document.body.style.overflow = 'hidden';
}

function unlockBody() {
  if (!modalRoot.innerHTML && !drawerRoot.innerHTML) document.body.style.overflow = '';
}

function openModal(html, { wide = false } = {}) {
  modalRoot.innerHTML = `<div class="overlay" data-overlay="modal">
    <div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true">${html}</div>
  </div>`;
  modalRoot.querySelector('[data-overlay]').addEventListener('click', (event) => {
    if (event.target.dataset.overlay === 'modal') closeModal();
  });
  lockBody();
  window.setTimeout(() => {
    modalRoot.querySelector('input, textarea, select, button')?.focus();
  }, 40);
}

function closeModal() {
  modalRoot.innerHTML = '';
  unlockBody();
}

function openDrawer(html) {
  drawerRoot.innerHTML = `<div class="drawer-overlay" data-close-drawer></div>
    <aside class="drawer" role="dialog" aria-modal="true">${html}</aside>`;
  drawerRoot.querySelector('[data-close-drawer]').addEventListener('click', closeDrawer);
  lockBody();
}

function closeDrawer() {
  drawerRoot.innerHTML = '';
  unlockBody();
}

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  if (modalRoot.innerHTML) closeModal();
  else if (drawerRoot.innerHTML) closeDrawer();
});

/* ------------------------------------------------------------------ */
/* Boot, learner, shell                                                */
/* ------------------------------------------------------------------ */

function parseRoute() {
  const raw = (location.hash || '').replace(/^#\/?/, '').split('?')[0];
  if (!raw) return 'home';
  return Object.prototype.hasOwnProperty.call(ROUTES, raw) ? raw : 'home';
}

async function refreshBootstrap() {
  S.bootstrap = await api('/api/bootstrap');
  return S.bootstrap;
}

function pickLearner() {
  const learners = S.bootstrap?.learners || [];
  if (!learners.length) {
    S.slug = '';
    return;
  }
  if (!learners.some((learner) => learner.slug === S.slug)) {
    const preferred = S.bootstrap.demo?.available ? 'demo' : learners[0].slug;
    S.slug = preferred;
  }
  localStorage.setItem('wengu.slug', S.slug);
}

async function refreshLearner(includeEarly = S.includeEarly, retry = true) {
  const suffix = includeEarly ? '?include_early=true' : '';
  try {
    const data = await api(learnerPath(suffix));
    S.view = data.view;
    S.scope = data.scope;
    return data;
  } catch (error) {
    if (error.status === 404 && retry) {
      await refreshBootstrap();
      pickLearner();
      if (S.slug) return refreshLearner(includeEarly, false);
      location.hash = '#/welcome';
    }
    throw error;
  }
}

function renderShell(active = S.route) {
  const learner = S.view?.profile || {};
  const stats = S.view?.stats || {};
  const scope = S.scope || {};
  const learners = S.bootstrap?.learners || [];
  const version = S.bootstrap?.powercontext_version || '…';
  const options = learners
    .map(
      (item) =>
        `<option value="${esc(item.slug)}" ${item.slug === S.slug ? 'selected' : ''}>${esc(
          item.name
        )}</option>`
    )
    .join('');
  const nav = NAV.map(([route, iconName, label]) => {
    const badge =
      route === 'home' && stats.due_now
        ? `<span class="nav-badge">${stats.due_now}</span>`
        : route === 'memory' && stats.memory?.records
        ? `<span class="nav-badge">${stats.memory.records}</span>`
        : '';
    return `<a href="#/${route}" class="${active === route ? 'active' : ''}" data-nav="${route}">
      ${icon(iconName)}<span>${label}</span>${badge}
    </a>`;
  }).join('');

  root.innerHTML = `
    <div class="app-shell">
      <aside class="sidebar" id="sidebar">
        <a class="brand" href="#/home" aria-label="温故首页">
          <img src="/static/assets/logo.svg" alt="" width="44" height="44" />
          <span class="brand-name"><strong>温故</strong><span>WenGu</span></span>
        </a>

        <div class="learner-box">
          <label for="learner-select">当前学习者</label>
          <select id="learner-select" class="learner-select" aria-label="切换学习者">
            ${options}
          </select>
          <p class="goal">${esc(learner.goal || '还没有设定学习目标')}</p>
          <div class="meta-row">
            <span>${esc(learner.daily_minutes || 20)} 分钟 / 天</span>
            <button type="button" class="text-btn" data-action="edit-profile">设置</button>
          </div>
          <div class="meta-row">
            <button type="button" class="text-btn" data-action="new-learner">＋ 新建学习空间</button>
          </div>
        </div>

        <nav class="nav" aria-label="主导航">
          <div class="nav-label">学习空间</div>
          ${nav}
        </nav>

        <div class="sidebar-foot">
          <span class="status-pill"><span class="status-dot"></span> PowerContext ${esc(version)} 已连接</span>
          <p class="sidebar-note">记忆以 Scope / Memory entry 保存在本机，0 次模型调用。<br />Scope ${esc(
            String(scope.scope_id || '').slice(0, 18)
          )}…</p>
        </div>
      </aside>
      <div class="sidebar-scrim hidden" id="scrim"></div>

      <div class="content">
        <header class="topbar">
          <button type="button" class="menu-btn" data-action="toggle-menu" aria-label="打开导航">${icon(
            'menu'
          )}</button>
          <div class="crumb">
            <span>温故</span><span class="sep"></span><strong>${esc(
              ROUTES[active]?.title || '今日接力'
            )}</strong>
          </div>
          <div class="spacer"></div>
          <span class="today">${esc(todayLong())}</span>
          <button type="button" class="btn small ghost" data-action="nav" data-route="memory">
            ${icon('database')} 记忆 rev ${esc(stats.memory?.revision ?? '—')}
          </button>
        </header>
        <main class="main" id="main"></main>
      </div>
    </div>`;

  document.getElementById('scrim').addEventListener('click', () => toggleMenu(false));
}

function toggleMenu(open) {
  const sidebar = document.getElementById('sidebar');
  const scrim = document.getElementById('scrim');
  if (!sidebar || !scrim) return;
  const shouldOpen = typeof open === 'boolean' ? open : !sidebar.classList.contains('open');
  sidebar.classList.toggle('open', shouldOpen);
  scrim.classList.toggle('hidden', !shouldOpen);
}

function setMain(html) {
  const main = document.getElementById('main');
  if (main) main.innerHTML = html;
}

/* ------------------------------------------------------------------ */
/* Router                                                              */
/* ------------------------------------------------------------------ */

async function renderRoute() {
  const route = parseRoute();
  S.route = route;
  closeModal();
  closeDrawer();
  toggleMenu(false);

  if (route === 'welcome') {
    renderWelcome();
    return;
  }
  if (!S.bootstrap) await refreshBootstrap();
  if (!S.slug) {
    renderWelcome();
    return;
  }
  if (S.includeEarly && route !== 'review') {
    S.includeEarly = false;
    S.view = null;
  }
  if (!S.view) await refreshLearner();
  renderShell(route);
  await renderRouteBody();
  window.scrollTo({ top: 0, behavior: 'auto' });
}

async function renderRouteBody() {
  switch (S.route) {
    case 'library':
      await renderLibrary();
      break;
    case 'review':
      renderReview();
      break;
    case 'memory':
      await renderMemory();
      break;
    case 'growth':
      await renderGrowth();
      break;
    case 'about':
      await renderAbout();
      break;
    default:
      renderHome();
  }
}

async function reloadRoute() {
  await refreshLearner();
  renderShell(S.route);
  await renderRouteBody();
}

/* ------------------------------------------------------------------ */
/* Home                                                                */
/* ------------------------------------------------------------------ */

function planRow(item, index) {
  const reasons = (item.reasons || [])
    .slice(0, 4)
    .map((reason) => {
      const allowed = ['struggle', 'new', 'overdue', 'lapse', 'scheduled'];
      const cls = allowed.includes(reason.code) ? reason.code : 'last';
      if (reason.entry_id) {
        return `<button type="button" class="chip ${cls}" data-action="open-memory" data-entry="${esc(
          reason.entry_id
        )}" title="查看这条 PowerContext 记忆">${icon('link')}${esc(reason.text)}</button>`;
      }
      return `<span class="chip ${cls}">${esc(reason.text)}</span>`;
    })
    .join('');
  const due = item.is_new
    ? '第一次学习'
    : item.last_reviewed_at
    ? `上次 ${relTime(item.last_reviewed_at)}`
    : '待复习';
  return `<article class="plan-row">
    <div class="plan-index">${String(index + 1).padStart(2, '0')}</div>
    <div class="plan-body">
      <div class="plan-top">
        <span class="topic-chip">${esc(item.topic)}</span>
        ${statusBadge(item.status, item.status_label)}
      </div>
      <h3>${esc(item.prompt)}</h3>
      <div class="plan-chips">${reasons}</div>
    </div>
    <div class="plan-side">
      <span class="due">${esc(due)}</span>
      <button type="button" class="btn small" data-action="review-item" data-item="${esc(
        item.item_id
      )}">开始 · ${Math.max(1, Math.round(item.estimated_minutes))}′</button>
    </div>
  </article>`;
}

function renderHome() {
  const view = S.view;
  if (!view) return;
  const { stats, plan, continuity, coach_memory: coach, profile } = view;
  const reviewedToday = view.reviews.filter((review) => dateKey(review.at) === todayKey()).length;
  const totalToday = reviewedToday + plan.items.length;
  const donePct = pct(reviewedToday, totalToday);
  const streak = stats.streak_recent || 0;

  const planHTML = plan.items.length
    ? plan.items.map((item, index) => planRow(item, index)).join('')
    : `<div class="card">${emptyHTML(
        plan.empty ? 'spark' : 'book',
        plan.empty_reason ? '今天没有到期任务' : '先放进一张知识卡',
        plan.empty_reason || '导入一段笔记，温故会自动拆成卡片并安排复习。',
        `<div class="btn-row" style="justify-content:center">
          <button type="button" class="btn primary" data-action="early-review">${icon(
            'repeat'
          )} 提前复习</button>
          <button type="button" class="btn" data-action="import-notes">${icon('upload')} 导入笔记</button>
        </div>`
      )}</div>`;

  const weak = (coach.weak_points || [])
    .map(
      (point) => `<div class="weak-item">
        <p>${esc(point.text)}</p>
        <div class="weak-meta">
          <span>${esc(point.topic || '未分类')}</span>
          <span>·</span>
          <span>${esc(fmtDate(point.at))}</span>
          <button type="button" class="text-btn" data-action="open-memory" data-entry="${esc(
            point.entry_id
          )}">记忆 #${esc(String(point.entry_id).replace('mem_ent_', '').slice(0, 8))}</button>
        </div>
      </div>`
    )
    .join('');

  const prefs = (coach.preferences || [])
    .map(
      (pref) =>
        `<span class="pref"><b>${esc(pref.label)}</b>${esc(pref.text || '')}</span>`
    )
    .join('');

  const activity = (stats.activity_7d || [])
    .map((day) => {
      const max = Math.max(1, ...(stats.activity_7d || []).map((entry) => entry.count));
      const height = Math.max(day.count ? 8 : 2, Math.round((day.count / max) * 100));
      const today = day.date === todayKey();
      return `<div class="bar-col ${today ? 'is-today' : ''}" title="${esc(day.date)} · ${day.count} 次复习">
        <span class="bar-value">${day.count || ''}</span>
        <div class="bar-track"><div class="bar-fill" style="height:${height}%"></div></div>
        <span class="bar-label">${esc(day.label)}</span>
      </div>`;
    })
    .join('');

  const topics = (stats.topics || [])
    .slice(0, 4)
    .map(
      (topic) => `<div class="topic-row">
        <span class="topic-name" title="${esc(topic.topic)}">${esc(topic.topic)}</span>
        <div class="topic-track"><div class="topic-fill" style="width:${topic.mastery}%"></div></div>
        <span class="topic-num">${topic.mastery}%</span>
      </div>
      <div class="topic-meta"><span>${topic.items} 张卡</span><span>${topic.due} 张到期</span><span>${topic.struggles} 个卡点</span></div>`
    )
    .join('');

  const recent = (view.recent || [])
    .slice(0, 7)
    .map(
      (entry) => `<div class="tl-item ${esc(entry.kind)}" role="button" tabindex="0" data-action="open-memory" data-entry="${esc(
        entry.entry_id
      )}" title="查看记忆原文">
        <span class="tl-dot"></span>
        <div class="tl-main">
          <p class="tl-kind">${esc(entry.kind_label)}</p>
          <p>${esc(entry.human)}</p>
        </div>
        <span class="tl-time">${esc(relTime(entry.at))}</span>
      </div>`
    )
    .join('');

  const firstName = (profile.name || '你').slice(0, 12);
  const heroTitle = continuity.has_history ? continuity.headline : '第一次见面，从现在开始记';
  const heroBody = continuity.body;

  setMain(`
    <section class="hero fade-in">
      <div>
        <p class="eyebrow">${esc(firstName)} · ${esc(todayLong())}</p>
        <h1>${esc(heroTitle)}</h1>
        <p class="hero-body">${esc(heroBody)}</p>
        <div class="hero-actions">
          <button type="button" class="btn primary" data-action="start-review" ${
            plan.items.length ? '' : 'disabled'
          }>${icon('play')} 接着学${
    plan.items.length ? ` · ${plan.estimated_minutes} 分钟` : ''
  }</button>
          <button type="button" class="btn ghost" data-action="nav" data-route="memory">
            ${icon('database')} 看它记住了什么
          </button>
        </div>
        <div class="hero-meta">
          <span>${esc(continuity.last_seen_at ? `上次学习 ${relTime(continuity.last_seen_at)}` : '还没有学习记录')}</span>
          <span class="dot-sep"></span>
          <span>目标：${esc(clip(profile.goal || '未设置', 40))}</span>
          <span class="dot-sep"></span>
          <span>最近连续 ${streak} 天</span>
        </div>
      </div>
      <div class="hero-side">
        <div class="ring" style="--p:${donePct}">
          <div class="ring-inner"><strong>${plan.items.length}</strong><span>项等待接力</span></div>
        </div>
        <p class="side-caption">今日已完成 ${reviewedToday} / ${totalToday}<br />PowerContext 记忆 rev ${esc(
    stats.memory?.revision ?? '—'
  )}</p>
      </div>
    </section>

    <div class="stat-strip" style="margin-top:18px">
      <div class="stat">
        <span class="num">${stats.due_review}<small>张</small></span>
        <span class="label">到期复习</span>
        <span class="trend">按记忆重放排序</span>
      </div>
      <div class="stat">
        <span class="num">${stats.new_items}<small>张</small></span>
        <span class="label">新知识待学</span>
        <span class="trend">每次最多约 40%</span>
      </div>
      <div class="stat">
        <span class="num">${stats.open_struggles}<small>个</small></span>
        <span class="label">未解决卡点</span>
        <span class="trend">会自动插到队首</span>
      </div>
      <div class="stat">
        <span class="num">${stats.reviews_total}<small>次</small></span>
        <span class="label">累计复习</span>
        <span class="trend">${stats.sessions_total} 次学习会话</span>
      </div>
    </div>

    <div class="dash-grid" style="margin-top:28px">
      <div class="stack">
        <section>
          <div class="section-head">
            <div>
              <h2>今天的接力清单</h2>
              <p class="hint">从 ${stats.items_total} 张卡片和 ${stats.reviews_total} 条复习记忆中重放得出</p>
            </div>
            <div class="btn-row">
              <button type="button" class="btn small ghost" data-action="early-review">${icon(
                'clock'
              )} 提前复习</button>
              <button type="button" class="btn small ghost" data-action="nav" data-route="library">${icon(
                'book'
              )} 全部卡片</button>
            </div>
          </div>
          <div class="plan-list">${planHTML}</div>
          ${
            plan.items.length
              ? `<p class="small muted" style="margin-top:12px;line-height:1.7">${esc(plan.why)}</p>`
              : ''
          }
        </section>

        <div class="two-col">
          <section class="card panel">
            <div class="panel-head">
              <h3>最近 7 天复习</h3>
              <span class="hint">累计 ${stats.active_days} 天 · 最近连续 ${streak} 天</span>
            </div>
            <div class="bars">${activity}</div>
          </section>
          <section class="card panel">
            <div class="panel-head">
              <h3>主题掌握度</h3>
              <span class="hint">平均 ${stats.average_mastery}%</span>
            </div>
            ${topics || emptyHTML('chart', '还没有主题', '导入第一段笔记后，这里会出现掌握度。')}
          </section>
        </div>
      </div>

      <div class="stack">
        <section class="card memory-panel">
          <h2>${icon('database')} 教练记得你</h2>
          <p class="memory-summary">${esc(coach.summary)}</p>
          ${
            weak
              ? `<div class="memory-block">
                  <p class="block-label">没解决的卡点</p>
                  <div class="weak-list">${weak}</div>
                </div>`
              : ''
          }
          ${
            prefs
              ? `<div class="memory-block">
                  <p class="block-label">你的偏好</p>
                  <div class="pref-list">${prefs}</div>
                </div>`
              : ''
          }
          ${
            coach.last_next_action
              ? `<div class="memory-block">
                  <p class="block-label">上次留下的下一步</p>
                  <p class="small" style="line-height:1.75">${esc(coach.last_next_action)}</p>
                </div>`
              : ''
          }
          <div class="memory-foot">
            <span>${stats.memory?.records ?? 0} 条记忆 · ${stats.memory?.sources ?? 0} 份原始资料</span>
            <button type="button" class="text-btn" data-action="nav" data-route="memory">打开记忆中心 →</button>
          </div>
        </section>

        <section class="card panel">
          <div class="panel-head">
            <h3>最近的记忆</h3>
            <span class="hint">点开看原文</span>
          </div>
          <div class="timeline">
            ${recent || emptyHTML('database', '还没有记忆', '开始第一次学习后，这里会出现可追溯的记录。')}
          </div>
        </section>
      </div>
    </div>
  `);
}

/* ------------------------------------------------------------------ */
/* Library                                                             */
/* ------------------------------------------------------------------ */

function libraryItems() {
  const view = S.view;
  let items = view.items.slice();
  if (S.library.hits) {
    const byId = new Map(view.items.map((item) => [item.item_id, item]));
    items = S.library.hits
      .map((record) => byId.get(record.meta?.id))
      .filter(Boolean);
  }
  if (S.library.kind === 'due') items = items.filter((item) => item.is_due);
  else if (S.library.kind !== 'all') items = items.filter((item) => item.status === S.library.kind);
  if (S.library.topic !== 'all') items = items.filter((item) => item.topic === S.library.topic);
  return items;
}

function dueLabel(item) {
  if (item.is_new) return '未开始';
  if (item.is_due) {
    return item.overdue_days > 0 ? `逾期 ${item.overdue_days} 天` : '今天到期';
  }
  return `${fmtDate(item.due_at)} 复习`;
}

function knowledgeCard(item) {
  const hit = (S.library.hits || []).find((record) => record.meta?.id === item.item_id);
  return `<article class="card knowledge-card" role="button" tabindex="0" data-action="open-card" data-item="${esc(
    item.item_id
  )}">
    <div class="kc-top">
      <span class="topic-chip">${esc(item.topic)}</span>
      ${statusBadge(item.status, item.status_label)}
    </div>
    <h3>${esc(item.prompt)}</h3>
    <p class="kc-answer">${esc(item.answer)}</p>
    <div class="meter"><i style="width:${item.mastery}%"></i></div>
    <div class="kc-foot">
      <span>掌握 ${item.mastery}% · ${item.review_count} 次</span>
      <span>${hit ? `匹配 ${Number(hit.score).toFixed(2)}` : dueLabel(item)}</span>
    </div>
  </article>`;
}

function paintLibrary() {
  const view = S.view;
  if (!view) return;
  const allItems = view.items;
  const counts = {
    all: allItems.length,
    due: allItems.filter((item) => item.is_due).length,
    new: allItems.filter((item) => item.status === 'new').length,
    learning: allItems.filter((item) => item.status === 'learning').length,
    review: allItems.filter((item) => item.status === 'review').length,
    mastered: allItems.filter((item) => item.status === 'mastered').length,
  };
  const filters = [
    ['all', '全部'],
    ['due', '待复习'],
    ['new', '新知识'],
    ['learning', '学习中'],
    ['review', '复习中'],
    ['mastered', '已掌握'],
  ];
  const items = libraryItems();
  const topics = new Set(allItems.map((item) => item.topic));
  const topicOptions = Array.from(topics)
    .sort()
    .map(
      (topic) =>
        `<option value="${esc(topic)}" ${S.library.topic === topic ? 'selected' : ''}>${esc(
          topic
        )}</option>`
    )
    .join('');

  setMain(`
    <div class="page-head">
      <div>
        <h1>知识库</h1>
        <p class="sub">每张卡片都对应一条 PowerContext 记忆和一份原始资料。搜索直接走记忆库的全文索引。</p>
      </div>
      <div class="page-actions">
        <button type="button" class="btn" data-action="import-notes">${icon('upload')} 导入笔记</button>
        <button type="button" class="btn primary" data-action="add-card">${icon('plus')} 新建卡片</button>
      </div>
    </div>

    <div class="toolbar">
      <form class="search-box" data-form="library-search" role="search">
        ${icon('search')}
        <input class="input" id="library-q" name="q" value="${esc(
          S.library.query
        )}" placeholder="全文检索：梯度、贝叶斯、precision…" autocomplete="off" />
      </form>
      <select class="select" id="library-topic" style="width:auto;min-width:150px" aria-label="按主题筛选">
        <option value="all">全部主题</option>
        ${topicOptions}
      </select>
      <div class="filter-chips">
        ${filters
          .map(
            ([value, label]) =>
              `<button type="button" class="filter-chip ${
                S.library.kind === value ? 'active' : ''
              }" data-action="library-filter" data-kind="${value}">${label}<span class="count">${counts[value]}</span></button>`
          )
          .join('')}
      </div>
    </div>

    ${
      S.library.query
        ? `<p class="small muted" style="margin:-6px 0 14px">PowerContext 检索「${esc(
            S.library.query
          )}」：命中 ${S.library.hits?.length ?? 0} 条知识卡片</p>`
        : ''
    }

    <div class="knowledge-grid" id="library-grid">
      ${
        items.length
          ? items.map(knowledgeCard).join('')
          : `<div class="card" style="grid-column:1/-1">${emptyHTML(
              'search',
              S.library.query ? '没有匹配的卡片' : '这个筛选下还没有卡片',
              S.library.query
                ? '试试更短的关键词，或清空搜索看全部卡片。'
                : '换个筛选条件，或者导入一段新笔记。',
              S.library.query
                ? `<button type="button" class="btn" data-action="clear-library-search">清空搜索</button>`
                : `<button type="button" class="btn primary" data-action="add-card">新建第一张卡片</button>`
            )}</div>`
      }
    </div>
  `);
}

async function renderLibrary() {
  setMain(loadingHTML());
  if (S.library.query) {
    const data = await api(
      learnerPath(
        `/memory?q=${encodeURIComponent(S.library.query)}&kind=knowledge&state=active`
      )
    );
    S.library.hits = data.records;
  } else {
    S.library.hits = null;
  }
  paintLibrary();
}

function openCardDrawer(itemId) {
  const item = S.view?.items.find((entry) => entry.item_id === itemId);
  if (!item) return;
  const struggles = (item.open_struggles || [])
    .map(
      (struggle) =>
        `<span class="chip struggle">${icon('flag')}${esc(struggle.text)}</span>`
    )
    .join('');
  openDrawer(`
    <div class="drawer-head">
      <div>
        <span class="topic-chip">${esc(item.topic)}</span>
        <div style="margin-top:8px">${statusBadge(item.status, item.status_label)}</div>
      </div>
      <button type="button" class="btn-icon" data-action="close-drawer" aria-label="关闭">${icon(
        'x'
      )}</button>
    </div>
    <div class="drawer-body">
      <h2>${esc(item.prompt)}</h2>
      <div class="drawer-section">
        <p class="label">答案 / 说明</p>
        <div class="answer-body">${esc(item.answer)}</div>
      </div>
      ${struggles ? `<div class="drawer-section"><p class="label">你记过的卡点</p><div class="tag-row">${struggles}</div></div>` : ''}
      <dl class="meta-grid">
        <div class="meta-cell"><dt>掌握度</dt><dd>${item.mastery}%</dd></div>
        <div class="meta-cell"><dt>复习次数</dt><dd>${item.review_count} 次</dd></div>
        <div class="meta-cell"><dt>下次到期</dt><dd>${esc(dueLabel(item))}</dd></div>
        <div class="meta-cell"><dt>难度系数</dt><dd>${item.ease}</dd></div>
        <div class="meta-cell"><dt>间隔</dt><dd>${item.interval_days} 天</dd></div>
        <div class="meta-cell"><dt>遗忘次数</dt><dd>${item.lapses}</dd></div>
      </dl>
      <div class="drawer-actions">
        <button type="button" class="btn primary" data-action="review-item" data-item="${esc(
          item.item_id
        )}">${icon('play')} 复习这张</button>
        ${
          item.source_id
            ? `<button type="button" class="btn" data-action="load-source" data-source="${esc(
                item.source_id
              )}">${icon('book')} 原始资料</button>`
            : ''
        }
        ${
          item.entry_id
            ? `<button type="button" class="btn ghost" data-action="open-memory" data-entry="${esc(
                item.entry_id
              )}">${icon('link')} 记忆条目</button>`
            : ''
        }
      </div>
      <div id="source-panel"></div>
    </div>
  `);
}

/* ------------------------------------------------------------------ */
/* Review                                                              */
/* ------------------------------------------------------------------ */

function reviewCardFromPlan(item) {
  return {
    item_id: item.item_id,
    prompt: item.prompt,
    answer: item.answer,
    topic: item.topic,
    status: item.status,
    status_label: item.status_label,
    mastery: item.mastery,
    last_rating: item.last_rating,
    last_rating_label: item.last_rating_label,
    open_struggles: item.open_struggles || [],
    estimated_minutes: item.estimated_minutes,
    reasons: item.reasons || [],
  };
}

function startReview(itemId = null) {
  const planItems = S.view?.plan?.items || [];
  let queue = planItems.map(reviewCardFromPlan);
  if (!queue.length) {
    toast('今天没有到期卡片，可以试试提前复习', 'error');
    return;
  }
  if (itemId) {
    const chosen = queue.find((item) => item.item_id === itemId);
    const fallback = S.view.items.find((item) => item.item_id === itemId);
    const card = chosen || (fallback ? reviewCardFromPlan(fallback) : null);
    if (card) queue = [card, ...queue.filter((item) => item.item_id !== itemId)];
  }
  S.review = {
    queue,
    index: 0,
    reveal: false,
    note: '',
    reviewed: 0,
    ratings: { 0: 0, 1: 0, 2: 0, 3: 0 },
    startedAt: new Date().toISOString(),
    sessionId: `s_${Date.now().toString(36)}`,
    next: null,
    finished: false,
    saving: false,
    saveError: '',
  };
  if (parseRoute() === 'review') {
    renderShell('review');
    paintReview();
  } else {
    location.hash = '#/review';
  }
}

async function beginEarlyReview() {
  if (S.busy) return;
  S.busy = true;
  try {
    S.includeEarly = true;
    await refreshLearner(true);
    renderShell(S.route);
    if (S.route === 'review') paintReview();
    else startReview();
    toast('已提前放入最接近到期的卡片');
  } catch (error) {
    handleError(error);
  } finally {
    S.busy = false;
  }
}

function paintReview() {
  const review = S.review;
  if (!review) {
    renderReviewIntro();
    return;
  }
  if (review.finished) {
    renderReviewDone();
    return;
  }
  const card = review.queue[review.index];
  if (!card) {
    renderReviewDone();
    return;
  }
  const progress = pct(review.index, review.queue.length);
  const struggleChips = (card.open_struggles || [])
    .map((struggle) => `<span class="chip struggle">${icon('flag')}${esc(struggle.text)}</span>`)
    .join('');
  const ratings = RATING_META.map(
    (meta) => `<button type="button" class="rating-btn r${meta.value}" data-action="rate" data-rating="${meta.value}">
      <strong>${meta.label}</strong><span>${meta.hint}</span>
    </button>`
  ).join('');

  setMain(`
    <div class="review-wrap fade-in">
      <div class="review-topline">
        <div class="progress" aria-hidden="true"><i style="width:${progress}%"></i></div>
        <span class="review-count">${review.index + 1} / ${review.queue.length} · 已评 ${review.reviewed} 张</span>
        <button type="button" class="text-btn" data-action="leave-review">退出本轮</button>
      </div>

      <article class="flashcard card">
        <div class="fc-top">
          <span class="topic-chip">${esc(card.topic)}</span>
          ${statusBadge(card.status, card.status_label)}
          ${struggleChips}
        </div>
        <h2 class="fc-prompt">${esc(card.prompt)}</h2>
        <p class="fc-hint">${
          review.reveal
            ? '对照下面的答案，诚实评价。评价会写入记忆并决定下次间隔。'
            : '先在心里讲一遍，再翻面。想不起来也没关系，那正是要补的地方。'
        }</p>

        ${
          review.reveal
            ? `<div class="fc-answer">${esc(card.answer)}</div>
               <div class="review-note">
                 <label for="review-note">想记下一个卡点？（可选，会存入记忆）</label>
                 <input class="input" id="review-note" maxlength="500" value="${esc(
                   review.note
                 )}" placeholder="比如：总把偏差和方差的方向记反" autocomplete="off" />
               </div>`
            : ''
        }

        <div class="fc-actions">
          ${
            review.reveal
              ? `<div class="rating-grid">${ratings}</div>`
              : `<button type="button" class="btn primary" data-action="reveal">${icon(
                  'eye'
                )} 翻面看答案</button>`
          }
        </div>
      </article>
      <p class="small muted" style="text-align:center;margin-top:14px">评价 0「忘记」会在 10 分钟后再次出现；其余按记忆重放算法安排间隔。</p>
    </div>
  `);
}

function renderReviewIntro() {
  const plan = S.view?.plan;
  if (!plan) return;
  const preview = plan.items
    .slice(0, 4)
    .map((item) => `<li>${esc(item.prompt)}</li>`)
    .join('');
  if (plan.items.length) {
    setMain(`
      <div class="review-wrap fade-in">
        <section class="card review-intro">
          <p class="eyebrow">复习接力</p>
          <h1>今天的 ${plan.items.length} 张卡片</h1>
          <p class="sub" style="color:var(--muted);line-height:1.8;font-size:13px">按卡点、逾期和上次评价排序。预计 ${plan.estimated_minutes} 分钟，一次只处理一张。</p>
          <ul class="review-preview">${preview}</ul>
          <div class="btn-row">
            <button type="button" class="btn primary" data-action="begin-review">${icon(
              'play'
            )} 开始复习</button>
            <button type="button" class="btn ghost" data-action="nav" data-route="library">先去知识库看看</button>
          </div>
        </section>
      </div>
    `);
  } else {
    setMain(`
      <div class="review-wrap fade-in">
        <section class="card review-intro">
          <p class="eyebrow">复习接力</p>
          <h1>今天没有到期卡片</h1>
          <p class="sub" style="color:var(--muted);line-height:1.8;font-size:13px">${esc(
            plan.empty_reason || '所有卡片都安排好了。'
          )}</p>
          <div class="btn-row" style="margin-top:22px">
            <button type="button" class="btn primary" data-action="early-review">${icon(
              'clock'
            )} 提前复习最接近到期的一张</button>
            <button type="button" class="btn ghost" data-action="nav" data-route="library">去知识库</button>
          </div>
        </section>
      </div>
    `);
  }
}

function renderReview() {
  if (S.review) paintReview();
  else renderReviewIntro();
}

function renderReviewDone() {
  const review = S.review;
  if (!review) return renderReviewIntro();
  const next = review.next || S.view?.next_action || '';
  const rated = Object.entries(review.ratings)
    .filter(([, count]) => count > 0)
    .map(([value, count]) => {
      const meta = RATING_META.find((item) => String(item.value) === value);
      return `<span class="chip">${esc(meta?.label || value)} ${count}</span>`;
    })
    .join('');
  setMain(`
    <div class="review-wrap fade-in">
      <section class="card review-done">
        <div class="done-mark">${icon(review.saveError ? 'info' : 'check')}</div>
        <p class="eyebrow" style="justify-content:center">${
          review.saveError ? '会话尚未保存' : '本轮完成'
        }</p>
        <h1>${review.saveError ? '复习已记住，会话还没写进去' : '今天的接力接上了'}</h1>
        <p class="sub" style="color:var(--muted);font-size:13px;line-height:1.8;margin-top:10px">${
          review.saveError
            ? esc(review.saveError)
            : '每条评价都已写入 PowerContext，下一步也已经记下。'
        }</p>
        <div class="done-stats">
          <div class="done-stat"><strong>${review.reviewed}</strong><span>张已评价</span></div>
          <div class="done-stat"><strong>${Object.values(review.ratings).reduce(
            (sum, value) => sum + value,
            0
          )}</strong><span>次自评</span></div>
          <div class="done-stat"><strong>${
            S.view?.stats?.streak_current ?? 0
          }</strong><span>当前连续天数</span></div>
        </div>
        <div class="tag-row" style="justify-content:center">${rated}</div>
        ${
          next
            ? `<div class="next-card" style="margin-top:22px"><span class="label">下次先攻</span>${esc(
                next
              )}</div>`
            : ''
        }
        <div class="btn-row" style="justify-content:center">
          ${
            review.saveError
              ? `<button type="button" class="btn primary" data-action="retry-finish">${icon(
                  'refresh'
                )} 重试保存</button>`
              : `<button type="button" class="btn primary" data-action="nav" data-route="home">${icon(
                  'home'
                )} 回今日接力</button>
                 <button type="button" class="btn" data-action="reset-review">${icon(
                   'repeat'
                 )} 再学一组</button>`
          }
        </div>
      </section>
    </div>
  `);
}

async function rateCard(rating) {
  const review = S.review;
  if (!review || review.busy) return;
  const card = review.queue[review.index];
  if (!card) return;
  review.busy = true;
  try {
    const result = await api(learnerPath('/reviews'), {
      method: 'POST',
      body: {
        item_id: card.item_id,
        rating,
        note: review.note,
        session_id: review.sessionId,
      },
    });
    review.ratings[rating] += 1;
    review.reviewed += 1;
    review.index += 1;
    review.reveal = false;
    review.note = '';
    toast(result.message || '已记住');
    if (review.index >= review.queue.length) {
      await finishReview();
    } else {
      paintReview();
    }
  } catch (error) {
    handleError(error);
  } finally {
    review.busy = false;
  }
}

async function finishReview() {
  const review = S.review;
  if (!review || review.saving) return;
  if (review.reviewed === 0) {
    review.finished = true;
    paintReview();
    return;
  }
  review.saving = true;
  review.saveError = '';
  try {
    const ratings = {};
    Object.entries(review.ratings).forEach(([key, value]) => {
      if (value > 0) ratings[key] = value;
    });
    const result = await api(learnerPath('/sessions'), {
      method: 'POST',
      body: {
        session_id: review.sessionId,
        started_at: review.startedAt,
        ended_at: new Date().toISOString(),
        reviewed: review.reviewed,
        ratings,
      },
    });
    review.next = result.next_action || '';
    review.finished = true;
    S.includeEarly = false;
    await refreshLearner();
    renderShell('review');
    paintReview();
  } catch (error) {
    review.finished = true;
    review.saveError = `${error.message}。评价已经保存，可以重试写入会话记忆。`;
    paintReview();
  } finally {
    review.saving = false;
  }
}

/* ------------------------------------------------------------------ */
/* Memory center                                                       */
/* ------------------------------------------------------------------ */

function memoryKindLabel(kind) {
  return KIND_LABELS[kind] || kind;
}

function paintMemory() {
  const data = S.memory.data;
  const view = S.view;
  if (!data || !view) return;
  const records = data.records || [];
  const counts = data.counts || {};
  const kinds = [
    ['', '全部'],
    ['knowledge', '知识卡'],
    ['review', '复习'],
    ['struggle', '卡点'],
    ['session', '会话'],
    ['profile', '画像'],
  ];
  const kindOptions = kinds
    .map(
      ([value, label]) =>
        `<button type="button" class="filter-chip ${
          S.memory.kind === value ? 'active' : ''
        }" data-action="memory-kind" data-kind="${value}">${label}${
          value ? `<span class="count">${counts[value] || 0}</span>` : ''
        }</button>`
    )
    .join('');

  const rows = records
    .map(
      (record) => `<button type="button" class="memory-row" data-action="open-memory" data-entry="${esc(
        record.entry_id
      )}">
        <span class="memory-kind"><span class="kind-dot ${esc(record.kind)}"></span>${esc(
        record.kind_label
      )}</span>
        <span class="memory-human">${esc(record.human)}</span>
        <span class="memory-meta">
          <span class="mono">#${esc(record.citation_short)}</span>
          <span>${esc(relTime(record.created_at))}</span>
          ${
            record.score !== undefined
              ? `<span>匹配 ${Number(record.score).toFixed(2)}</span>`
              : record.state !== 'active'
              ? '<span>已删除</span>'
              : ''
          }
        </span>
      </button>`
    )
    .join('');

  const changes = (S.memory.changes || [])
    .slice(0, 8)
    .map(
      (revision) => `<div class="change-item">
        <span class="change-rev">rev ${revision.revision}</span>
        <div class="change-body">
          ${
            revision.changes.length
              ? revision.changes
                  .slice(0, 3)
                  .map(
                    (change) =>
                      `<div><span class="op ${esc(change.op)}">${esc(change.op)}</span>${esc(
                        change.reason || '写入记忆'
                      )}</div>`
                  )
                  .join('')
              : '<div class="reason">无变更</div>'
          }
        </div>
      </div>`
    )
    .join('');

  setMain(`
    <div class="page-head">
      <div>
        <h1>记忆中心</h1>
        <p class="sub">这里没有隐藏的数据库。每一条学习画像、卡片、评价、卡点和会话都是 PowerContext Memory entry，可检索、可修改、可删除、可追溯。</p>
      </div>
      <div class="page-actions">
        <span class="badge accent">rev ${esc(data.revision)}</span>
        <span class="badge">${data.total} 条记忆</span>
        <button type="button" class="btn small" data-action="export">${icon(
          'download'
        )} 导出</button>
      </div>
    </div>

    <div class="toolbar">
      <form class="search-box" data-form="memory-search" role="search">
        ${icon('search')}
        <input class="input" id="memory-q" name="q" value="${esc(
          S.memory.q
        )}" placeholder="全文检索记忆：卡点、梯度、方差…" autocomplete="off" />
      </form>
      <div class="filter-chips">${kindOptions}</div>
      <select class="select" id="memory-state" style="width:auto;min-width:120px" aria-label="按状态筛选">
        <option value="" ${S.memory.state === '' ? 'selected' : ''}>全部状态</option>
        <option value="active" ${S.memory.state === 'active' ? 'selected' : ''}>有效</option>
        <option value="inactive" ${S.memory.state === 'inactive' ? 'selected' : ''}>已删除</option>
      </select>
    </div>

    <div class="memory-layout">
      <section class="card memory-list">
        <div class="memory-list-head">
          <span>${
            data.search
              ? `检索「${esc(data.search.query)}」 · 命中 ${records.length} 条 · 模式 ${esc(
                  data.search.mode || 'auto'
                )}`
              : `显示 ${records.length} 条`
          }</span>
          <span>Memory rev ${esc(data.revision)} · Scope ${esc(
    String(S.scope?.scope_id || '').slice(0, 16)
  )}…</span>
        </div>
        ${
          rows ||
          emptyHTML(
            'search',
            '没有匹配的记忆',
            '换一个关键词，或清除筛选条件。',
            `<button type="button" class="btn small" data-action="clear-memory-search">清空筛选</button>`
          )
        }
      </section>

      <aside class="stack">
        <section class="card panel">
          <div class="panel-head">
            <h3>现场组装上下文</h3>
            <span class="hint">context.prepare</span>
          </div>
          <form data-form="context">
            <div class="field">
              <label for="context-q">给教练一个问题</label>
              <input class="input" id="context-q" name="query" value="最近的学习卡点和学习目标" />
            </div>
            <div class="tag-row" style="margin-top:8px">
              <button type="button" class="chip" data-action="context-preset" data-query="我的学习目标和节奏">目标与节奏</button>
              <button type="button" class="chip" data-action="context-preset" data-query="我反复忘记的知识点">反复忘记</button>
              <button type="button" class="chip" data-action="context-preset" data-query="概率和线代的薄弱环节">薄弱环节</button>
            </div>
            <div class="btn-row" style="margin-top:12px">
              <button type="submit" class="btn primary small">${icon('spark')} 让 PowerContext 组装</button>
            </div>
          </form>
          <div id="context-result">
            <pre class="context-box">准备一段与你的记忆相关的上下文。结果只来自当前 Scope，不调用模型，不联网。</pre>
          </div>
        </section>

        <section class="card panel">
          <div class="panel-head">
            <h3>变更历史</h3>
            <span class="hint">最近 ${S.memory.changes.length} 次</span>
          </div>
          ${changes || '<p class="small muted">还没有写入记录。</p>'}
        </section>

        <section class="card panel">
          <div class="panel-head"><h3>库存</h3><span class="hint">statistics.overview</span></div>
          <div class="proof-grid">
            <div class="proof-cell"><div class="label">原始资料</div><div class="value">${esc(
              view.memory?.sources ?? 0
            )} 份</div></div>
            <div class="proof-cell"><div class="label">有效记忆</div><div class="value">${esc(
              view.memory?.active ?? 0
            )} 条</div></div>
            <div class="proof-cell"><div class="label">模型请求</div><div class="value">${esc(
              view.memory?.model_requests ?? 0
            )} 次</div></div>
            <div class="proof-cell"><div class="label">数据库</div><div class="value">本地 SQLite</div></div>
          </div>
        </section>
      </aside>
    </div>
  `);
}

async function renderMemory() {
  setMain(loadingHTML());
  const params = new URLSearchParams();
  if (S.memory.q) params.set('q', S.memory.q);
  if (S.memory.kind) params.set('kind', S.memory.kind);
  if (S.memory.state) params.set('state', S.memory.state);
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const [data, changes] = await Promise.all([
    api(learnerPath(`/memory${suffix}`)),
    api(learnerPath('/changes')),
  ]);
  S.memory.data = data;
  S.memory.changes = changes.revisions || [];
  paintMemory();
}

function metaRows(record) {
  const meta = record.meta || {};
  const preferred = ['topic', 'prompt', 'rating', 'note', 'text', 'session_id', 'item_id', 'status', 'at'];
  const lines = [];
  preferred.forEach((key) => {
    if (meta[key] !== undefined && meta[key] !== '') {
      lines.push(`${key}: ${typeof meta[key] === 'object' ? JSON.stringify(meta[key]) : meta[key]}`);
    }
  });
  Object.keys(meta)
    .filter((key) => !preferred.includes(key))
    .forEach((key) => {
      const value = meta[key];
      lines.push(`${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`);
    });
  return lines.join('\n');
}

async function openMemoryDrawer(entryId) {
  try {
    const detail = await api(learnerPath(`/memory/${encodeURIComponent(entryId)}`));
    const record = detail.record;
    const source = detail.source;
    const meta = record.meta || {};
    const isProfile = record.kind === 'profile';
    const isOpenStruggle = record.kind === 'struggle' && meta.status === 'open';
    const knowledgeId = record.kind === 'knowledge' ? meta.id : null;
    openDrawer(`
      <div class="drawer-head">
        <div>
          <div class="tag-row">
            <span class="badge">${esc(memoryKindLabel(record.kind))}</span>
            <span class="badge ${record.state === 'active' ? 'new' : 'inactive'}">${
              record.state === 'active' ? '有效' : '已删除'
            }</span>
            <span class="mono" style="font-size:10px;color:var(--muted)">#${esc(
              record.citation_short
            )}</span>
          </div>
          <p class="small muted" style="margin-top:8px">${esc(fmtDateTime(record.created_at))}</p>
        </div>
        <button type="button" class="btn-icon" data-action="close-drawer" aria-label="关闭">${icon(
          'x'
        )}</button>
      </div>
      <div class="drawer-body">
        <div class="answer-body">${esc(record.human)}</div>

        <div class="drawer-section">
          <p class="label">PowerContext 引用<span class="mono">rev ${esc(
            record.memory_revision
          )}</span></p>
          <div class="citation-box">entry_id: ${esc(record.entry_id)}
entry_version_id: ${esc(record.version_id)}
memory_revision: ${esc(record.memory_revision)}</div>
        </div>

        <div class="drawer-section">
          <p class="label">Memory 原文（含类型化元数据）<button type="button" class="text-btn" data-action="copy" data-copy="${esc(
            record.raw_text
          )}">复制</button></p>
          <pre class="raw-box">${esc(record.raw_text)}</pre>
        </div>

        <div class="drawer-section">
          <p class="label">结构化字段</p>
          <pre class="raw-box">${esc(metaRows(record))}</pre>
        </div>

        ${
          source
            ? `<div class="drawer-section">
                <p class="label">原始资料内容</p>
                <pre class="raw-box">${esc(source.content)}</pre>
              </div>`
            : meta.source_id
            ? `<div class="drawer-section">
                <p class="label">原始资料</p>
                <button type="button" class="btn small" data-action="load-source" data-source="${esc(
                  meta.source_id
                )}">读取资料内容</button>
                <div id="source-panel"></div>
              </div>`
            : ''
        }

        ${
          !isProfile
            ? `<div class="drawer-section">
                <p class="label">修正这条记忆<button type="button" class="text-btn" data-action="save-revise" data-entry="${esc(
                  record.entry_id
                )}">保存修改</button></p>
                <textarea class="textarea" id="revise-text" rows="6">${esc(record.human)}</textarea>
                <p class="form-note" style="margin-top:7px">修改会生成新的 entry version；旧版本仍保留在 PowerContext 的 revision 历史里。</p>
              </div>`
            : `<div class="drawer-section">
                <p class="label">学习画像</p>
                <p class="small muted" style="line-height:1.7">画像由引导与「设置」写入。修改后请从左侧「设置」更新，仍会以新的画像记忆保存。</p>
              </div>`
        }

        <div class="drawer-actions">
          ${
            knowledgeId
              ? `<button type="button" class="btn primary" data-action="review-item" data-item="${esc(
                  knowledgeId
                )}">${icon('play')} 复习这张</button>`
              : ''
          }
          ${
            isOpenStruggle
              ? `<button type="button" class="btn" data-action="resolve-struggle" data-entry="${esc(
                  record.entry_id
                )}">${icon('check')} 标记已解决</button>`
              : ''
          }
          ${
            !isProfile && record.state === 'active'
              ? `<button type="button" class="btn danger" data-action="retire" data-entry="${esc(
                  record.entry_id
                )}">${icon('trash')} 删除记忆</button>`
              : ''
          }
        </div>
      </div>
    `);
  } catch (error) {
    handleError(error);
  }
}

/* ------------------------------------------------------------------ */
/* Growth                                                              */
/* ------------------------------------------------------------------ */

function paintGrowth() {
  const usage = S.usage;
  const view = S.view;
  if (!usage || !view) return;
  const maxDay = Math.max(1, ...usage.by_day.map((day) => day.requests));
  const bars = usage.by_day
    .map((day) => {
      const height = Math.max(day.requests ? 7 : 2, Math.round((day.requests / maxDay) * 100));
      const today = day.date === todayKey();
      return `<div class="bar-col ${today ? 'is-today' : ''}" title="${esc(day.date)} · ${
        day.requests
      } 次请求 / ${day.writes} 次写入">
        <span class="bar-value">${day.requests || ''}</span>
        <div class="bar-track"><div class="bar-fill" style="height:${height}%"></div></div>
        <span class="bar-label">${esc(day.label)}</span>
      </div>`;
    })
    .join('');
  const endpoints = usage.top_endpoints
    .map(
      (item) => `<div class="endpoint-row"><span class="mono">${esc(
        item.pattern
      )}</span><span class="chip">${item.count}</span></div>`
    )
    .join('');
  const memoryRows = usage.memory
    .map(
      (item) => `<div class="endpoint-row">
        <span>${esc(item.name)}</span>
        <span class="small muted">${item.memory_active} 条有效 · ${item.sources} 份资料</span>
      </div>`
    )
    .join('');
  const recentRows = usage.recent
    .slice(0, 10)
    .map(
      (row) => `<tr>
        <td>${esc(fmtDateTime(row.ts))}</td>
        <td><span class="chip">${esc(row.method)}</span></td>
        <td class="path" title="${esc(row.path)}">${esc(row.path)}</td>
        <td>${esc(row.status)}</td>
        <td>${esc(row.ms)} ms</td>
      </tr>`
    )
    .join('');
  const feedbackItems = S.feedback
    .map(
      (item) => `<div class="feedback-item">
        <div class="feedback-head">
          <span class="stars">${stars(item.meta?.rating)}</span>
          <span>${esc(item.meta?.name || '匿名学习者')}${
            item.meta?.role ? ` · ${esc(item.meta.role)}` : ''
          }</span>
          <span>${esc(relTime(item.created_at))}</span>
        </div>
        <p class="feedback-text">${esc(item.meta?.text || item.human)}</p>
      </div>`
    )
    .join('');
  const sessions = (view.sessions || [])
    .slice(0, 6)
    .map(
      (session) => `<div class="change-item">
        <span class="change-rev">${esc(fmtDate(session.ended_at))}</span>
        <div class="change-body">
          <div>复习 ${session.reviewed} 张 · ${session.duration_minutes} 分钟${
            session.topics?.length ? ` · ${esc(session.topics.join('、'))}` : ''
          }</div>
          <div class="reason">${esc(session.next_action || '')}</div>
        </div>
      </div>`
    )
    .join('');

  setMain(`
    <div class="page-head">
      <div>
        <h1>成长与反馈</h1>
        <p class="sub">下面的使用数字来自本机 <span class="mono">data/usage.jsonl</span>，每次页面请求和记忆读写都会记录；没有估算或编造的用户。</p>
      </div>
      <div class="page-actions">
        <button type="button" class="btn small" data-action="export">${icon(
          'download'
        )} 导出记忆</button>
        <a class="btn small ghost" href="#/about" data-action="nav" data-route="about">${icon(
          'info'
        )} 技术说明</a>
      </div>
    </div>

    <div class="stat-strip">
      <div class="stat"><span class="num">${usage.total_requests}</span><span class="label">真实 API 请求</span><span class="trend">含页面加载与读写</span></div>
      <div class="stat"><span class="num">${usage.writes}</span><span class="label">记忆写操作</span><span class="trend">POST / PATCH</span></div>
      <div class="stat"><span class="num">${usage.active_days}</span><span class="label">有记录的天数</span><span class="trend">${
        usage.first_seen ? `自 ${esc(fmtDate(usage.first_seen))}` : '等待第一条记录'
      }</span></div>
      <div class="stat"><span class="num">${usage.learners}<small>个</small></span><span class="label">学习空间</span><span class="trend">每个都是独立 Scope</span></div>
    </div>

    <div class="growth-grid" style="margin-top:26px">
      <div class="stack">
        <section class="card panel">
          <div class="panel-head">
            <h3>最近 14 天请求</h3>
            <span class="hint">${usage.total_requests} 次 · 最近 ${
              usage.last_seen ? esc(relTime(usage.last_seen)) : '—'
            }</span>
          </div>
          <div class="bars">${bars}</div>
          <p class="form-note" style="margin-top:12px">每次打开页面或执行记忆操作都会落一行 JSONL。比赛验收时可对照这份真实日志，而不是截图里的数字。</p>
        </section>

        <section class="card panel">
          <div class="panel-head"><h3>最近请求明细</h3><span class="hint">最多 10 条</span></div>
          ${
            recentRows
              ? `<div style="overflow:auto"><table class="usage-table">
                  <thead><tr><th>时间</th><th>方法</th><th>路径</th><th>状态</th><th>耗时</th></tr></thead>
                  <tbody>${recentRows}</tbody>
                </table></div>`
              : '<p class="small muted">还没有请求记录，刷新一次页面就会出现。</p>'
          }
        </section>

        <section class="card panel">
          <div class="panel-head"><h3>学习会话</h3><span class="hint">来自 session 记忆</span></div>
          ${sessions || '<p class="small muted">完成一轮复习后，这里会出现会话摘要。</p>'}
        </section>
      </div>

      <div class="stack">
        <section class="card panel">
          <div class="panel-head"><h3>记忆库存</h3><span class="hint">statistics.overview</span></div>
          ${memoryRows || '<p class="small muted">还没有学习空间。</p>'}
          <div class="divider"></div>
          <div class="proof-grid">
            <div class="proof-cell"><div class="label">模型请求</div><div class="value">0 次</div></div>
            <div class="proof-cell"><div class="label">就绪状态</div><div class="value">离线可用</div></div>
          </div>
        </section>

        <section class="card panel">
          <div class="panel-head"><h3>最常见的调用</h3><span class="hint">按接口聚合</span></div>
          ${endpoints || '<p class="small muted">暂无。</p>'}
        </section>

        <section class="card panel">
          <div class="panel-head"><h3>写一条反馈</h3><span class="hint">写入独立反馈 Scope</span></div>
          <form data-form="feedback">
            <div class="form-grid">
              <div class="field">
                <label for="fb-rating">评分</label>
                <select class="select" id="fb-rating" name="rating">
                  <option value="5">5 · 很有帮助</option>
                  <option value="4">4 · 不错</option>
                  <option value="3">3 · 一般</option>
                  <option value="2">2 · 有点别扭</option>
                  <option value="1">1 · 没解决问题</option>
                </select>
              </div>
              <div class="field">
                <label for="fb-role">身份（可选）</label>
                <input class="input" id="fb-role" name="role" placeholder="如：考研学生 / 开发者" />
              </div>
              <div class="field full">
                <label for="fb-name">称呼（可选）</label>
                <input class="input" id="fb-name" name="name" placeholder="怎么称呼你" />
              </div>
              <div class="field full">
                <label for="fb-text">哪一步帮你省了时间？哪里还别扭？</label>
                <textarea class="textarea" id="fb-text" name="text" required placeholder="具体一点会更有帮助…"></textarea>
              </div>
            </div>
            <div class="btn-row" style="margin-top:12px;align-items:center">
              <button type="submit" class="btn primary">提交反馈</button>
              <span class="form-note">不会上传到第三方，只存在本机 PowerContext。</span>
            </div>
          </form>
        </section>

        <section class="card panel">
          <div class="panel-head"><h3>反馈记录</h3><span class="hint">${S.feedback.length} 条</span></div>
          ${
            feedbackItems ||
            '<p class="small muted">还没有反馈。演示数据里有一条明确标注的示例反馈。</p>'
          }
        </section>
      </div>
    </div>
  `);
}

async function renderGrowth() {
  setMain(loadingHTML());
  const [usage, feedback] = await Promise.all([api('/api/usage'), api('/api/feedback')]);
  S.usage = usage;
  S.feedback = feedback.feedback || [];
  paintGrowth();
}

/* ------------------------------------------------------------------ */
/* About                                                               */
/* ------------------------------------------------------------------ */

function paintAbout() {
  const proof = S.proof;
  const view = S.view;
  if (!proof || !view) return;
  const inventory = proof.inventory || {};
  const search = proof.search || { hits: [] };
  const context = proof.context || {};
  const hits = (search.hits || [])
    .map(
      (hit) => `<div class="proof-hit">${esc(clip(humanText(hit.text), 96))}<span class="score">score ${Number(
        hit.score
      ).toFixed(3)} · ${esc((hit.matched_by || []).join('+'))}</span></div>`
    )
    .join('');
  const citations = (proof.sample_citations || [])
    .slice(0, 3)
    .map(
      (citation) => `<div class="proof-hit"><span class="mono">${esc(
        citation.kind
      )}</span> · <span class="mono">${esc(citation.entry_id)}</span></div>`
    )
    .join('');

  setMain(`
    <section class="card about-hero">
      <div>
        <p class="eyebrow">Qoder × OceanBase 学习效率赛道</p>
        <h1>把「上次学到哪」<br />变成记忆，而不是重新开始。</h1>
        <p>温故（WenGu）是一个离线优先的学习接力教练。它不生成漂亮的笔记，而是记住你的目标、每次自评、说过的卡点和上次留下的下一步；下次打开时，直接把你放回学习现场。</p>
      </div>
      <div class="quote">
        “温故而知新，可以为师矣。”
        <small>《论语·为政》· 产品名字的来处</small>
      </div>
    </section>

    <div class="three-col" style="margin-top:18px">
      <div class="card feature-card">
        <div class="f-icon accent">${icon('target')}</div>
        <h3>痛点：每次都从零解释</h3>
        <p>换设备、隔几天、换个 AI 工具，学习状态就断了。温故把「我是谁、我要去哪、我卡在哪」写成可重放的学习记忆。</p>
      </div>
      <div class="card feature-card">
        <div class="f-icon">${icon('repeat')}</div>
        <h3>做法：记忆驱动计划</h3>
        <p>复习间隔、卡点优先级、每日预算全部由记忆重放计算，不靠模型猜测。评价 0 的卡片 10 分钟后回来，卡点会被顶到队首。</p>
      </div>
      <div class="card feature-card">
        <div class="f-icon gold">${icon('database')}</div>
        <h3>底座：PowerContext</h3>
        <p>每个学习者是一个 Scope；画像、卡片、评价、卡点、会话都是 Memory entry；原始笔记是 Source；检索和上下文组装都走 PowerContext。</p>
      </div>
    </div>

    <section class="section">
      <div class="section-head">
        <div><h2>技术架构</h2><p class="hint">没有第二个数据库，没有模型 API Key。</p></div>
      </div>
      <div class="card arch">
        <div class="arch-layer"><span class="arch-name">浏览器 · 前端</span><span class="arch-desc">原生 JS / CSS，无构建步骤。今日接力、复习、知识库、记忆中心、使用证据。</span></div>
        <div class="arch-arrow">↓</div>
        <div class="arch-layer"><span class="arch-name">FastAPI · 服务层</span><span class="arch-desc">输入校验、学习服务、真实使用日志（data/usage.jsonl）、静态资源。</span></div>
        <div class="arch-arrow">↓</div>
        <div class="arch-layer highlight"><span class="arch-name">温故教练层 · 纯逻辑</span><span class="arch-desc">把记忆重放为卡片状态；SM-2-lite 间隔调度；卡点/逾期/新知识排序；连续性与下一步生成。全部可单元测试。</span></div>
        <div class="arch-arrow">↓</div>
        <div class="arch-layer highlight"><span class="arch-name">PowerContext 1.2.0</span><span class="arch-desc">嵌入式运行时：Scope 隔离、Memory 读写/修订/删除、Source 捕获、中文全文检索、context.prepare、revision 引用与统计。</span></div>
        <div class="arch-arrow">↓</div>
        <div class="arch-layer"><span class="arch-name">SQLite + sqlite-vec</span><span class="arch-desc">本机文件持久化；断网、无 API Key 也能完整运行。演示数据同样走真实写入路径。</span></div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <div><h2>现场证据</h2><p class="hint">下面不是示意图，是当前 Scope 的实时返回值。</p></div>
        <button type="button" class="btn small" data-action="refresh-proof">${icon(
          'refresh'
        )} 刷新</button>
      </div>
      <div class="card panel">
        <div class="proof-grid">
          <div class="proof-cell"><div class="label">Scope</div><div class="value mono">${esc(
            proof.scope_id || ''
          )}</div></div>
          <div class="proof-cell"><div class="label">Memory revision</div><div class="value">${esc(
            proof.memory_revision
          )}</div></div>
          <div class="proof-cell"><div class="label">Memory entries</div><div class="value">${esc(
            inventory.memory_active ?? 0
          )} 有效 / ${esc(inventory.memory_total ?? 0)} 总计</div></div>
          <div class="proof-cell"><div class="label">Sources</div><div class="value">${esc(
            inventory.sources ?? 0
          )} 份原始资料</div></div>
          <div class="proof-cell"><div class="label">模型请求</div><div class="value">${esc(
            inventory.model_requests ?? 0
          )} 次（无需 API Key）</div></div>
          <div class="proof-cell"><div class="label">运行时</div><div class="value">PowerContext ${esc(
            proof.health?.powercontext_version || '?'
          )}</div></div>
        </div>

        <div class="two-col" style="margin-top:18px">
          <div>
            <p class="label" style="font-size:10px;letter-spacing:.16em;color:var(--muted);margin-bottom:8px">中文全文检索「${esc(
              search.query || '卡点'
            )}」</p>
            ${hits || '<p class="small muted">没有命中。</p>'}
          </div>
          <div>
            <p class="label" style="font-size:10px;letter-spacing:.16em;color:var(--muted);margin-bottom:8px">context.prepare 现场输出</p>
            <pre class="context-box">${esc(humanText(context.content) || '（无上下文）')}</pre>
            <p class="form-note">${esc(context.status || '')} · ${esc(
    context.content_bytes ?? 0
  )} bytes · 仅使用当前 Scope 的记忆（展示时隐去温故自己的类型化元数据）</p>
          </div>
        </div>

        <div class="divider"></div>
        <p class="label" style="font-size:10px;letter-spacing:.16em;color:var(--muted);margin-bottom:8px">可追溯的 entry 引用示例</p>
        ${citations || '<p class="small muted">暂无。</p>'}
      </div>
    </section>

    <section class="section">
      <div class="section-head"><div><h2>技术验收对照</h2><p class="hint">对应比赛基础验收项。</p></div></div>
      <div class="two-col">
        <div class="card panel">
          <div class="endpoint-row"><span>PowerContext 作为核心记忆层</span><span class="badge new">已使用</span></div>
          <div class="endpoint-row"><span>Scope / Memory / Sources</span><span class="badge new">已使用</span></div>
          <div class="endpoint-row"><span>中文全文检索 FTS</span><span class="badge new">已使用</span></div>
          <div class="endpoint-row"><span>context.prepare 上下文组装</span><span class="badge new">已使用</span></div>
          <div class="endpoint-row"><span>修订 / 删除 / revision 引用</span><span class="badge new">已使用</span></div>
          <div class="endpoint-row"><span>模型 API 依赖</span><span class="badge">0 次调用</span></div>
        </div>
        <div class="card panel">
          <div class="panel-head"><h3>本地运行</h3><span class="hint">Python 3.11+</span></div>
          <pre class="code-block">cd qoder
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python run.py
# 打开 http://127.0.0.1:8010</pre>
          <p class="form-note" style="margin-top:10px">首次启动会自动写入一份可复现的演示学习记录；设置 <span class="mono">WENGU_AUTO_SEED=0</span> 可关闭。</p>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="card panel">
        <div class="panel-head"><h3>数据与来源说明</h3><span class="hint">诚实披露</span></div>
        <p class="small" style="line-height:1.85;color:var(--ink-2)">
          演示学习者「林知夏」及其卡片、复习、卡点、会话、反馈均为合成的示例数据，用于验证产品流程；写入路径与真实使用完全一致，标有 <span class="mono">seed: true</span>，反馈文本明确标注「演示数据」。页面上的使用统计只来自本机真实请求日志，不包含虚构用户或使用量。
        </p>
        <div class="btn-row" style="margin-top:14px">
          <a class="btn small" href="https://github.com/curryxjh/powercontext" target="_blank" rel="noreferrer">${icon(
            'external'
          )} 代码仓库</a>
          <button type="button" class="btn small ghost" data-action="nav" data-route="memory">${icon(
            'database'
          )} 查看记忆中心</button>
        </div>
      </div>
    </section>
  `);
}

async function renderAbout() {
  setMain(loadingHTML());
  S.proof = await api(learnerPath('/proof?q=卡点'));
  paintAbout();
}

/* ------------------------------------------------------------------ */
/* Welcome + learner modals                                            */
/* ------------------------------------------------------------------ */

function renderWelcome() {
  root.innerHTML = `
    <div class="welcome">
      <div class="welcome-main">
        <div class="brand">
          <img src="/static/assets/logo.svg" alt="" width="44" height="44" />
          <span class="brand-name"><strong>温故</strong><span>WenGu</span></span>
        </div>
        <h1>学习不是重启，<br />是<em>接着来</em>。</h1>
        <p class="lede">温故记住你的目标、每次自评、说过的卡点和上次留下的下一步。离线运行，无需 API Key；所有记忆都在你自己的 PowerContext 里。</p>
        <div class="btn-row">
          ${
            S.bootstrap?.demo?.available
              ? `<button type="button" class="btn accent" data-action="enter-demo">进入演示学习空间</button>`
              : `<button type="button" class="btn primary" data-action="seed-demo">载入演示数据</button>`
          }
          <button type="button" class="btn" data-action="new-learner">创建我的学习空间</button>
        </div>
      </div>
      <aside class="welcome-side">
        <h2>下次打开，直接接着学</h2>
        <div class="welcome-points">
          <div class="welcome-point"><span class="wp-num">1</span><span>导入笔记或建卡，自动拆成可复习的知识点。</span></div>
          <div class="welcome-point"><span class="wp-num">2</span><span>每次只评四档：忘记、模糊、掌握、熟练。间隔由记忆重放决定。</span></div>
          <div class="welcome-point"><span class="wp-num">3</span><span>说过的卡点会被记住，下次直接排到队首。</span></div>
          <div class="welcome-point"><span class="wp-num">4</span><span>在记忆中心查看、修改、删除每一条记忆，并看到引用与版本。</span></div>
        </div>
        <p class="fine">PowerContext 嵌入式运行时 · 本地 SQLite · 0 次模型调用<br />Qoder × OceanBase Build with Qoder 参赛项目</p>
      </aside>
    </div>`;
}

function openLearnerModal() {
  openModal(`
    <div class="modal-head">
      <div>
        <h2>建立一个学习空间</h2>
        <p class="sub">这些信息会作为学习画像写入 PowerContext，决定每天的复习预算与讲解偏好。</p>
      </div>
      <button type="button" class="btn-icon" data-action="close-modal" aria-label="关闭">${icon('x')}</button>
    </div>
    <div class="modal-body">
      <form data-form="learner">
        <div class="form-grid">
          <div class="field">
            <label for="new-name">怎么称呼你</label>
            <input class="input" id="new-name" name="name" maxlength="60" required placeholder="如：林知夏" />
          </div>
          <div class="field">
            <label for="new-minutes">每天可投入</label>
            <select class="select" id="new-minutes" name="daily_minutes">
              <option value="10">10 分钟</option>
              <option value="15">15 分钟</option>
              <option value="20" selected>20 分钟</option>
              <option value="30">30 分钟</option>
              <option value="45">45 分钟</option>
              <option value="60">60 分钟</option>
            </select>
          </div>
          <div class="field full">
            <label for="new-goal">近期学习目标</label>
            <input class="input" id="new-goal" name="goal" maxlength="500" required placeholder="如：两周后通过机器学习期中考试" />
          </div>
          <div class="field full">
            <label for="new-style">喜欢的讲解方式</label>
            <select class="select" id="new-style" name="style">
              <option>图示 + 生活类比</option>
              <option>简洁直给，先结论</option>
              <option>苏格拉底式追问</option>
              <option>例题驱动，边做边学</option>
            </select>
          </div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn ghost" data-action="close-modal">取消</button>
          <button type="submit" class="btn primary">创建并开始</button>
        </div>
      </form>
    </div>
  `);
}

function openProfileModal() {
  const profile = S.view?.profile || {};
  openModal(`
    <div class="modal-head">
      <div>
        <h2>学习设置</h2>
        <p class="sub">保存后会生成一条新的学习画像记忆，旧的画像仍保留在 revision 历史中。</p>
      </div>
      <button type="button" class="btn-icon" data-action="close-modal" aria-label="关闭">${icon('x')}</button>
    </div>
    <div class="modal-body">
      <form data-form="profile">
        <div class="form-grid">
          <div class="field">
            <label for="pf-name">称呼</label>
            <input class="input" id="pf-name" name="name" value="${esc(profile.name || '')}" required />
          </div>
          <div class="field">
            <label for="pf-minutes">每天可投入</label>
            <select class="select" id="pf-minutes" name="daily_minutes">
              ${[10, 15, 20, 30, 45, 60]
                .map(
                  (value) =>
                    `<option value="${value}" ${
                      Number(profile.daily_minutes) === value ? 'selected' : ''
                    }>${value} 分钟</option>`
                )
                .join('')}
            </select>
          </div>
          <div class="field full">
            <label for="pf-goal">学习目标</label>
            <input class="input" id="pf-goal" name="goal" value="${esc(profile.goal || '')}" required />
          </div>
          <div class="field full">
            <label for="pf-style">讲解偏好</label>
            <input class="input" id="pf-style" name="style" value="${esc(profile.style || '')}" />
          </div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn ghost" data-action="close-modal">取消</button>
          <button type="submit" class="btn primary">保存画像</button>
        </div>
      </form>
    </div>
  `);
}

function openKnowledgeModal() {
  const topics = Array.from(new Set((S.view?.topics || []).map((topic) => topic.topic)));
  openModal(`
    <div class="modal-head">
      <div>
        <h2>新建知识卡片</h2>
        <p class="sub">答案会自动捕获为一份 PowerContext Source，卡片本身是一条 knowledge 记忆。</p>
      </div>
      <button type="button" class="btn-icon" data-action="close-modal" aria-label="关闭">${icon('x')}</button>
    </div>
    <div class="modal-body">
      <form data-form="knowledge">
        <div class="form-grid">
          <div class="field">
            <label for="kc-topic">主题</label>
            <input class="input" id="kc-topic" name="topic" list="topic-list" maxlength="40" required placeholder="如：概率统计" />
            <datalist id="topic-list">${topics
              .map((topic) => `<option value="${esc(topic)}"></option>`)
              .join('')}</datalist>
          </div>
          <div class="field">
            <label for="kc-source">来源标题（可选）</label>
            <input class="input" id="kc-source" name="source_title" maxlength="120" placeholder="如：第 3 章笔记" />
          </div>
          <div class="field full">
            <label for="kc-prompt">问题 / 概念</label>
            <input class="input" id="kc-prompt" name="prompt" maxlength="200" required placeholder="如：贝叶斯公式如何把先验和似然变成后验？" />
          </div>
          <div class="field full">
            <label for="kc-answer">答案 / 说明</label>
            <textarea class="textarea" id="kc-answer" name="answer" rows="6" required placeholder="用自己的话讲清楚，最好带一个例子。"></textarea>
          </div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn ghost" data-action="close-modal">取消</button>
          <button type="submit" class="btn primary">保存卡片</button>
        </div>
      </form>
    </div>
  `);
}

function openImportModal() {
  openModal(`
    <div class="modal-head">
      <div>
        <h2>导入一段笔记</h2>
        <p class="sub">支持 Markdown 标题（## 知识点 + 说明）、Q:/A: 问答块，或按自然段自动拆分。原文会作为 Source 完整保存。</p>
      </div>
      <button type="button" class="btn-icon" data-action="close-modal" aria-label="关闭">${icon('x')}</button>
    </div>
    <div class="modal-body">
      <form data-form="import">
        <div class="form-grid">
          <div class="field full">
            <label for="im-topic">默认主题</label>
            <input class="input" id="im-topic" name="topic" maxlength="40" value="" placeholder="可选，例如：数据结构" />
          </div>
          <div class="field full">
            <label for="im-text">粘贴笔记</label>
            <textarea class="textarea" id="im-text" name="text" rows="12" required placeholder="## 梯度下降
损失函数在当前点的梯度指向增长最快的方向，负梯度就是下降最快的方向。

## 交叉验证
把数据分成 k 份轮流做验证，降低单次划分的偶然性。"></textarea>
          </div>
        </div>
        <p class="form-note">拆分后的每张卡片都可以在知识库里单独修改；原文永远可追溯。</p>
        <div class="modal-foot">
          <button type="button" class="btn ghost" data-action="close-modal">取消</button>
          <button type="submit" class="btn primary">${icon('upload')} 拆分并导入</button>
        </div>
      </form>
    </div>
  `, { wide: true });
}

/* ------------------------------------------------------------------ */
/* Actions                                                             */
/* ------------------------------------------------------------------ */

const actions = {
  nav: (el) => {
    const route = el.dataset.route || 'home';
    const target = `#/${route}`;
    if (location.hash === target) renderRoute();
    else location.hash = target;
  },
  'toggle-menu': () => toggleMenu(),
  'new-learner': () => openLearnerModal(),
  'edit-profile': () => openProfileModal(),
  'close-modal': () => closeModal(),
  'close-drawer': () => closeDrawer(),
  'add-card': () => openKnowledgeModal(),
  'import-notes': () => openImportModal(),
  'start-review': () => startReview(),
  'begin-review': () => startReview(),
  'review-item': (el) => {
    closeDrawer();
    startReview(el.dataset.item);
  },
  reveal: () => {
    if (!S.review) return;
    S.review.reveal = true;
    paintReview();
    window.setTimeout(() => {
      document.getElementById('review-note')?.focus({ preventScroll: true });
    }, 60);
  },
  rate: (el) => rateCard(Number(el.dataset.rating)),
  'leave-review': async () => {
    S.review = null;
    S.includeEarly = false;
    await refreshLearner();
    if (parseRoute() === 'home') await renderRoute();
    else location.hash = '#/home';
  },
  'reset-review': () => {
    S.review = null;
    startReview();
  },
  'retry-finish': () => {
    if (!S.review) return;
    S.review.finished = false;
    S.review.saveError = '';
    paintReview();
    finishReview();
  },
  'early-review': () => beginEarlyReview(),
  'library-filter': (el) => {
    S.library.kind = el.dataset.kind || 'all';
    paintLibrary();
  },
  'clear-library-search': () => {
    S.library.query = '';
    S.library.hits = null;
    renderLibrary();
  },
  'open-card': (el) => openCardDrawer(el.dataset.item),
  'open-memory': (el) => openMemoryDrawer(el.dataset.entry),
  'load-source': async (el) => {
    const sourceId = el.dataset.source;
    if (!sourceId) return;
    try {
      const source = await api(learnerPath(`/sources/${encodeURIComponent(sourceId)}`));
      const panel = document.getElementById('source-panel') || drawerRoot;
      if (panel) {
        panel.innerHTML = `<pre class="raw-box" style="margin-top:10px">${esc(
          source.content
        )}</pre><p class="form-note" style="margin-top:6px">Source ${esc(
          source.source_id
        )} · ${esc(source.digest || '')}</p>`;
      }
    } catch (error) {
      handleError(error);
    }
  },
  'memory-kind': (el) => {
    S.memory.kind = el.dataset.kind || '';
    renderMemory().catch(handleError);
  },
  'clear-memory-search': () => {
    S.memory = { q: '', kind: '', state: '', data: S.memory.data, changes: S.memory.changes };
    renderMemory().catch(handleError);
  },
  'context-preset': (el) => {
    const input = document.getElementById('context-q');
    if (input) {
      input.value = el.dataset.query || '';
      input.focus();
    }
  },
  'save-revise': async (el) => {
    const entryId = el.dataset.entry;
    const textarea = document.getElementById('revise-text');
    if (!entryId || !textarea) return;
    const human = textarea.value.trim();
    if (!human) return toast('记忆内容不能为空', 'error');
    try {
      await api(learnerPath(`/memory/${encodeURIComponent(entryId)}/revise`), {
        method: 'POST',
        body: { human },
      });
      closeDrawer();
      toast('记忆已更新，旧版本仍可追溯');
      await reloadRoute();
    } catch (error) {
      handleError(error);
    }
  },
  retire: async (el) => {
    const entryId = el.dataset.entry;
    if (!entryId) return;
    if (!window.confirm('删除这条记忆？它会从教练的判断中移除，但 revision 历史仍保留。')) return;
    try {
      await api(learnerPath(`/memory/${encodeURIComponent(entryId)}/retire`), { method: 'POST' });
      closeDrawer();
      toast('记忆已删除');
      await reloadRoute();
    } catch (error) {
      handleError(error);
    }
  },
  'resolve-struggle': async (el) => {
    const entryId = el.dataset.entry;
    if (!entryId) return;
    try {
      await api(learnerPath(`/struggles/${encodeURIComponent(entryId)}/resolve`), {
        method: 'POST',
      });
      closeDrawer();
      toast('卡点已标记为解决');
      await reloadRoute();
    } catch (error) {
      handleError(error);
    }
  },
  copy: async (el) => {
    const text = el.dataset.copy || '';
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制');
    } catch {
      toast('浏览器不允许复制，请手动选择文本', 'error');
    }
  },
  export: () => {
    const link = document.createElement('a');
    link.href = learnerPath('/export');
    link.download = '';
    document.body.appendChild(link);
    link.click();
    link.remove();
  },
  'refresh-proof': async () => {
    try {
      S.proof = await api(learnerPath('/proof?q=卡点'));
      paintAbout();
      toast('已刷新实时证据');
    } catch (error) {
      handleError(error);
    }
  },
  'seed-demo': async () => {
    try {
      await api('/api/demo/seed', { method: 'POST' });
      await refreshBootstrap();
      S.slug = 'demo';
      localStorage.setItem('wengu.slug', 'demo');
      S.view = null;
      await refreshLearner();
      S.route = 'home';
      if (location.hash === '#/welcome') location.hash = '#/home';
      await renderRoute();
      toast('演示学习空间已载入');
    } catch (error) {
      handleError(error);
    }
  },
  'enter-demo': async () => {
    S.slug = 'demo';
    localStorage.setItem('wengu.slug', 'demo');
    S.view = null;
    try {
      await refreshLearner();
      if (location.hash === '#/welcome') location.hash = '#/home';
      await renderRoute();
    } catch (error) {
      handleError(error);
    }
  },
};

document.addEventListener('click', (event) => {
  const el = event.target.closest('[data-action]');
  if (!el) return;
  const action = el.dataset.action;
  const handler = actions[action];
  if (!handler) return;
  event.preventDefault();
  try {
    const result = handler(el);
    if (result && typeof result.catch === 'function') result.catch(handleError);
  } catch (error) {
    handleError(error);
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  const el = event.target.closest('.knowledge-card, .tl-item');
  if (!el) return;
  event.preventDefault();
  const action = el.dataset.action;
  if (actions[action]) actions[action](el);
});

/* ------------------------------------------------------------------ */
/* Forms and inputs                                                    */
/* ------------------------------------------------------------------ */

document.addEventListener('submit', (event) => {
  const form = event.target.closest('form[data-form]');
  if (!form) return;
  event.preventDefault();
  const kind = form.dataset.form;
  const data = Object.fromEntries(new FormData(form).entries());

  if (kind === 'library-search') {
    S.library.query = String(data.q || '').trim();
    renderLibrary().catch(handleError);
    return;
  }

  if (kind === 'memory-search') {
    S.memory.q = String(data.q || '').trim();
    renderMemory().catch(handleError);
    return;
  }

  if (kind === 'context') {
    const query = String(data.query || '').trim();
    if (!query) return;
    const box = document.getElementById('context-result');
    if (box) box.innerHTML = '<pre class="context-box">正在从 PowerContext 组装…</pre>';
    api(learnerPath('/context'), { method: 'POST', body: { query, max_bytes: 4000 } })
      .then((result) => {
        if (!box) return;
        box.innerHTML = `<div class="tag-row" style="margin-top:10px;margin-bottom:8px">
            <span class="badge new">${esc(result.status)}</span>
            <span class="badge">${esc(result.content_bytes)} bytes</span>
          </div>
          <pre class="context-box">${esc(humanText(result.content) || '（上下文为空）')}</pre>`;
      })
      .catch((error) => {
        handleError(error);
        if (box) box.innerHTML = `<pre class="context-box">组装失败：${esc(error.message)}</pre>`;
      });
    return;
  }

  if (kind === 'feedback') {
    if (!String(data.text || '').trim()) return;
    api('/api/feedback', {
      method: 'POST',
      body: {
        rating: Number(data.rating || 5),
        text: String(data.text),
        role: String(data.role || ''),
        name: String(data.name || ''),
      },
    })
      .then(async () => {
        toast('谢谢，反馈已写入 PowerContext');
        S.feedback = (await api('/api/feedback')).feedback || [];
        paintGrowth();
      })
      .catch(handleError);
    return;
  }

  if (kind === 'knowledge') {
    api(learnerPath('/knowledge'), { method: 'POST', body: data })
      .then(async (result) => {
        closeModal();
        toast('卡片已保存，并捕获了一份原始资料');
        S.library.query = '';
        S.library.hits = null;
        await reloadRoute();
      })
      .catch(handleError);
    return;
  }

  if (kind === 'import') {
    api(learnerPath('/import'), {
      method: 'POST',
      body: { text: String(data.text || ''), topic: String(data.topic || '粘贴的笔记') },
    })
      .then(async (result) => {
        closeModal();
        toast(`已拆分并写入 ${result.parsed.items} 张知识卡片`);
        S.library.query = '';
        S.library.hits = null;
        await reloadRoute();
      })
      .catch(handleError);
    return;
  }

  if (kind === 'learner') {
    api('/api/learners', {
      method: 'POST',
      body: {
        name: String(data.name || ''),
        goal: String(data.goal || ''),
        daily_minutes: Number(data.daily_minutes || 20),
        style: String(data.style || ''),
      },
    })
      .then(async (result) => {
        closeModal();
        S.slug = result.slug;
        localStorage.setItem('wengu.slug', S.slug);
        await refreshBootstrap();
        S.view = null;
        await refreshLearner();
        S.library = { query: '', kind: 'all', topic: 'all', hits: null };
        S.memory = { q: '', kind: '', state: '', data: null, changes: [] };
        S.review = null;
        if (location.hash === '#/home') await renderRoute();
        else location.hash = '#/home';
        toast(`学习空间已建立：${result.name}`);
      })
      .catch(handleError);
    return;
  }

  if (kind === 'profile') {
    api(learnerPath('/profile'), {
      method: 'POST',
      body: {
        name: String(data.name || ''),
        goal: String(data.goal || ''),
        daily_minutes: Number(data.daily_minutes || 20),
        style: String(data.style || ''),
      },
    })
      .then(async () => {
        closeModal();
        toast('学习画像已更新');
        await reloadRoute();
      })
      .catch(handleError);
  }
});

document.addEventListener('input', (event) => {
  if (event.target.id === 'review-note' && S.review) {
    S.review.note = event.target.value;
  }
});

document.addEventListener('change', (event) => {
  if (event.target.id === 'learner-select') {
    const slug = event.target.value;
    if (!slug || slug === S.slug) return;
    S.slug = slug;
    localStorage.setItem('wengu.slug', slug);
    S.view = null;
    S.review = null;
    S.library = { query: '', kind: 'all', topic: 'all', hits: null };
    S.memory = { q: '', kind: '', state: '', data: null, changes: [] };
    refreshLearner()
      .then(() => {
        renderShell(S.route);
        return renderRouteBody();
      })
      .catch(handleError);
    return;
  }
  if (event.target.id === 'library-topic') {
    S.library.topic = event.target.value;
    paintLibrary();
    return;
  }
  if (event.target.id === 'memory-state') {
    S.memory.state = event.target.value;
    renderMemory().catch(handleError);
  }
});

/* ------------------------------------------------------------------ */
/* Boot                                                                */
/* ------------------------------------------------------------------ */

async function init() {
  try {
    await refreshBootstrap();
    pickLearner();
    if (!S.slug) {
      if (!location.hash || location.hash === '#/welcome') history.replaceState(null, '', '#/welcome');
      await renderRoute();
      return;
    }
    await refreshLearner();
    if (!location.hash) history.replaceState(null, '', '#/home');
    if (location.hash === '#/welcome') history.replaceState(null, '', '#/home');
    await renderRoute();
  } catch (error) {
    console.error(error);
    root.innerHTML = `<div class="boot">
      <img src="/static/assets/logo.svg" alt="" width="48" height="48" />
      <h1 style="font-size:22px">温故暂时没有启动</h1>
      <p style="max-width:420px;text-align:center;line-height:1.7;font-size:13px">${
        esc(error.message) || '请检查服务是否在运行。'
      }</p>
      <button type="button" class="btn primary" onclick="location.reload()">重新连接</button>
    </div>`;
  }
}

window.addEventListener('hashchange', () => {
  renderRoute().catch(handleError);
});

init();
