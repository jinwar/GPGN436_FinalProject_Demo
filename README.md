# GPGN 436/536 Final Project Demos

## Online demos for students

- [Acoustic time-reversal lab](https://jinwar.github.io/GPGN436_FinalProject_Demo/#acoustic)
- [Confined aquifer pumping and recovery](https://jinwar.github.io/GPGN436_FinalProject_Demo/#aquifer)

Both demos run Python and NumPy directly in your browser using **Pyodide**.
No account, Python installation, or application server is required. The first
visit downloads the Python runtime and NumPy from jsDelivr; subsequent visits
can use the browser cache. Each tab has its own calculation state. Performance
and available memory depend on the student's device. Closing/reloading the tab
clears the results. No simulation inputs are sent to a backend.

## Projects and numerical methods

- [Acoustic time reversal](acoustic/README.md): 2D wave propagation, receiver recordings, backpropagation, and focusing.
- [Confined aquifer](aquifer/README.md): radial pressure diffusion, constant-rate production, shut-in recovery, and volume conservation.

The browser runs the same teaching solvers in `acoustic/acoustic.py` and
`aquifer/aquifer.py`. A module Web Worker keeps calculations off the UI thread.
Progress messages update the page, and Cancel terminates and restarts the worker.
The static UI provides geometry editing, parameter controls, plots, and playback.
Acoustic grids are limited to 241 × 241 nodes in the browser to bound movie memory.
Aquifer playback retains at most 181 frames, including shut-in, while well history
and diagnostics use every numerical step. The optional local Panel apps remain
available in each project directory.

## Preview locally

```bash
python scripts/build_site.py
python -m http.server 8000 --directory _site
```

Open http://localhost:8000. An HTTP server is needed (opening `index.html` as a
local file does not support worker/module loading). Internet access is needed
for the pinned Pyodide 0.27.7 runtime and NumPy. No Node build or Panel server is
needed for the browser demos.

## Validation

```bash
python -m pip install numpy pytest
(cd acoustic && python -m pytest -q)
(cd aquifer && python -m pytest -q)
```

## GitHub Pages deployment

GitHub Pages publishes the generated `gh-pages` branch from its root directory.
Repository **Settings → Pages → Source** is **Deploy from a branch**, with
**gh-pages / (root)** selected. No custom workflow or application server is needed.

After updating and testing the source on `main`, publish with:

```bash
python scripts/deploy_pages.py
```

This script requires Git and an authenticated GitHub CLI (`gh`). It builds `_site/`,
then commits and pushes the output using a temporary checkout of `gh-pages`.
GitHub's standard Pages deployment publishes that branch automatically. Changes
to `main` alone do not republish the site; run the deployment script after changes.
The build copies the authoritative solver files into the generated site. Relative
URLs allow the demo to run under the repository's Pages path.

Render deployment configuration and launchers have been removed. Existing hosted
services are managed separately in the Render dashboard; deleting a configuration
file alone does not stop an already-provisioned service.
