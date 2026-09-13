"use strict";

let tokenPrompt = null;
const tok = () => sessionStorage.getItem('adminToken') || '';

async function api(path, options = {}) {
  const url = new URL(path, window.location.origin);
  if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/')) {
    throw new Error('Invalid API URL');
  }
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set('Content-Type', 'application/json');
  if (tok()) headers.set('X-Admin-Token', tok());
  const request = () => fetch(url, {...options, headers, cache: 'no-store', redirect: 'error'});
  let response = await request();
  if (response.status === 401) {
    if (tok() && headers.get('X-Admin-Token') !== tok()) {
      headers.set('X-Admin-Token', tok());
    } else {
      if (!tokenPrompt) {
        tokenPrompt = Promise.resolve().then(() => {
          const token = prompt(t('prompt_token'));
          if (!token) throw new Error(t('no_token'));
          sessionStorage.setItem('adminToken', token.trim());
          return token.trim();
        }).finally(() => { tokenPrompt = null; });
      }
      headers.set('X-Admin-Token', await tokenPrompt);
    }
    response = await request();
  }
  const body = await response.json().catch(() => ({}));
  const healthWarning = url.pathname === '/api/health' && response.status === 503 && Array.isArray(body.problems);
  if (!response.ok && !healthWarning) {
    if (response.status === 401) sessionStorage.removeItem('adminToken');
    throw new Error(body.detail || body.message || ('HTTP ' + response.status));
  }
  return body;
}
