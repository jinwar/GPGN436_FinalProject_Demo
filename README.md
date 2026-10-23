# Acoustic time-reversal lab

Interactive Python/Panel demonstration of 2D acoustic propagation and source localization.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
panel serve app.py --show
```

Select **Source** and click anywhere in the 120 m × 120 m model to move the source.
Select **Receiver** to add up to 64 receivers; **Delete** removes a receiver within
8 m of a click. The receiver-ring preset is a useful first experiment. Adjust the
Ricker central frequency (40–200 Hz, default 100 Hz), velocity and recording duration,
then click **Run forward + time reversal**. Use the player to animate or scrub the
forward and reverse movies. The orange cursor tracks the original recording time;
it moves backward during reversal. Select **Focus image** to see normalized focusing
energy. Changing geometry or model parameters invalidates the previous result.

## Numerical method

`acoustic.py` follows the explicit NumPy array, Courant-number, and `UUo`/`UUm`
time-loop style of [06_Hyperbolic_PDEs.ipynb](https://github.com/jinwar/GeophysicsComputing_GPGN436536/blob/main/06_Hyperbolic_PDEs.ipynb)
by Jinwar / the GPGN436536 course (the notebook credits Jeff Shragge for its solver).
This implementation uses second-order time and eighth-order space for
`p_tt + 2 sigma p_t = v² Laplacian(p) + s` in a homogeneous medium.
Arrays are indexed `[y, x]`; plot coordinates are metres, with y increasing upward.

The wavelet is `(1 - 2a) exp(-a)`, where `a = (pi f (t - t0))²` and `t0 = 1.5/f`.
Grid spacing provides at least six points per wavelength at `2.5 f`.
`dt = 0.4 dx/v` is below the eighth-order 2D stability limit (~0.555).
A 28-cell quadratic damping sponge lies **outside** the selectable model; it reduces
edge reflections but is not a perfectly matched layer. Bilinear weights support
sub-grid coordinates and use the same sampling/injection operator. Source amplitudes
are scaled to arbitrary units. Movies retain at most 150 frames; recording and imaging
use every numerical step.

Time reversal starts from zero pressure and injects the recorded receiver data in
reverse order with additive forcing. This finite-aperture backpropagation is not exact
reconstruction of the complete boundary wavefield. The imaging condition is
`I(x,y) = integral p_reverse(x,y,tau)² d tau`, over a half-period on either side of
`tau = T - t0`. It uses the known emission time, **not** the true source location.
The star is a visual reference only. Sparse/one-sided arrays, short recordings,
low frequencies and sponge reflections broaden the focus or create artifacts.

Computation runs in a worker thread; browser sessions have independent geometry and
results. Very large models are rejected to bound memory and computation.

## Validation

```bash
pip install pytest
pytest -q
```

Tests cover wavelet spectrum, travel times, off-grid reciprocity, finite propagation,
and localization with a surrounding receiver array. No external services or credentials
are required. Install packages from PyPI; run the Panel server again in each new session.

## Publish the website on Render

[Deploy to Render](https://render.com/deploy?repo=https://github.com/jinwar/GPGN436_FinalProject_Demo)

Sign in to Render, follow the deployment link, authorize this GitHub repository if
requested, and create the Blueprint service. The repository's `render.yaml` defines
a Python web service on the free plan. After deployment, open the service URL shown
in Render and select `/app` if it does not open automatically. This is separate
from saving or publishing a Codex cloud environment.

`serve.py` uses Render's `PORT` and `RENDER_EXTERNAL_HOSTNAME` to configure the
listener and permitted WebSocket origin. No API keys are needed by the application.
Free services may sleep when idle and take time to wake up. Multiple simultaneous
large simulations can exceed free-tier memory; use smaller models or a larger
instance for shared classroom use. The app does not persist browser-session results.
