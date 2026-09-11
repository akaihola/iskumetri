// Pin the Python and NumPy ABI together. The detector is our canonical source.
const runtimeURL = 'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.mjs';
let ready;
async function initialize() {
  const {loadPyodide} = await import(runtimeURL);
  const pyodide = await loadPyodide();
  await pyodide.loadPackage('numpy');
  const source = await fetch(new URL('onsets.py', import.meta.url));
  if (!source.ok) throw new Error(`Cannot load the detector: HTTP ${source.status}`);
  pyodide.FS.writeFile('onsets.py', await source.text());
  pyodide.runPython('import json, numpy as np\nfrom onsets import analyze_pcm');
  return pyodide;
}

// Initialization is asynchronous; queue messages so Python globals never overlap.
let queue = Promise.resolve();
self.onmessage = ({data: {id, samples, params}}) => {
  queue = queue.then(async () => {
    let pyodide;
    try {
      ready ??= initialize().catch(error => { ready = null; throw error; });
      pyodide = await ready;
      pyodide.globals.set('samples_js', samples);
      pyodide.globals.set('params_json', JSON.stringify(params));
      const result = pyodide.runPython(`
try:
    samples = np.asarray(samples_js.to_py(), dtype=np.float32)
    result_json = json.dumps(analyze_pcm(samples, **json.loads(params_json)), allow_nan=False)
finally:
    globals().pop('samples', None)
result_json
`);
      self.postMessage({id, result: JSON.parse(result)});
    } catch (error) {
      self.postMessage({id, error: `Analysis failed: ${error.message}`});
    } finally {
      if (pyodide) {
        pyodide.globals.delete('samples_js');
        pyodide.globals.delete('params_json');
        pyodide.globals.delete('result_json');
      }
    }
  });
};
