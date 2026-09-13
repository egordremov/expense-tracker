const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'static/i18n.js'), 'utf8');
{
  const context = {
    localStorage: {getItem: () => null},
    navigator: {language: 'ru-RU'},
    document: {documentElement: {}, cookie: ''},
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  assert.equal(context.document.documentElement.lang, 'en');
}
{
  const context = {
    localStorage: {getItem: () => 'en'},
    navigator: {language: 'en-GB'},
    document: {documentElement: {}, cookie: 'lang=ru'},
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  assert.equal(context.document.documentElement.lang, 'ru');
}
for (const lang of ['ru', 'en', 'lt']) {
  const context = {
    localStorage: {getItem: () => lang},
    navigator: {language: lang},
    document: {documentElement: {}, cookie: ''},
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  const dictionaries = vm.runInContext('I18N', context);
  for (const key of Object.keys(dictionaries.ru)) {
    assert.ok(key in dictionaries[lang], `${lang}: missing ${key}`);
  }
  assert.equal(context.document.documentElement.lang, lang);
  assert.equal(vm.runInContext('catKey(catName("напитки"))', context), 'напитки');
  assert.equal(vm.runInContext('healthProblems({problems_i18n:[{code:"unparsed",params:{n:2}}]})[0].includes("{n}")', context), false);
  assert.ok(vm.runInContext('syncMessage({status:"success",details:{days:30,mails:2,new_mails:2,new_expenses:3}}).length', context) > 0);
  for (const file of ['static/index.html', 'static/settings.html']) {
    const html = fs.readFileSync(path.join(root, file), 'utf8');
    for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
      new vm.Script(match[1], {filename: file});
    }
    for (const match of html.matchAll(/data-i18n(?:-ph|-title)?="([^"]+)"/g)) {
      assert.ok(match[1] in dictionaries[lang], `${file}: missing ${lang}.${match[1]}`);
    }
  }
}
console.log('UI syntax, translation keys and localization helpers: OK (ru, en, lt)');

async function checkApiClient() {
  const apiSource = fs.readFileSync(path.join(root, 'static/api.js'), 'utf8');
  const token = 'test-only-admin-token-at-least-32-characters';
  const storage = new Map();
  const calls = [];
  let prompts = 0;
  let response = {status: 200, body: {ok: true}};
  const context = {
    URL, Headers,
    window: {location: {origin: 'http://localhost:8080'}},
    sessionStorage: {getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k)},
    prompt: () => { prompts++; return token; },
    t: key => key,
    fetch: async (url, options) => {
      calls.push({url, options});
      if (options.headers.get('X-Admin-Token') !== token) return {status: 401, ok: false, json: async () => ({detail: 'Unauthorized'})};
      return {status: response.status, ok: response.status === 200, json: async () => response.body};
    },
  };
  vm.createContext(context);
  vm.runInContext(apiSource, context);
  await Promise.all([context.api('/api/stats'), context.api('/api/stores')]);
  assert.equal(prompts, 1);
  assert.equal(storage.get('adminToken'), token);
  assert.equal(calls.at(-1).options.redirect, 'error');
  assert.equal(calls.at(-1).options.cache, 'no-store');
  const previousCalls = calls.length;
  await assert.rejects(context.api('http://untrusted.invalid/api/stats'), /Invalid API URL/);
  assert.equal(calls.length, previousCalls);
  response = {status: 503, body: {detail: 'Storage unavailable'}};
  await assert.rejects(context.api('/api/settings'), /Storage unavailable/);
  response = {status: 503, body: {ok: false, problems: ['No mail configured']}};
  assert.equal((await context.api('/api/health')).ok, false);
  response = {status: 401, body: {detail: 'Unauthorized'}};
  await assert.rejects(context.api('/api/stats'), /Unauthorized/);
  assert.equal(storage.has('adminToken'), false);
  console.log('API client: token prompt, concurrent requests, rotation failures and origin guard: OK');
}
checkApiClient().catch(error => {console.error(error); process.exitCode = 1;});
