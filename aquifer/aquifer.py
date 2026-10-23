"""Confined aquifer: radial pressure diffusion on a logarithmic grid.

SI units inside the solver. Pressure is gauge pressure; positive Q is extraction.
The explicit coefficient arrays and Thomas solve follow the teaching structure
of GPGN 436/536 Module 05, with annular control volumes for radial conservation.
"""
from dataclasses import dataclass
import numpy as np

DAY = 86400.0
MD = 9.869233e-16
WATER_VISCOSITY = 1.0e-3
WATER_COMPRESSIBILITY = 4.4e-10
PORE_COMPRESSIBILITY = 4.5e-10
WELL_RADIUS = 0.10


@dataclass(frozen=True)
class Model:
    permeability_md: float = 100.0
    porosity: float = 0.20
    rate_m3_day: float = 100.0
    boundary_distance: float = 500.0
    production_days: float = 10.0
    total_days: float = 30.0
    initial_mpa: float = 10.0
    thickness: float = 20.0
    nodes: int = 240
    time_steps: int = 600
    growth: float = 1.10

    def __post_init__(self):
        positive = ('permeability_md', 'porosity', 'boundary_distance',
                    'total_days', 'initial_mpa', 'thickness')
        for name in positive:
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f'{name.replace("_", " ")} must be positive and finite.')
        if not 0 < self.porosity < 1:
            raise ValueError('Porosity must be between 0 and 100%.')
        if not np.isfinite(self.rate_m3_day) or self.rate_m3_day < 0:
            raise ValueError('Production rate must be finite and nonnegative.')
        if not np.isfinite(self.production_days) or not 0 <= self.production_days <= self.total_days:
            raise ValueError('Production time must be between zero and total simulation time.')
        if not 40 <= self.nodes <= 1200 or int(self.nodes) != self.nodes:
            raise ValueError('Use 40–1200 radial nodes.')
        if not 100 <= self.time_steps <= 10000 or int(self.time_steps) != self.time_steps:
            raise ValueError('Use 100–10000 nominal time steps.')
        if not 1.01 <= self.growth <= 1.3:
            raise ValueError('Time-step growth must be between 1.01 and 1.3.')

    @property
    def storage(self):
        return self.porosity * (WATER_COMPRESSIBILITY + PORE_COMPRESSIBILITY)

    @property
    def diffusivity(self):
        return self.permeability_md * MD / (WATER_VISCOSITY * self.storage)


def radial_grid(model):
    """Return node radii, annular storage (m³/Pa), and conductance (m³/Pa/s).

    Nodes include the well wall and closed outer boundary. Geometric midpoint
    faces define the control volumes; end cells have half-width support.
    Logarithmic Darcy resistances give the inter-node conductance.
    """
    r = np.geomspace(WELL_RADIUS, WELL_RADIUS + model.boundary_distance, model.nodes)
    faces = np.r_[r[0], np.sqrt(r[:-1] * r[1:]), r[-1]]
    volume = np.pi * model.thickness * np.diff(faces**2)
    capacity = model.storage * volume
    conductance = (2 * np.pi * model.thickness * model.permeability_md * MD
                   / WATER_VISCOSITY / np.diff(np.log(r)))
    return r, capacity, conductance


def thomas(aa, bb, cc, dd):
    """Solve a tridiagonal system; a/c have length n-1, b/d length n."""
    b, d = bb.copy(), dd.copy()
    for i in range(1, len(b)):
        factor = aa[i - 1] / b[i - 1]
        b[i] -= factor * cc[i - 1]
        d[i] -= factor * d[i - 1]
    x = np.empty_like(d)
    x[-1] = d[-1] / b[-1]
    for i in range(len(b) - 2, -1, -1):
        x[i] = (d[i] - cc[i] * x[i + 1]) / b[i]
    return x


def implicit_step(drawdown, dt, rate, capacity, conductance):
    """Backward Euler update of drawdown, conserving annular fluid storage.

    Solve for drawdown rather than absolute pressure to avoid cancellation
    when the change is small compared with the initial reservoir pressure.
    The inner flux removes rate m³/s; outer flux is exactly zero.
    """
    aa = -dt * conductance
    cc = aa.copy()
    bb = capacity.copy()
    bb[:-1] += dt * conductance
    bb[1:] += dt * conductance
    dd = capacity * drawdown
    dd[0] += dt * rate
    return thomas(aa, bb, cc, dd)


def simulate(model, progress=None):
    """Simulate production then shut-in, stopping at zero well gauge pressure.

    Time steps start small at startup and shut-in, grow geometrically, and
    land exactly on production end and total time. If a step crosses zero,
    bisection refines the event instead of retaining negative pressures.
    """
    r, capacity, conductance = radial_grid(model)
    initial = model.initial_mpa * 1e6
    total = model.total_days * DAY
    shutin = model.production_days * DAY
    q = model.rate_m3_day / DAY
    drawdown = np.zeros(model.nodes)
    times, fields, rates = [0.0], [drawdown.copy()], [q if shutin > 0 else 0.0]
    t, removed, cutoff = 0.0, 0.0, False
    cap_dt = total / model.time_steps
    start_dt = min(cap_dt, 0.1 * capacity[0] / conductance[0])
    dt = start_dt
    last_percent = -1
    if progress:
        progress(0, 'Preparing radial grid')
    for iteration in range(20000):
        if t >= total:
            break
        producing = t < shutin
        rate = q if producing else 0.0
        endpoint = shutin if producing else total
        step = min(dt, endpoint - t)
        trial = implicit_step(drawdown, step, rate, capacity, conductance)
        if trial[0] >= initial:
            lo, hi = 0.0, step
            for _ in range(50):
                mid = 0.5 * (lo + hi)
                candidate = implicit_step(drawdown, mid, rate, capacity, conductance)
                if candidate[0] >= initial:
                    hi = mid
                else:
                    lo = mid
            step = lo
            trial = implicit_step(drawdown, step, rate, capacity, conductance)
            cutoff = True
        t += step
        removed += rate * step
        drawdown = trial
        times.append(t)
        fields.append(drawdown.copy())
        rates.append(rate)
        percent = min(99, int(100 * t / total))
        if progress and percent != last_percent:
            progress(percent, 'Pumping' if producing else 'Shut-in recovery')
            last_percent = percent
        if cutoff:
            break
        if abs(t - endpoint) < 1e-8:
            t = endpoint
            times[-1] = t
            dt = start_dt
        else:
            dt = min(cap_dt, dt * model.growth)
    else:
        raise RuntimeError('Time-step budget exceeded; reduce the parameter range.')
    if progress:
        progress(100, 'Pressure cutoff reached' if cutoff else 'Complete')
    fields = np.asarray(fields)
    stored_release = float(np.sum(capacity * fields[-1]))
    return dict(model=model, radius=r, times=np.asarray(times), drawdown=fields,
                pressure=initial-fields, rates=np.asarray(rates), capacity=capacity,
                cutoff=cutoff, produced_volume=removed,
                balance_error=abs(stored_release-removed)/max(removed, 1e-30),
                equilibrium_mpa=(initial-removed/capacity.sum())/1e6)
