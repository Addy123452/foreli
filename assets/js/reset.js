/* Forgot-password and reset-password flows. */
(function () {
  'use strict';

  var API_BASE = window.FORELI_API_BASE ||
    (window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '');

  var form = document.querySelector('form[data-auth-mode]');
  if (!form) return;

  if (window.location.hostname.indexOf('github.io') !== -1) {
    var card = document.querySelector('.auth-card');
    if (card) {
      var notice = document.createElement('div');
      notice.className = 'auth-notice';
      notice.textContent = 'Static preview — the Foreli backend is not hosted here yet. See the README for deployment.';
      card.insertBefore(notice, form);
    }
  }

  var mode = form.getAttribute('data-auth-mode'); // 'forgot' | 'reset'
  var errorBox = document.getElementById('authError');
  var resultBox = document.getElementById('authResult');
  var submitBtn = form.querySelector('button[type="submit"]');

  function showError(message) { errorBox.textContent = message; errorBox.hidden = false; }
  function clearError() { errorBox.textContent = ''; errorBox.hidden = true; }
  function showResult(html) { resultBox.innerHTML = html; resultBox.hidden = false; }

  form.querySelectorAll('[data-toggle-password]').forEach(function (toggle) {
    toggle.addEventListener('click', function () {
      var input = toggle.closest('.password-wrap').querySelector('input');
      var showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      toggle.textContent = showing ? 'Show' : 'Hide';
    });
  });

  function extractError(data) {
    var d = data && data.detail;
    if (!d) return 'Request failed. Please try again.';
    if (typeof d === 'string') return d;
    if (Array.isArray(d) && d.length && d[0].msg) return d[0].msg;
    return 'Request failed. Please try again.';
  }

  function post(path, body) {
    return fetch(API_BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) throw new Error(extractError(data));
        return data;
      });
    });
  }

  if (mode === 'reset') {
    var hidden = document.getElementById('reset-token');
    var queryToken = new URLSearchParams(window.location.search).get('token');
    if (hidden && queryToken) hidden.value = queryToken;
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    clearError();

    if (mode === 'forgot') {
      var email = (form.querySelector('input[name="email"]').value || '').trim();
      if (!email || email.indexOf('@') < 1 || email.indexOf('.') < 0) {
        showError('Enter a valid email address.');
        return;
      }
      submitBtn.disabled = true;
      submitBtn.textContent = 'Sending…';
      post('/api/auth/forgot', { email: email })
        .then(function (data) {
          if (data.reset_url) {
            showResult('Reset link ready: <a href="' + data.reset_url + '">open reset page</a>' +
              '<br><small>This link is single-use and expires in 30 minutes. It is also logged in the server console.</small>');
          } else {
            showResult('If an account exists for that email, a reset link has been generated.' +
              '<br><small>Email delivery is not configured, so check the server console for the link.</small>');
          }
          submitBtn.disabled = false;
          submitBtn.textContent = 'Send reset link';
        })
        .catch(function (err) {
          showError(err.message);
          submitBtn.disabled = false;
          submitBtn.textContent = 'Send reset link';
        });
      return;
    }

    // Reset mode.
    var tokenField = form.querySelector('input[name="token"]');
    var token = (tokenField && tokenField.value ? tokenField.value :
      (new URLSearchParams(window.location.search).get('token') || '')).trim();
    var password = form.querySelector('input[name="password"]').value || '';
    var confirmInput = form.querySelector('input[name="confirm"]');
    if (!token) { showError('Missing reset token. Open the reset link again.'); return; }
    if (password.length < 8) { showError('Password must be at least 8 characters.'); return; }
    if (confirmInput && password !== (confirmInput.value || '')) {
      showError('Passwords do not match.');
      return;
    }
    submitBtn.disabled = true;
    submitBtn.textContent = 'Updating…';
    post('/api/auth/reset', { token: token, password: password })
      .then(function () {
        submitBtn.textContent = 'Password updated ✓';
        showResult('Password updated. Redirecting to sign in…');
        setTimeout(function () { window.location.href = 'login.html'; }, 900);
      })
      .catch(function (err) {
        showError(err.message);
        submitBtn.disabled = false;
        submitBtn.textContent = 'Set new password';
      });
  });
})();
