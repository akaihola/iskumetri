const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function app() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: id === 'smooth' ? '1' : 'ms', checked: id === 'auto', disabled: false,
      listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; },
      checkValidity() { return true; }, setAttribute() {}, getContext() { return {}; },
    });
    return elements.get(id);
  }
  const context = vm.createContext({
    document: { getElementById: element, querySelector: () => ({value: 'ms'}), querySelectorAll: () => [] },
    window: { addEventListener() {}, location: { origin: 'http://localhost' } },
    ResizeObserver: class { observe() {} }, matchMedia: () => ({addEventListener() {}}),
    requestAnimationFrame() {}, setTimeout() {}, clearTimeout() {},
  });
  vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), context);
  return { element, run: code => vm.runInContext(code, context), context };
}

test('native sensitivity input switches auto off and enables manual gap', () => {
  const a = app();
  assert.equal(a.element('mingap').disabled, true);
  assert.equal(a.element('sensitivity').disabled, false);
  for (const value of ['1.1', '0.9', '2']) {
    a.element('auto').checked = true;
    a.element('auto').listeners.change();
    a.element('sensitivity').value = value;
    a.element('sensitivity').listeners.input();
    assert.equal(a.element('auto').checked, false);
    assert.equal(a.element('mingap').disabled, false);
  }
  a.element('auto').checked = true;
  a.element('auto').listeners.change();
  assert.equal(a.element('mingap').disabled, true);
});

test('centered intervals use elapsed time and actual edge counts', () => {
  const a = app();
  a.run('data = {onsets: [0,1,3,6,10], intervals: [1,2,3,4]}');
  assert.equal(a.run('windowed(2,2)'), 2500);
  assert.equal(a.run('windowed(2,3)'), 3000);
  assert.equal(a.run('windowed(0,2)'), 1000);
  assert.equal(a.run('windowed(4,2)'), 4000);
  assert.equal(a.run('windowed(2,64)'), 2500);
  assert.equal(a.run('windowed(2,1)'), 3000);
  a.run('mode="bpm"');
  assert.equal(a.run('windowed(2,2)'), 24);
  assert.equal(a.run('windowed(2,3)'), 20);
  a.run('data = {onsets: [0], intervals: []}');
  assert.ok(Number.isNaN(a.run('windowed(0,2)')));
});

test('player waits for readiness, retains playback, and follows paused seeks', () => {
  const a = app();
  const queued = [], seeks = [];
  let events, time = 0;
  const player = {
    getIframe: () => ({}), cueVideoById: id => queued.push(id),
    getCurrentTime: () => time, seekTo: (t, allow) => seeks.push([t, allow]),
  };
  a.context.YT = { Player: function(id, opts) { events = opts.events; return player; } };
  a.context.window.YT = a.context.YT;
  a.run('draw = () => {}; data = {video_id: "first", title:"First",duration:40}; loadPlayer()');
  assert.deepEqual(queued, []);
  a.run('data = {video_id:"second", title:"Second", duration:40}; loadPlayer()');
  events.onReady();
  assert.deepEqual(queued, ['second']);
  a.run('loadPlayer()');
  assert.equal(queued.length, 1);
  a.run('data = {video_id:"third", title:"Third", duration:40}; loadPlayer()');
  assert.deepEqual(queued, ['second', 'third']);
  time = 12.5;
  a.run('tick(100)');
  assert.equal(a.run('playerTime'), 12.5);
  time = 18;
  a.run('tick(200)');
  assert.equal(a.run('playerTime'), 18);
  a.run('plotBox = () => ({x:0,w:100}); view = {t0:10,t1:20}; drag = {moved:false}');
  a.element('chart').listeners.pointerup({offsetX:50});
  assert.deepEqual(seeks, [[15, true]]);
  events.onError();
  assert.match(a.element('player-status').textContent, /unavailable/);
});

test('API load errors leave a visible playback status', () => {
  const a = app();
  let script;
  a.context.document.createElement = () => ({remove() {}});
  a.context.document.head = {append: el => {script = el;}};
  a.run('loadPlayer()');
  assert.equal(script.src, 'https://www.youtube.com/iframe_api');
  script.onerror();
  assert.match(a.element('player-status').textContent, /analysis chart is still usable/);
});


test('re-enabling auto restores an invalid manual sensitivity', () => {
  const a = app();
  const sensitivity = a.element('sensitivity');
  sensitivity.value = '';
  sensitivity.defaultValue = '1';
  sensitivity.checkValidity = () => false;
  sensitivity.listeners.input();
  a.element('auto').checked = true;
  a.element('auto').listeners.change();
  assert.equal(sensitivity.value, '1');
  assert.equal(a.element('auto').checked, true);
});

test('a failed YouTube script can be retried on the next analysis', () => {
  const a = app();
  const scripts = [];
  a.context.document.createElement = () => ({remove() {}});
  a.context.document.head = {append: script => scripts.push(script)};
  a.run('loadPlayer()');
  scripts[0].onerror();
  a.run('loadPlayer()');
  assert.equal(scripts.length, 2);
});
