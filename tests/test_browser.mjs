import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {createServer} from 'node:http';
import {execFileSync} from 'node:child_process';
import {chromium, firefox} from 'playwright';

function parity(got, expected) {
  for (const key of ['raw_count', 'inferred', 'params']) assert.deepEqual(got[key], expected[key], key);
  assert.equal(got.segment.detected, expected.segment.detected);
  for (const key of ['onsets', 'intervals', 'velocities']) {
    assert.equal(got[key].length, expected[key].length, key);
    got[key].forEach((value, i) => assert.ok(Math.abs(value - expected[key][i]) <= (key === 'velocities' ? .001 : 128 / 22050), `${key}[${i}]`));
  }
  for (const key of ['start', 'end']) assert.ok(Math.abs(got.segment[key] - expected.segment[key]) <= 128 / 22050);
  assert.ok(Math.abs(got.duration - expected.duration) < .001);
}

for (const [name, engine] of Object.entries({chromium, firefox})) {
  test(`${name}: static upload, native parity, playback and failures`, {timeout: 300000}, async () => {
    const fixtures = await mkdtemp(join(tmpdir(), 'iskumetri-browser-'));
    let browser, server, failRuntime = false;
    try {
      execFileSync('python3', ['tools/build_static.py']);
      execFileSync('uv', ['run', 'python', 'tests/browser_fixtures.py', fixtures], {env: {...process.env, PYTHONPATH: '.'}});
      const expected = JSON.parse(await readFile(join(fixtures, 'expected.json')));
      server = createServer(async (req, res) => {
        try {
          let path = new URL(req.url, 'http://localhost').pathname;
          let root = resolve('dist');
          if (path === '/parity-worker.js') { root = resolve('tests'); }
          else if (path.startsWith('/fixtures/')) { root = fixtures; path = path.slice('/fixtures'.length); }
          else if (path.startsWith('/subpath/')) path = path.slice('/subpath'.length);
          if (path === '/') path = '/index.html';
          const file = resolve(root, '.' + path);
          if (!file.startsWith(root + '/')) throw Error('path');
          res.setHeader('Content-Type', path.endsWith('.js') ? 'text/javascript' : path.endsWith('.html') ? 'text/html' : path.endsWith('.css') ? 'text/css' : 'application/octet-stream');
          let body = await readFile(file);
          if (failRuntime && path.endsWith('/analysis-worker.js')) {
            body = body.toString().replace('https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.mjs', './unavailable-runtime.mjs');
          }
          res.end(body);
        } catch { res.writeHead(404).end(); }
      });
      await new Promise(r => server.listen(0, '127.0.0.1', r));
      const origin = `http://127.0.0.1:${server.address().port}`;
      browser = await engine.launch({executablePath: process.env[`${name.toUpperCase()}_EXECUTABLE_PATH`] || undefined});
      console.log(`${name} ${browser.version()}`);
      const page = await browser.newPage();
      const errors = [], forbidden = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => {
        if (request.method() === 'POST' || /youtube|\/api\//.test(request.url())) forbidden.push(request.url());
      });
      await page.goto(origin + '/subpath/');
      // Stage-level parity uses identical float32 bytes, not different codec decoders.
      for (const [fixture, results] of Object.entries(expected.pcm)) {
        const got = await page.evaluate(async fixture => {
          const samples = new Float32Array(await (await fetch(`/fixtures/${fixture}.f32`)).arrayBuffer());
          window.parityWorker ??= new Worker('/parity-worker.js', {type:'module'});
          window.productionWorker ??= new Worker('analysis-worker.js', {type:'module'});
          const request = (worker, params) => new Promise((resolve, reject) => {
            worker.onerror = error => reject(Error(error.message));
            worker.onmessage = ({data}) => data.error ? reject(Error(data.error)) : resolve(data.result);
            const copy = samples.slice();
            worker.postMessage({id:fixture, samples:copy, params}, [copy.buffer]);
          });
          const flux = await request(parityWorker);
          const results = [];
          for (const params of [{}, {sensitivity:1.0, min_interval:.03}]) {
            results.push(await request(productionWorker, params));
          }
          return {flux, results};
        }, fixture);
        got.results.forEach((result, i) => parity(result, results[i]));
        const bytes = await readFile(join(fixtures, `${fixture}.flux`));
        const flux = new Float32Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
        assert.equal(got.flux.length, flux.length);
        got.flux.forEach((value, i) => assert.ok(Math.abs(value - flux[i]) < 1e-5, `${fixture} flux ${i}`));
      }
      await page.evaluate(() => { parityWorker.terminate(); productionWorker.terminate(); });
      // The actual production worker receives decoded audio through the UI.
      await page.locator('#auto').uncheck();
      const upload = async filename => {
        await page.locator('#audio-file').setInputFiles(join(fixtures, filename));
        await page.locator('#go').click();
        await page.waitForFunction(() => !document.getElementById('go').disabled, null, {timeout:120000});
        assert.equal(await page.locator('#status').textContent(), '');
        return await page.evaluate(() => data);
      };
      for (const [filename, result] of Object.entries(expected.files)) {
        const got = await upload(filename);
        // Decoders can move noise peaks across thresholds. Check known attacks
        // separately from inferred/noise detections; identical-PCM parity is above.
        const match = result => expected.clicks.map(time => {
          const closest = result.onsets.reduce((a, b) => Math.abs(a - time) < Math.abs(b - time) ? a : b);
          assert.ok(Math.abs(closest - time) < .025, `${filename} missing click ${time}`);
          return closest;
        });
        const found = match(got), native = match(result);
        const offsets = found.map((value, i) => value - native[i]);
        offsets.forEach(value => assert.ok(Math.abs(value) <= 128 / 22050));
        found.slice(1).forEach((value, i) => assert.ok(Math.abs((value - found[i]) - (native[i + 1] - native[i])) <= 128 / 22050));
        console.log(`${name} ${filename}: ${got.onsets.length}/${result.onsets.length} total detections; known click offsets ${Math.min(...offsets).toFixed(4)}..${Math.max(...offsets).toFixed(4)} s`);
      }
      for (const filename of ['single.wav', 'silent.wav']) {
        const result = await upload(filename);
        assert.equal(result.onsets.length, filename === 'single.wav' ? 1 : 0);
        assert.match(await page.locator('#summary').textContent(), /too few/);
      }
      await upload('mono44.wav');
      await page.evaluate(() => { document.getElementById('audio-player').currentTime = 2; });
      await page.waitForFunction(() => playerTime === 2);
      await page.locator('#chart').click({position:{x:160,y:100}});
      assert.notEqual(await page.locator('#audio-player').evaluate(el => el.currentTime), 2);
      await page.locator('#auto').check();
      await page.locator('#go').click();
      await page.waitForFunction(() => !document.getElementById('go').disabled);
      assert.equal(await page.locator('#status').textContent(), '');
      await page.locator('#audio-file').setInputFiles({name:'broken.wav',mimeType:'audio/wav',buffer:Buffer.from('invalid')});
      await page.locator('#go').click();
      await page.waitForFunction(() => !document.getElementById('go').disabled);
      assert.match(await page.locator('#status').textContent(), /Cannot decode/);
      await upload('mono44.wav');
      await page.setViewportSize({width:390,height:844});
      await page.emulateMedia({colorScheme:'dark'});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.deepEqual(errors, []);
      assert.deepEqual(forbidden, []);
      const limits = await page.evaluate(async () => {
        const messages = [];
        for (const blob of [new Blob([]), {size:128 * 1024 * 1024 + 1}]) {
          try { await audioAnalysis.analyzeAudio(blob, {}); }
          catch (error) { messages.push(error.message); }
        }
        return messages;
      });
      assert.match(limits[0], /empty/);
      assert.match(limits[1], /128 MiB/);
      if (process.env.ISKUMETRI_LONG_TEST) {
        const measured = await page.evaluate(async () => {
          function wav(seconds) {
            const samples = seconds * 8000, buffer = new ArrayBuffer(44 + samples * 2);
            const view = new DataView(buffer);
            for (const [offset, text] of [[0,'RIFF'],[8,'WAVE'],[12,'fmt '],[36,'data']])
              for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
            for (const [offset,value] of [[4,36+samples*2],[16,16],[24,8000],[28,16000],[40,samples*2]]) view.setUint32(offset,value,true);
            for (const [offset,value] of [[20,1],[22,1],[32,2],[34,16]]) view.setUint16(offset,value,true);
            return new Blob([buffer], {type:'audio/wav'});
          }
          let ticks = 0;
          const timer = setInterval(() => ticks++, 50), start = performance.now();
          try {
            const result = await audioAnalysis.analyzeAudio(wav(1199), {});
            let overLimit;
            try { await audioAnalysis.analyzeAudio(wav(1201), {}); }
            catch (error) { overLimit = error.message; }
            return {duration:result.duration, count:result.onsets.length, ms:performance.now()-start,
                    ticks, mainThreadHeap:performance.memory?.usedJSHeapSize, overLimit};
          } finally { clearInterval(timer); audioAnalysis.reset(); }
        });
        assert.equal(measured.duration, 1199);
        assert.equal(measured.count, 0);
        assert.ok(measured.ticks > 2);
        assert.match(measured.overLimit, /20 minutes/);
        console.log(name, 'long recording', measured);
      }
      // A cold worker's runtime failure must be visible and retryable.
      await page.evaluate(() => audioAnalysis.dispose());
      failRuntime = true;
      await page.locator('#go').click();
      await page.waitForFunction(() => !document.getElementById('go').disabled);
      assert.match(await page.locator('#status').textContent(), /failed|could not load/i);
      failRuntime = false;
      await upload('mono44.wav');
    } catch (error) { console.error(error); throw error; } finally {
      await browser?.close();
      if (server) await new Promise(r => server.close(r));
      await rm(fixtures, {recursive:true,force:true});
    }
  });
}
