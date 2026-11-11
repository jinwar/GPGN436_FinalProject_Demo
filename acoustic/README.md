# Acoustic time-reversal lab

Interactive Python/Panel demonstration of 2D acoustic propagation and source localization.

## Run

From the repository root:

```bash
cd acoustic
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
Choose grid spacing `dx` and Courant number `C` in the sidebar; the calculated
`dt = C dx/v` updates immediately. Defaults are `dx = 1 m` and `C = 0.4`.
The Courant control is capped at 0.55, below the eighth-order 2D stability limit
(~0.555). Spacing choices divide the 120 m model exactly. A warning appears when
the grid provides fewer than six points per wavelength at `2.5 f`.
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

In the local Panel app, computation runs in a worker thread. The GitHub Pages
version uses a Pyodide Web Worker; browser tabs have independent geometry and results. Very large models are rejected to bound memory and computation.

## Validation

From the `acoustic/` directory with the virtual environment activated:

```bash
pip install pytest
pytest -q
```

Tests cover wavelet spectrum, travel times, off-grid reciprocity, finite propagation,
and localization with a surrounding receiver array. No external services or credentials
are required. Install packages from PyPI; run the Panel server again in each new session.

## Browser demo on GitHub Pages

[Open this lab](https://jinwar.github.io/GPGN436_FinalProject_Demo/#acoustic).
Python and NumPy execute locally in a Pyodide Web Worker. Use Run to compute,
then Play or the frame slider to inspect the results. Cancel terminates an active
calculation. Changing model inputs clears the previous result.
See the [root README](../README.md) for static preview and deployment instructions.
The Panel instructions above are an optional local alternative.
