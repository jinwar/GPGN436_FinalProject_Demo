// Each tab owns its Python runtime. Terminating this worker cancels a calculation.
import { loadPyodide } from 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.mjs';
let py;
const ready = (async () => {
  py = await loadPyodide();
  await py.loadPackage('numpy');
  for (const name of ['acoustic', 'aquifer', 'bridge']) {
    const response = await fetch(`./${name}.py`);
    if (!response.ok) throw new Error(`Cannot load ${name}.py (${response.status})`);
    py.FS.writeFile(`${name}.py`, await response.text());
  }
  py.globals.set('report_progress', (percent, phase) => self.postMessage({type:'progress', percent, phase}));
  await py.runPythonAsync('from bridge import run');
  self.postMessage({type:'ready'});
})();
ready.catch(error => self.postMessage({type:'error', message: String(error)}));
self.onmessage = async ({data}) => {
  try {
    await ready;
    py.globals.set('request_json', JSON.stringify(data));
    const result = await py.runPythonAsync('run(request_json, report_progress)');
    try {
      const converted = result.toJs({dict_converter: Object.fromEntries});
      self.postMessage({type:'result', result: converted});
    } finally { result.destroy(); }
  } catch (error) { self.postMessage({type:'error', message: String(error).trim().split('\n').at(-1)}); }
};
