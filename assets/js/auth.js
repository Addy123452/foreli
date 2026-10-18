/* Shared login / registration form logic. */
(function () {
  'use strict';

  var API_BASE = window.FORELI_API_BASE ||
    (window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '');

  var form = document.querySelector('form[data-auth-mode]');
  if (!form) return;

  var mode = form.getAttribute('data-auth-mode'); // 'login' | 'register'
  var errorBox = document.getElementById('authError');
  var submitBtn = form.querySelector('button[type="submit"]');
  var emailInput = form.querySelector('input[name="email"]');
  var passwordInput = form.querySelector('input[name="password"]');
  var confirmInput = form.querySelector('input[name="confirm"]');

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function clearError() {
    errorBox.textContent = '';
    errorBox.hidden = true;
  }

  // Show / hide password controls.
  form.querySelectorAll('[data-toggle-password]').forEach(function (toggle) {
    toggle.addEventListener('click', function () {
      var wrap = toggle.closest('.password-wrap');
      var input = wrap ? wrap.querySelector('input') : null;
      if (!input) return;
      var showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      toggle.textContent = showing ? 'Show' : 'Hide';
      toggle.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
    });
  });

  function setBusy(busy) {
    submitBtn.disabled = busy;
    if (busy) {
      submitBtn.textContent = 'Please wait…';
    } else {
      submitBtn.textContent = mode === 'register' ? 'Create account' : 'Sign in';
    }
  }

  function extractError(data) {
    var detail = data && data.detail;
    if (!detail) return 'Request failed. Please try again.';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length && detail[0].msg) return detail[0].msg;
    return 'Request failed. Please try again.';
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    clearError();

    var email = (emailInput.value || '').trim();
    var password = passwordInput.value || '';

    if (!email || email.indexOf('@') < 1 || email.indexOf('.') < 0) {
      showError('Enter a valid email address.');
      emailInput.focus();
      return;
    }
    if (password.length < 8) {
      showError('Password must be at least 8 characters.');
      passwordInput.focus();
      return;
    }
    if (mode === 'register' && password !== (confirmInput.value || '')) {
      showError('Passwords do not match.');
      confirmInput.focus();
      return;
    }

    setBusy(true);
    fetch(API_BASE + '/api/auth/' + mode, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email: email, password: password }),
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) throw new Error(extractError(data));
          return data;
        });
      })
      .then(function () {
        submitBtn.textContent = 'Success…';
        window.location.href = 'dashboard.html';
      })
      .catch(function (err) {
        showError(err.message);
        setBusy(false);
      });
  });
})();
