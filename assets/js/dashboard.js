/* Foreli dashboard — connects to the local backend API (FastAPI + SQLite). */
(function () {
  'use strict';

  // Runtime API base: same-origin by default; config.js or file:// fallback.
  var API_BASE = window.FORELI_API_BASE ||
    (window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '');

  var PRIORITY_ORDER = { urgent: 0, high: 1, medium: 2, low: 3 };
  var STATUS_LABEL = { todo: 'todo', in_progress: 'in progress', done: 'done', cancelled: 'cancelled' };
  var STATUS_BADGE = { todo: 'todo', in_progress: 'progress', done: 'done', cancelled: 'cancelled' };

  // --- state ---
  var tasks = [];
  var stats = null;
  var predictions = [];
  var predictionAnalytics = null;
  var editingId = null;
  var loadState = 'loading'; // 'loading' | 'ready' | 'error'
  var errorMessage = '';
  var state = { view: 'overview', search: '', status: 'all', priority: 'all', sort: 'due' };

  // --- DOM ---
  function $(sel) { return document.querySelector(sel); }
  var el = {
    sidebar: $('#sidebar'), scrim: $('#scrim'), menuToggle: $('#menuToggle'),
    pageTitle: $('#pageTitle'), pageSubtitle: $('#pageSubtitle'), todayLabel: $('#todayLabel'),
    newTaskBtn: $('#newTaskBtn'),
    statGrid: $('#statGrid'), todayList: $('#todayList'), upcomingList: $('#upcomingList'),
    focusCount: $('#focusCount'), upcomingCount: $('#upcomingCount'),
    riskList: $('#riskList'), predictionsList: $('#predictionsList'),
    refreshPredictionsBtn: $('#refreshPredictionsBtn'),
    predictionAnalytics: $('#predictionAnalytics'),
    taskList: $('#taskList'), taskCount: $('#taskCount'), taskListTitle: $('#taskListTitle'),
    searchInput: $('#searchInput'), statusFilter: $('#statusFilter'),
    priorityFilter: $('#priorityFilter'), sortSelect: $('#sortSelect'),
    modal: $('#taskModal'), modalTitle: $('#modalTitle'), taskForm: $('#taskForm'),
    taskTitle: $('#taskTitle'), taskDescription: $('#taskDescription'),
    taskStatus: $('#taskStatus'), taskPriority: $('#taskPriority'),
    taskDue: $('#taskDue'), taskEstimate: $('#taskEstimate'), taskTags: $('#taskTags'),
    saveTaskBtn: $('#saveTaskBtn'), toast: $('#toast'),
    apiStatus: $('#apiStatus'), apiStatusText: $('#apiStatusText'),
    userEmail: $('#userEmail'), logoutBtn: $('#logoutBtn'),
  };

  // --- helpers ---
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function parseLocal(iso) {
    // Stored values are naive local ISO strings; new Date() parses them as local time.
    return iso ? new Date(iso) : null;
  }

  function startOfDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  function dayDiff(d) {
    return Math.round((startOfDay(d) - startOfDay(new Date())) / 86400000);
  }

  function isOverdue(task) {
    if (task.status === 'done' || task.status === 'cancelled') return false;
    if (!task.due_at) return false;
    var d = parseLocal(task.due_at);
    return d && d < new Date();
  }

  function formatDue(task) {
    if (!task.due_at) return { text: 'No due date', cls: '' };
    var d = parseLocal(task.due_at);
    if (!d) return { text: 'Invalid date', cls: '' };
    var diff = dayDiff(d);
    var time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    var monthDay = d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    if (diff === 0) return { text: 'Today · ' + time, cls: 'today' };
    if (diff === 1) return { text: 'Tomorrow · ' + time, cls: '' };
    if (diff === -1) return { text: 'Yesterday · ' + time, cls: 'overdue' };
    if (diff < -1) return { text: 'Overdue · ' + monthDay, cls: 'overdue' };
    return { text: monthDay + ' · ' + time, cls: '' };
  }

  function badge(priority) {
    return '<span class="badge badge-' + esc(priority) + '">' + esc(priority) + '</span>';
  }

  function statusBadge(status) {
    return '<span class="badge badge-' + STATUS_BADGE[status] + '">' + STATUS_LABEL[status] + '</span>';
  }

  function extractError(data) {
    var d = data && data.detail;
    if (!d) return 'Request failed';
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      return d.map(function (e) {
        var loc = e.loc && e.loc.length ? e.loc.join('.') + ': ' : '';
        return loc + (e.msg || 'Invalid value');
      }).join('; ');
    }
    return 'Request failed';
  }

  function api(path, options) {
    options = options || {};
    options.headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    options.credentials = options.credentials || 'include';
    return fetch(API_BASE + path, options).then(function (res) {
      if (res.status === 204) return null;
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          if (res.status === 401) window.location.href = 'login.html';
          var err = new Error(extractError(data));
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  var toastTimer;
  function showToast(message, type) {
    el.toast.textContent = message;
    el.toast.className = 'toast show' + (type === 'error' ? ' error' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.toast.className = 'toast'; }, 3200);
  }

  // --- data loading ---
  function refresh() {
    loadState = 'loading';
    errorMessage = '';
    render();
    return Promise.all([
      api('/api/tasks'),
      api('/api/stats'),
      api('/api/predictions'),
      api('/api/predictions/analytics'),
    ])
      .then(function (results) {
        tasks = results[0] || [];
        stats = results[1] || null;
        predictions = results[2] || [];
        predictionAnalytics = results[3] || null;
        loadState = 'ready';
        render();
      })
      .catch(function (err) {
        loadState = 'error';
        errorMessage = err.message;
        render();
        showToast('Could not reach Foreli backend: ' + err.message, 'error');
      });
  }

  function checkHealth() {
    api('/api/health')
      .then(function (h) {
        el.apiStatus.className = 'api-status ok';
        el.apiStatusText.textContent = 'API connected';
      })
      .catch(function () {
        el.apiStatus.className = 'api-status err';
        el.apiStatusText.textContent = 'API offline';
      });
  }

  function checkAuth() {
    api('/api/auth/me')
      .then(function (user) {
        if (el.userEmail) el.userEmail.textContent = user.email;
      })
      .catch(function () {
        window.location.href = 'login.html';
      });
  }

  // --- render ---
  function render() {
    renderTopbar();
    if (state.view === 'overview') renderOverview();
    else if (state.view === 'tasks') renderTasks();
    else renderPredictionsView();
  }

  function renderTopbar() {
    var titles = {
      overview: ['Overview', 'Your day, at a glance.'],
      tasks: ['Tasks', 'Plan, prioritize, and stay on top of it.'],
      predictions: ['Predictions', 'Anticipate what could go wrong — and why.'],
    };
    el.pageTitle.textContent = titles[state.view][0];
    el.pageSubtitle.textContent = titles[state.view][1];
    el.todayLabel.textContent = new Date().toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });
  }

  function renderOverview() {
    renderStats();
    renderFocusList();
    renderUpcomingList();
    renderRisk();
  }

  function renderStats() {
    var cards = [
      { key: 'due_today', label: 'Due today', icon: '◷', cls: 'today' },
      { key: 'overdue', label: 'Overdue', icon: '⚠', cls: 'overdue' },
      { key: 'completed_today', label: 'Completed today', icon: '✓', cls: 'completed' },
      { key: 'due_next7', label: 'Next 7 days', icon: '◈', cls: 'upcoming' },
    ];
    var html = cards.map(function (c) {
      var value = '…';
      if (loadState === 'ready' && stats) value = stats[c.key];
      else if (loadState === 'error') value = '—';
      return '<article class="stat ' + c.cls + '">' +
        '<div class="stat-icon">' + c.icon + '</div>' +
        '<div class="stat-value">' + value + '</div>' +
        '<div class="stat-label">' + c.label + '</div>' +
        '</article>';
    }).join('');
    el.statGrid.innerHTML = html;
  }

  function focusTasks() {
    var now = new Date();
    return tasks.filter(function (t) {
      if (t.status === 'done' || t.status === 'cancelled') return false;
      if (!t.due_at) return false;
      var d = parseLocal(t.due_at);
      return d && (d < now || dayDiff(d) === 0);
    }).sort(byDue);
  }

  function upcomingTasks() {
    var now = new Date();
    return tasks.filter(function (t) {
      if (t.status === 'done' || t.status === 'cancelled') return false;
      if (!t.due_at) return false;
      var d = parseLocal(t.due_at);
      return d && d >= startOfDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
    }).sort(byDue);
  }

  function byDue(a, b) {
    var ad = a.due_at || '9999', bd = b.due_at || '9999';
    return ad < bd ? -1 : ad > bd ? 1 : 0;
  }

  function renderFocusList() {
    var items = focusTasks();
    el.focusCount.textContent = items.length ? items.length + ' task' + (items.length > 1 ? 's' : '') : '';
    el.todayList.innerHTML = buildList(items, { compact: true, empty: 'Nothing due right now. Enjoy the calm.', overdue: true });
  }

  function renderUpcomingList() {
    var items = upcomingTasks().slice(0, 8);
    var all = upcomingTasks();
    el.upcomingCount.textContent = all.length > 8 ? 'showing 8 of ' + all.length : '';
    el.upcomingList.innerHTML = buildList(items, { compact: true, empty: 'No upcoming tasks scheduled.' });
  }

  function renderTasks() {
    var filtered = filterTasks();
    el.taskListTitle.textContent = 'All tasks';
    el.taskCount.textContent = filtered.length ? filtered.length + ' task' + (filtered.length > 1 ? 's' : '') : '';
    el.taskList.innerHTML = buildList(filtered, { compact: false, empty: 'No tasks match your filters.' });
  }

  function buildList(items, opts) {
    if (loadState === 'loading') {
      return '<li class="placeholder"><div class="spinner"></div>Loading…</li>';
    }
    if (loadState === 'error') {
      return '<li class="placeholder error">' + esc(errorMessage) +
        '<br><span class="retry" data-action="retry">Retry</span></li>';
    }
    if (!items.length) {
      return '<li class="placeholder"><div class="ghost">' + (opts.emptyGlyph || '✧') + '</div>' + esc(opts.empty) + '</li>';
    }
    return items.map(function (t) { return taskItem(t, opts); }).join('');
  }

  function taskItem(t, opts) {
    var due = formatDue(t);
    var doneCls = t.status === 'done' ? ' done' : '';
    var tags = (t.tags || []).map(function (tag) {
      return '<span class="badge badge-tag">#' + esc(tag) + '</span>';
    }).join('');
    var actions = opts.compact ? '' :
      '<div class="task-actions">' +
      '<button class="icon-btn" data-action="edit" data-id="' + t.id + '" aria-label="Edit">✎</button>' +
      '<button class="icon-btn danger" data-action="delete" data-id="' + t.id + '" aria-label="Delete">✕</button>' +
      '</div>';
    return '<li class="task' + doneCls + '" data-id="' + t.id + '">' +
      '<button class="check" data-action="toggle" data-id="' + t.id + '" aria-label="Toggle complete">✓</button>' +
      '<div class="task-body">' +
      '<div class="task-title">' + esc(t.title) + '</div>' +
      '<div class="task-meta">' +
      (t.due_at ? '<span class="due ' + due.cls + '">◷ ' + esc(due.text) + '</span>' : '') +
      badge(t.priority) +
      statusBadge(t.status) +
      tags +
      '</div>' +
      '</div>' +
      actions +
      '</li>';
  }

  function filterTasks() {
    var q = state.search.toLowerCase();
    var list = tasks.filter(function (t) {
      if (state.status !== 'all' && t.status !== state.status) return false;
      if (state.priority !== 'all' && t.priority !== state.priority) return false;
      if (q) {
        var hay = (t.title + ' ' + (t.description || '') + ' ' + (t.tags || []).join(' ')).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
    var sort = state.sort;
    list.sort(function (a, b) {
      if (sort === 'priority') {
        var p = PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority];
        if (p !== 0) return p;
        return byDue(a, b);
      }
      if (sort === 'created') {
        return (b.created_at || '') < (a.created_at || '') ? -1 : 1;
      }
      return byDue(a, b);
    });
    return list;
  }

  // --- predictions ---
  var RISK_ORDER = { high: 0, medium: 1, low: 2 };
  var TYPE_LABEL = {
    overload: 'Workload overload',
    workload: 'Heavy week',
    conflict: 'Schedule conflict',
    delay: 'Delay risk',
    missed: 'Deadline pattern',
    slowdown: 'Pace change',
  };

  function riskBadge(level) {
    return '<span class="risk risk-' + esc(level) + '">' + esc(level) + '</span>';
  }

  function relativeTime(iso) {
    var d = parseLocal(iso);
    if (!d) return '';
    var s = Math.floor((new Date() - d) / 1000);
    if (s < 60) return 'just now';
    var m = Math.floor(s / 60);
    if (m < 60) return m + 'm ago';
    var h = Math.floor(m / 60);
    if (h < 24) return h + 'h ago';
    return Math.floor(h / 24) + 'd ago';
  }

  function feedbackRow(p) {
    var opts = [
      { key: 'accurate', label: '✓ Accurate' },
      { key: 'partial', label: '◐ Partial' },
      { key: 'inaccurate', label: '✕ Inaccurate' },
    ];
    var btns = opts.map(function (o) {
      var sel = p.feedback === o.key ? ' selected' : '';
      return '<button class="fb-btn' + sel + '" data-action="feedback" data-id="' + p.id + '" data-feedback="' + o.key + '">' + o.label + '</button>';
    }).join('');
    var note = p.feedback
      ? '<span class="fb-note">You rated this <b>' + esc(p.feedback) + '</b></span>'
      : '<span class="fb-note">Was this accurate?</span>';
    return '<div class="pred-feedback">' + note + '<div class="fb-actions">' + btns + '</div></div>';
  }

  function predictionItem(p, compact) {
    var typeLabel = TYPE_LABEL[p.type] || p.type;
    if (compact) {
      return '<li class="prediction compact">' +
        riskBadge(p.risk_level) +
        '<div class="pred-body"><div class="pred-title">' + esc(p.title) + '</div>' +
        '<div class="pred-sub">' + esc(typeLabel) + '</div></div></li>';
    }
    var prob = p.probability != null ? '<span class="pred-prob">~' + Math.round(p.probability * 100) + '%</span>' : '';
    var factors = (p.factors || []).map(function (f) {
      return '<span class="badge badge-tag">' + esc(f) + '</span>';
    }).join('');
    var rec = p.recommendation ? '<p class="pred-recommendation">→ ' + esc(p.recommendation) + '</p>' : '';
    var foot = [];
    if (p.horizon) foot.push('<span class="pred-meta">◷ ' + esc(p.horizon) + '</span>');
    if (p.related_task_ids && p.related_task_ids.length) foot.push('<span class="pred-meta">' + p.related_task_ids.length + ' related task(s)</span>');
    foot.push('<span class="pred-meta">created ' + relativeTime(p.created_at) + '</span>');
    return '<li class="prediction">' +
      '<div class="pred-head">' + riskBadge(p.risk_level) +
      '<span class="pred-type">' + esc(typeLabel) + '</span>' + prob + '</div>' +
      '<div class="pred-title">' + esc(p.title) + '</div>' +
      '<p class="pred-explanation">' + esc(p.explanation) + '</p>' +
      (factors ? '<div class="pred-factors">' + factors + '</div>' : '') +
      rec +
      '<div class="pred-foot">' + foot.join('') + '</div>' +
      feedbackRow(p) +
      '</li>';
  }

  function sortPredictions(list) {
    return list.slice().sort(function (a, b) {
      return (RISK_ORDER[a.risk_level] || 2) - (RISK_ORDER[b.risk_level] || 2);
    });
  }

  function renderRisk() {
    if (loadState === 'loading') {
      el.riskList.innerHTML = '<li class="placeholder"><div class="spinner"></div>Analyzing…</li>';
      return;
    }
    if (loadState === 'error') {
      el.riskList.innerHTML = '<li class="placeholder error">' + esc(errorMessage) + '<br><span class="retry" data-action="retry">Retry</span></li>';
      return;
    }
    var top = sortPredictions(predictions).slice(0, 3);
    if (!top.length) {
      el.riskList.innerHTML = '<li class="placeholder"><div class="ghost">✧</div>No risk signals right now.</li>';
      return;
    }
    el.riskList.innerHTML = top.map(function (p) { return predictionItem(p, true); }).join('');
  }

  function renderAnalytics() {
    var a = predictionAnalytics;
    if (!a) { el.predictionAnalytics.innerHTML = ''; return; }
    var avg = a.resolution && a.resolution.avg_hours != null ? a.resolution.avg_hours + 'h' : '—';
    var acc = a.feedback && a.feedback.accuracy != null ? Math.round(a.feedback.accuracy * 100) + '%' : '—';
    var byType = Object.keys(a.by_type || {}).map(function (k) {
      var t = a.by_type[k];
      return '<span class="badge badge-tag">' + esc(k) + ' · ' + t.total + '</span>';
    }).join('');
    el.predictionAnalytics.innerHTML =
      '<section class="card" style="margin-bottom:16px">' +
      '<div class="card-head"><h2>Prediction analytics</h2><span class="card-hint">from stored predictions</span></div>' +
      '<div class="stat-grid">' +
      '<article class="stat today"><div class="stat-value">' + a.total + '</div><div class="stat-label">total</div></article>' +
      '<article class="stat completed"><div class="stat-value">' + a.active + '</div><div class="stat-label">active</div></article>' +
      '<article class="stat upcoming"><div class="stat-value">' + a.resolved + '</div><div class="stat-label">resolved</div></article>' +
      '<article class="stat overdue"><div class="stat-value">' + acc + '</div><div class="stat-label">accuracy</div></article>' +
      '</div>' +
      (byType ? '<div class="pred-factors">' + byType + '</div>' : '') +
      '<p class="card-hint">Avg time to resolve: ' + avg + '. ' + esc(a.note) + '</p>' +
      '</section>';
  }

  function renderPredictionsView() {
    renderAnalytics();
    if (loadState === 'loading') {
      el.predictionsList.innerHTML = '<li class="placeholder"><div class="spinner"></div>Generating predictions…</li>';
      return;
    }
    if (loadState === 'error') {
      el.predictionsList.innerHTML = '<li class="placeholder error">' + esc(errorMessage) + '<br><span class="retry" data-action="retry">Retry</span></li>';
      return;
    }
    var list = sortPredictions(predictions);
    if (!list.length) {
      el.predictionsList.innerHTML = '<li class="placeholder"><div class="ghost">◈</div>No predictions right now.<br><span style="opacity:.85">Add tasks with due dates and time estimates so Foreli has real data to analyze.</span></li>';
      return;
    }
    el.predictionsList.innerHTML = list.map(function (p) { return predictionItem(p, false); }).join('');
  }

  function refreshPredictions() {
    var btn = el.refreshPredictionsBtn;
    btn.disabled = true;
    btn.textContent = '↻ Refreshing…';
    api('/api/predictions/refresh', { method: 'POST' })
      .then(function () {
        return Promise.all([api('/api/predictions'), api('/api/predictions/analytics')]);
      })
      .then(function (res) {
        predictions = res[0] || [];
        predictionAnalytics = res[1] || null;
        renderPredictionsView();
        renderRisk();
        showToast('Predictions refreshed');
      })
      .catch(function (err) { showToast(err.message, 'error'); })
      .then(function () { btn.disabled = false; btn.textContent = '↻ Refresh'; });
  }

  function submitFeedback(id, choice) {
    api('/api/predictions/' + id + '/feedback', {
      method: 'POST',
      body: JSON.stringify({ feedback: choice }),
    })
      .then(function () {
        return Promise.all([api('/api/predictions'), api('/api/predictions/analytics')]);
      })
      .then(function (res) {
        predictions = res[0] || [];
        predictionAnalytics = res[1] || null;
        renderPredictionsView();
        renderRisk();
        showToast('Feedback recorded');
      })
      .catch(function (err) { showToast(err.message, 'error'); });
  }

  // --- modal ---
  function openCreate() {
    editingId = null;
    el.modalTitle.textContent = 'New task';
    el.saveTaskBtn.textContent = 'Create task';
    el.taskForm.reset();
    el.taskStatus.value = 'todo';
    el.taskPriority.value = 'medium';
    el.modal.hidden = false;
    document.body.style.overflow = 'hidden';
    el.taskTitle.focus();
  }

  function openEdit(id) {
    var t = tasks.find(function (x) { return x.id === id; });
    if (!t) return;
    editingId = id;
    el.modalTitle.textContent = 'Edit task';
    el.saveTaskBtn.textContent = 'Save changes';
    el.taskTitle.value = t.title || '';
    el.taskDescription.value = t.description || '';
    el.taskStatus.value = t.status || 'todo';
    el.taskPriority.value = t.priority || 'medium';
    el.taskDue.value = t.due_at ? toInputValue(t.due_at) : '';
    el.taskEstimate.value = t.estimated_minutes != null ? t.estimated_minutes : '';
    el.taskTags.value = (t.tags || []).join(', ');
    el.modal.hidden = false;
    document.body.style.overflow = 'hidden';
    el.taskTitle.focus();
  }

  function closeModal() {
    el.modal.hidden = true;
    document.body.style.overflow = '';
  }

  function toInputValue(iso) {
    var d = parseLocal(iso);
    if (!d) return '';
    function p(n) { return String(n).padStart(2, '0'); }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function setSubmitBusy(busy) {
    el.saveTaskBtn.disabled = busy;
    el.saveTaskBtn.textContent = busy ? 'Saving…' : (editingId ? 'Save changes' : 'Create task');
  }

  function handleSubmit(e) {
    e.preventDefault();
    var title = el.taskTitle.value.trim();
    if (!title) { showToast('Please enter a title.', 'error'); el.taskTitle.focus(); return; }
    var payload = {
      title: title,
      description: el.taskDescription.value.trim() || null,
      status: el.taskStatus.value,
      priority: el.taskPriority.value,
      due_at: el.taskDue.value ? el.taskDue.value + ':00' : null,
      estimated_minutes: el.taskEstimate.value ? parseInt(el.taskEstimate.value, 10) : null,
      tags: el.taskTags.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean),
    };
    setSubmitBusy(true);
    var req = editingId
      ? api('/api/tasks/' + editingId, { method: 'PATCH', body: JSON.stringify(payload) })
      : api('/api/tasks', { method: 'POST', body: JSON.stringify(payload) });
    req.then(function () {
      showToast(editingId ? 'Task updated' : 'Task created');
      closeModal();
      return refresh();
    }).catch(function (err) {
      showToast(err.message, 'error');
    }).then(function () {
      setSubmitBusy(false);
    });
  }

  // --- actions ---
  function toggleTask(id) {
    api('/api/tasks/' + id + '/toggle', { method: 'POST' })
      .then(function () { return refresh(); })
      .catch(function (err) { showToast(err.message, 'error'); });
  }

  function deleteTask(id, btn) {
    if (btn.dataset.arm !== '1') {
      btn.dataset.arm = '1';
      btn.textContent = '?';
      btn.classList.add('danger-armed');
      btn.title = 'Click again to confirm delete';
      setTimeout(function () { resetDelete(btn); }, 3000);
      return;
    }
    api('/api/tasks/' + id, { method: 'DELETE' })
      .then(function () { showToast('Task deleted'); return refresh(); })
      .catch(function (err) { showToast(err.message, 'error'); });
  }

  function resetDelete(btn) {
    btn.dataset.arm = '0';
    btn.textContent = '✕';
    btn.classList.remove('danger-armed');
    btn.title = '';
  }

  function switchView(view) {
    state.view = view;
    document.querySelectorAll('.nav-item').forEach(function (n) {
      n.classList.toggle('active', n.dataset.view === view);
    });
    document.querySelectorAll('.view').forEach(function (v) {
      v.classList.toggle('active', v.id === 'view-' + view);
    });
    closeSidebar();
    render();
  }

  function openSidebar() { el.sidebar.classList.add('open'); el.scrim.classList.add('show'); }
  function closeSidebar() { el.sidebar.classList.remove('open'); el.scrim.classList.remove('show'); }

  // --- events ---
  function bindEvents() {
    document.querySelectorAll('[data-view]').forEach(function (n) {
      n.addEventListener('click', function () { switchView(n.dataset.view); });
    });
    el.newTaskBtn.addEventListener('click', openCreate);
    el.logoutBtn.addEventListener('click', function () {
      api('/api/auth/logout', { method: 'POST' })
        .catch(function () {})
        .then(function () { window.location.href = 'index.html'; });
    });
    el.refreshPredictionsBtn.addEventListener('click', refreshPredictions);
    el.menuToggle.addEventListener('click', openSidebar);
    el.scrim.addEventListener('click', closeSidebar);
    el.taskForm.addEventListener('submit', handleSubmit);

    el.modal.querySelectorAll('[data-close]').forEach(function (b) {
      b.addEventListener('click', closeModal);
    });
    el.modal.addEventListener('click', function (e) {
      if (e.target === el.modal) closeModal();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !el.modal.hidden) closeModal();
    });

    // Task list action delegation (overview + tasks lists).
    [el.todayList, el.upcomingList, el.taskList, el.riskList, el.predictionsList].forEach(function (list) {
      list.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-action]');
        if (!btn) return;
        var id = btn.dataset.id ? parseInt(btn.dataset.id, 10) : null;
        var action = btn.dataset.action;
        if (action === 'toggle' && id) toggleTask(id);
        else if (action === 'edit' && id) openEdit(id);
        else if (action === 'delete' && id) deleteTask(id, btn);
        else if (action === 'feedback' && id) submitFeedback(id, btn.dataset.feedback);
        else if (action === 'retry') refresh();
      });
    });

    el.searchInput.addEventListener('input', function () {
      state.search = el.searchInput.value;
      renderTasks();
    });
    el.statusFilter.addEventListener('change', function () { state.status = el.statusFilter.value; renderTasks(); });
    el.priorityFilter.addEventListener('change', function () { state.priority = el.priorityFilter.value; renderTasks(); });
    el.sortSelect.addEventListener('change', function () { state.sort = el.sortSelect.value; renderTasks(); });
  }

  // --- init ---
  bindEvents();
  checkAuth();
  checkHealth();
  refresh();
  // Re-check health periodically.
  setInterval(checkHealth, 15000);
})();
