# Confined aquifer pumping and recovery

Interactive 1D radial pressure diffusion in homogeneous, confined sandstone.
Run locally with Python 3.10+:

```bash
pip install -r requirements.txt
panel serve app.py --address 127.0.0.1 --port 5007 --show
```

## Model

A fully penetrating 20 cm diameter well produces at constant volumetric rate Q
until the production time, then shuts in until the total simulation time.
Pressure is gauge pressure. Initial pressure (default 10 MPa) and thickness
(default 20 m) are editable, along with permeability, porosity, rate, reservoir
extent, and both times. The reservoir extent is measured from the well wall;
the outer radius equals 0.10 m plus the entered distance.

The equation is

    phi (cw + cp) dp/dt = (k/mu) (1/r) d/dr (r dp/dr).

The outer boundary has zero flux; extraction at the inner boundary is Q.
After shut-in both boundaries have zero flux. The entire calculation stops
when well pressure reaches zero gauge pressure, with a refined crossing time
and a warning. Valid results remain available for playback.

Fixed properties: water viscosity 1e-3 Pa s, water compressibility 4.4e-10 /Pa,
and sandstone pore-volume compressibility 4.5e-10 /Pa. The latter is an
illustrative value, not a universal sandstone property or mineral-grain
compressibility. No wellbore storage, skin, vertical flow, or pressure-dependent
material properties are modeled.

## Numerical approach

Logarithmically spaced radial nodes include the well wall and outer boundary.
Geometric midpoint faces define annular control volumes. Inter-node Darcy
conductances use logarithmic resistance. Backward Euler produces an explicitly
assembled tridiagonal system solved with the Thomas algorithm. Drawdown is the
computed variable, avoiding cancellation against a large initial pressure.
The teaching structure follows [Module 05](https://github.com/jinwar/GeophysicsComputing_GPGN436536/blob/main/05_Parabolic_PDEs.ipynb).
The radial conservative discretization and backward Euler solver are new.

Time steps grow from a small near-well diffusion time, restart at shut-in, and
land exactly on schedule boundaries. Animation frames therefore have variable
time spacing; the actual time appears above the plot. The profile uses a log
radius axis. The well history uses a linear time axis.

Volume balance checks sum(phi*(cw+cp)*annular_volume*drawdown) against Q times
actual production duration. After shut-in the eventual uniform pressure is
initial pressure minus produced volume divided by total storage capacity.

Validation: `python -m pytest` (install pytest separately). Tests cover zero
flow, volume conservation throughout production/recovery, cutoff refinement,
parameter validation, and spatial/temporal refinement.

Property context: [sandstone compressibility measurement](https://academic.oup.com/gji/article/164/3/685/2133401).
