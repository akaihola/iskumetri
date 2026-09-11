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
      setAttribute() {}, getContext() { return {}; },
    });
    return elements.get(id);
  }
  const context = vm.createContext({
    document: { getElementById: element, querySelector: () => ({value: 'ms'}), querySelectorAll: () => [] },
    window: { location: { origin: 'http://localhost' } },
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
