"""Confined aquifer: radial pressure diffusion on a logarithmic grid.

SI units inside the solver. Pressure is gauge pressure; positive Q is extraction.
The explicit coefficient arrays and Thomas solve follow the teaching structure
of GPGN 436/536 Module 05, with annular control volumes for radial conservation.
"""
# A frozen dataclass keeps the physical parameters fixed while the solver runs.
from dataclasses import dataclass
import numpy as np

# Unit conversion constants: seconds per day and square metres per millidarcy.
DAY = 86400.0
MD = 9.869233e-16
# Dynamic viscosity in Pa s, held constant in this single-phase water model.
WATER_VISCOSITY = 1.0e-3
# Compressibilities have units 1/Pa. Their sum determines fluid/formation storage.
WATER_COMPRESSIBILITY = 4.4e-10
# Illustrative sandstone pore-volume compressibility, not mineral-grain compressibility.
PORE_COMPRESSIBILITY = 4.5e-10
# A 20 cm diameter well has a 0.10 m radius.
WELL_RADIUS = 0.10


@dataclass(frozen=True)
class Model:
    # Inputs use classroom-friendly units here; simulate converts them to SI units.
    permeability_md: float = 100.0
    # Porosity is a fraction (0.20 = 20%), not a percentage.
    porosity: float = 0.20
    rate_m3_day: float = 100.0
    # Distance is measured from the well wall, not from the well center (m).
    boundary_distance: float = 500.0
    # Pump from t=0 to production_days, then allow recovery until total_days.
    production_days: float = 10.0
    total_days: float = 30.0
    # Uniform initial gauge pressure (MPa) and aquifer thickness (m).
    initial_mpa: float = 10.0
    thickness: float = 20.0
    # Numerical controls: radial node count, nominal maximum time step, step growth.
    # time_steps limits dt to total/time_steps; the actual number of steps is larger.
    nodes: int = 240
    time_steps: int = 600
    growth: float = 1.10

    def __post_init__(self):
        # Check physical inputs before computing grid spacing or dividing by parameters.
        positive = ('permeability_md', 'porosity', 'boundary_distance',
                    'total_days', 'initial_mpa', 'thickness')
        # getattr reads each named dataclass field; reject NaN, infinity, and nonpositive values.
        for name in positive:
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f'{name.replace("_", " ")} must be positive and finite.')
        # A pore-volume fraction must be strictly between zero and one.
        if not 0 < self.porosity < 1:
            raise ValueError('Porosity must be between 0 and 100%.')
        # Zero production is allowed as a useful no-change reference experiment.
        if not np.isfinite(self.rate_m3_day) or self.rate_m3_day < 0:
            raise ValueError('Production rate must be finite and nonnegative.')
        # The schedule must shut in no later than the end of the simulation.
        if not np.isfinite(self.production_days) or not 0 <= self.production_days <= self.total_days:
            raise ValueError('Production time must be between zero and total simulation time.')
        # Keep the spatial grid large enough to resolve the profile but affordable interactively.
        if not 40 <= self.nodes <= 1200 or int(self.nodes) != self.nodes:
            raise ValueError('Use 40–1200 radial nodes.')
        # Bound the time-resolution control and require integer node/step counts.
        if not 100 <= self.time_steps <= 10000 or int(self.time_steps) != self.time_steps:
            raise ValueError('Use 100–10000 nominal time steps.')
        # Geometric growth gradually increases dt after the small startup steps.
        if not 1.01 <= self.growth <= 1.3:
            raise ValueError('Time-step growth must be between 1.01 and 1.3.')

    @property
    def storage(self):
        # Storage per bulk volume per unit pressure, S = phi*(cw+cp), in 1/Pa.
        # Multiplying S by rock volume gives a cell storage capacity in m³/Pa.
        return self.porosity * (WATER_COMPRESSIBILITY + PORE_COMPRESSIBILITY)

    @property
    def diffusivity(self):
        # Hydraulic diffusivity D = k/(mu*S) in m²/s controls pressure-spreading speed.
        return self.permeability_md * MD / (WATER_VISCOSITY * self.storage)


def radial_grid(model):
    """Return node radii, annular storage (m³/Pa), and conductance (m³/Pa/s).

    Nodes include the well wall and closed outer boundary. Geometric midpoint
    faces define the control volumes; end cells have half-width support.
    Logarithmic Darcy resistances give the inter-node conductance.
    """
    # geomspace uses a constant radius ratio: fine spacing near the well, coarse far away.
    # Include both boundary nodes; the outer radius is well radius + entered distance.
    r = np.geomspace(WELL_RADIUS, WELL_RADIUS + model.boundary_distance, model.nodes)
    # Each internal face is the geometric mean of adjacent node radii.
    # np.r_ joins the inner boundary, internal faces, and outer boundary into one array.
    faces = np.r_[r[0], np.sqrt(r[:-1] * r[1:]), r[-1]]
    # A cylindrical annulus has bulk volume pi*h*(r_outer²-r_inner²).
    # np.diff subtracts successive face values to give one volume per node.
    volume = np.pi * model.thickness * np.diff(faces**2)
    # A pressure drop of 1 Pa releases capacity[i] cubic metres from cell i.
    capacity = model.storage * volume
    # Integrating radial Darcy flow between two radii gives
    # G = 2*pi*h*k / (mu*ln(r_right/r_left)). Then flow = G*pressure_difference.
    # There are n-1 conductances connecting n nodes; none connects outside the domain.
    conductance = (2 * np.pi * model.thickness * model.permeability_md * MD
                   / WATER_VISCOSITY / np.diff(np.log(r)))
    # These geometry-dependent arrays are reused at every time step.
    return r, capacity, conductance


def thomas(aa, bb, cc, dd):
    """Solve a tridiagonal system; a/c have length n-1, b/d length n."""
    # Copy the diagonal and right-hand side: elimination modifies them in place.
    # aa, bb, cc represent lower, main, and upper diagonals; dd is the RHS.
    b, d = bb.copy(), dd.copy()
    # Forward elimination removes each lower-diagonal entry, row by row.
    for i in range(1, len(b)):
        # Divide by the previous pivot to find the multiple of the previous row to subtract.
        factor = aa[i - 1] / b[i - 1]
        # Update this row's diagonal after eliminating its lower-diagonal coefficient.
        b[i] -= factor * cc[i - 1]
        # Apply the same row operation to the RHS to preserve the equations.
        d[i] -= factor * d[i - 1]
    # Allocate the solution vector; every entry will be assigned during back substitution.
    x = np.empty_like(d)
    # The last eliminated row has just one unknown, so solve it directly.
    x[-1] = d[-1] / b[-1]
    # Back substitution moves from the next-to-last row toward the first.
    for i in range(len(b) - 2, -1, -1):
        # Subtract the already-known contribution from x[i+1], then divide by the pivot.
        x[i] = (d[i] - cc[i] * x[i + 1]) / b[i]
    # Thomas elimination solves this tridiagonal system in O(n) work and storage.
    return x


def implicit_step(drawdown, dt, rate, capacity, conductance):
    """Backward Euler update of drawdown, conserving annular fluid storage.

    Solve for drawdown rather than absolute pressure to avoid cancellation
    when the change is small compared with the initial reservoir pressure.
    The inner flux removes rate m³/s; outer flux is exactly zero.
    """
    # For drawdown s = p_initial-p, the cell equation is
    # C_i*(s_next-s_now) = dt*sum_j G_ij*(s_j_next-s_i_next) + dt*Q_i.
    # Move the neighbor terms to the left: off-diagonal coefficients are -dt*G.
    aa = -dt * conductance
    # Each link has the same conductance in both directions, making the matrix symmetric.
    cc = aa.copy()
    # Begin the main diagonal with each cell's storage capacity C_i.
    bb = capacity.copy()
    # Add each link's conductance to the node on its left (smaller radius).
    bb[:-1] += dt * conductance
    # Add it to the node on its right. End nodes have only one neighbor.
    # No outer-face term is added: this implements the closed, no-flow boundary.
    bb[1:] += dt * conductance
    # Known RHS contribution is storage times drawdown at the previous time.
    dd = capacity * drawdown
    # Positive extraction increases drawdown. Put the removed volume Q*dt
    # only in the first cell, implementing the well-wall flux boundary.
    dd[0] += dt * rate
    # Solve for all new drawdowns together: backward Euler is implicit in space.
    return thomas(aa, bb, cc, dd)


def simulate(model, progress=None):
    """Simulate production then shut-in, stopping at zero well gauge pressure.

    Time steps start small at startup and shut-in, grow geometrically, and
    land exactly on production end and total time. If a step crosses zero,
    bisection refines the event instead of retaining negative pressures.
    """
    # Build the geometry and constant hydraulic connections once.
    r, capacity, conductance = radial_grid(model)
    # Convert MPa to Pa; gauge pressure zero is the user-selected stopping threshold.
    initial = model.initial_mpa * 1e6
    # Convert the schedule from days to seconds for the SI diffusion equation.
    total = model.total_days * DAY
    shutin = model.production_days * DAY
    # Convert volumetric extraction rate from m³/day to m³/s.
    q = model.rate_m3_day / DAY
    # Initial pressure is uniform, so drawdown is zero at every radial node.
    drawdown = np.zeros(model.nodes)
    # Store the initial frame. Copies preserve snapshots when the evolving field changes.
    times, fields, rates = [0.0], [drawdown.copy()], [q if shutin > 0 else 0.0]
    # Track elapsed seconds, cumulative produced volume (m³), and whether the cutoff fired.
    t, removed, cutoff = 0.0, 0.0, False
    # This is the maximum time step, not the animation interval.
    cap_dt = total / model.time_steps
    # C/G has units of seconds: use a fraction of the near-well storage/flow timescale.
    # Backward Euler is stable at larger dt, but small steps resolve early-time changes.
    start_dt = min(cap_dt, 0.1 * capacity[0] / conductance[0])
    # Start with the small step; allow it to grow only after successful advancement.
    dt = start_dt
    # Throttle progress messages to integer-percent changes.
    last_percent = -1
    # The optional callback lets the app report progress without importing UI code here.
    if progress:
        progress(0, 'Preparing radial grid')
    # A hard iteration budget prevents pathological parameter combinations from running forever.
    for iteration in range(20000):
        # Stop normally once the requested total duration has been reached.
        if t >= total:
            break
        # After the exact shut-in time, the well becomes a zero-flow boundary.
        producing = t < shutin
        # Use constant production during pumping and zero during recovery.
        rate = q if producing else 0.0
        # The next step must not straddle the rate change or the end of the simulation.
        endpoint = shutin if producing else total
        # Shorten the proposed step if needed to land on that schedule boundary.
        step = min(dt, endpoint - t)
        # Compute a tentative implicit update before accepting its time and produced volume.
        trial = implicit_step(drawdown, step, rate, capacity, conductance)
        # p_well = initial - drawdown[0]; drawdown >= initial means pressure <= 0.
        if trial[0] >= initial:
            # Bracket the cutoff within this step: zero elapsed time is safe, full step crosses it.
            lo, hi = 0.0, step
            # Bisect the step duration, always solving from the last accepted field.
            # This refines the discrete-model crossing time, not the spatial/time discretization error.
            for _ in range(50):
                # Try the middle of the remaining safe/unsafe interval.
                mid = 0.5 * (lo + hi)
                # Recompute the step for that shorter duration; do not advance the accepted state yet.
                candidate = implicit_step(drawdown, mid, rate, capacity, conductance)
                # A nonpositive well pressure moves the unsafe upper bound earlier.
                if candidate[0] >= initial:
                    hi = mid
                else:
                    # Otherwise the trial is safe, so move the lower bound later.
                    lo = mid
            # Accept the safe side of the refined bracket to avoid retaining a negative pressure.
            step = lo
            # Recalculate the field for the accepted shortened step.
            trial = implicit_step(drawdown, step, rate, capacity, conductance)
            # Remember to terminate after saving this final valid frame.
            cutoff = True
        # Accept the step and advance physical time.
        t += step
        # Only actual accepted pumping time contributes to cumulative extracted volume.
        removed += rate * step
        # The tentative solution is now the current state.
        drawdown = trial
        # Keep one time, radial profile, and applied interval rate for each accepted step.
        times.append(t)
        # Copy the field so stored history does not alias a mutable solution array.
        fields.append(drawdown.copy())
        rates.append(rate)
        # Reserve 100% for the final callback, including early termination at the cutoff.
        percent = min(99, int(100 * t / total))
        # Report changes only, distinguishing pumping from recovery.
        if progress and percent != last_percent:
            progress(percent, 'Pumping' if producing else 'Shut-in recovery')
            last_percent = percent
        # Do not continue pumping or simulate recovery after the pressure-limit event.
        if cutoff:
            break
        # Remove tiny floating-point timing differences at schedule boundaries.
        if abs(t - endpoint) < 1e-8:
            t = endpoint
            # Ensure the saved frame also has the exact schedule time.
            times[-1] = t
            # Restart with small steps at shut-in to resolve the rapid pressure recovery.
            dt = start_dt
        else:
            # Away from a schedule boundary, grow dt gradually up to its chosen maximum.
            dt = min(cap_dt, dt * model.growth)
    else:
        # Python for/else reaches here only if all 20000 iterations finish without a break.
        raise RuntimeError('Time-step budget exceeded; reduce the parameter range.')
    # The optional callback lets the app report progress without importing UI code here.
    if progress:
        progress(100, 'Pressure cutoff reached' if cutoff else 'Complete')
    # Convert the profile list to an array with axes [time_index, radial_node].
    fields = np.asarray(fields)
    # Sum C_i*drawdown_i: fluid volume released from storage throughout the reservoir.
    # With a closed boundary this must equal cumulative produced water.
    stored_release = float(np.sum(capacity * fields[-1]))
    # Return gauge pressure as initial-drawdown, together with animation and diagnostic data.
    # The relative balance error divides by produced volume (protected against zero flow).
    # After shut-in, eventual uniform pressure follows from total storage and total extraction.
    return dict(model=model, radius=r, times=np.asarray(times), drawdown=fields,
                pressure=initial-fields, rates=np.asarray(rates), capacity=capacity,
                cutoff=cutoff, produced_volume=removed,
                balance_error=abs(stored_release-removed)/max(removed, 1e-30),
                equilibrium_mpa=(initial-removed/capacity.sum())/1e6)
