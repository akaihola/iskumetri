// Independent runtime check: compare the canonical Python stages to native fixtures.
import {loadPyodide} from 'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.mjs';
const ready = (async () => {
  const py = await loadPyodide();
  await py.loadPackage('numpy');
  py.FS.writeFile('onsets.py', await (await fetch('/onsets.py')).text());
  py.runPython('import json, numpy as np\nfrom onsets import onset_strength');
  return py;
})();
self.onmessage = async ({data: {samples}}) => {
  try {
    const py = await ready;
    py.globals.set('samples_js', samples);
    const result = py.runPython(`
y = np.asarray(samples_js.to_py(), dtype=np.float32)
json.dumps(onset_strength(y).tolist())
`);
    py.runPython('del y, samples_js');
    self.postMessage({result: JSON.parse(result)});
  } catch (error) { self.postMessage({error: error.message}); }
};
