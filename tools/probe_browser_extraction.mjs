// Network smoke probe only. Does not proxy requests or relax browser security.
import {createServer} from 'node:http';
import {chromium, firefox} from 'playwright';

const workerSource = `
import {loadPyodide} from 'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.mjs';
try {
  const py = await loadPyodide({stdout: text => self.postMessage({log:text}), stderr: text => self.postMessage({log:text})});
  await py.loadPackage(['micropip', 'ssl']);
  await py.runPythonAsync(\`
import micropip
await micropip.install(['yt-dlp==2026.8.19', 'pyodide-http==0.2.2'])
import pyodide_http
pyodide_http.patch_all()
import yt_dlp, json
class Log:
    def debug(self, message): print(message)
    def warning(self, message): print(message)
    def error(self, message): print(message)
for label, extra in [
    ('default', {}),
    ('googleapis-android-vr', {'extractor_args': {'youtube': {
        'innertube_host': ['youtubei.googleapis.com'], 'player_client': ['android_vr'],
        'player_skip': ['webpage', 'configs', 'initial_data']}}}),
]:
    print('ATTEMPT', label)
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'logger': Log(), 'noplaylist': True,
                              'socket_timeout': 10, 'retries': 0, 'extractor_retries': 0,
                              'format': 'bestaudio[abr<=100][asr>=44000]/worstaudio[asr>=44000]/bestaudio',
                              **extra}) as ydl:
            info = ydl.extract_info('https://www.youtube.com/watch?v=NvIDlwzHRGQ', download=False)
            print('METADATA', info.get('id'), info.get('duration'), info.get('ext'))
    except Exception as error:
        print(type(error).__name__, str(error))
\`);
  self.postMessage({finished:true});
} catch (error) { self.postMessage({runtimeError:error.message}); }
`;
const server = createServer((req, res) => {
  res.setHeader('Content-Type', req.url === '/worker.js' ? 'text/javascript' : 'text/html');
  res.end(req.url === '/worker.js' ? workerSource : '<!doctype html><title>Static-origin extraction probe</title>');
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
try {
  for (const [name, engine] of Object.entries({chromium, firefox})) {
    let browser;
    try {
      browser = await engine.launch({executablePath:process.env[`${name.toUpperCase()}_EXECUTABLE_PATH`] || undefined});
      const page = await browser.newPage();
      page.on('console', message => console.log(name, message.type(), message.text()));
      page.on('requestfailed', request => console.log(name, 'requestfailed', request.url(), request.failure()));
      await page.goto(`http://127.0.0.1:${server.address().port}`);
      console.log(name, browser.version(), await page.evaluate(() => location.origin));
      console.log(await page.evaluate(async () => {
        const out = [];
        for (const url of ['https://www.youtube.com/watch?v=NvIDlwzHRGQ',
                           'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=NvIDlwzHRGQ&format=json',
                           'https://www.youtube.com/youtubei/v1/player',
                           'https://youtubei.googleapis.com/youtubei/v1/player']) {
          try {
            const options = url.includes('/youtubei/') ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({videoId:'NvIDlwzHRGQ',context:{client:{clientName:'WEB',clientVersion:'2.20260910.01.00'}}})} : {};
            const response = await fetch(url, {...options,signal:AbortSignal.timeout(15000)});
            out.push({url, status:response.status, type:response.type, bytes:(await response.text()).length});
          } catch(error) { out.push({url,error:error.message}); }
        }
        try {
          const response = await fetch('https://www.youtube.com/watch?v=NvIDlwzHRGQ', {mode:'no-cors',signal:AbortSignal.timeout(15000)});
          out.push({mode:'no-cors',status:response.status,type:response.type,bytes:(await response.text()).length});
        } catch(error) { out.push({mode:'no-cors',error:error.message}); }
        return out;
      }));
      console.log(name, await page.evaluate(() => new Promise(resolve => {
        const worker = new Worker('/worker.js', {type:'module'});
        const finish = result => { clearTimeout(timer); worker.terminate(); resolve(result); };
        const timer = setTimeout(() => finish({timeout:true}), 120000);
        worker.onmessage = ({data}) => { if (data.log) console.log(data.log); else finish(data); };
        worker.onerror = error => finish({workerError:error.message});
      })));
    } finally { await browser?.close(); }
  }
} finally { await new Promise(r => server.close(r)); }
