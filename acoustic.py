"""2D acoustic finite differences, in the array/time-loop style of GPGN436/536.

Arrays use [y, x]. Units are metres and seconds; amplitudes are arbitrary.
"""
# A dataclass groups model parameters; frozen=True prevents accidental changes during a run.
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Model:
    # Source central frequency (Hz), constant wave speed (m/s), and recording time (s).
    frequency: float = 100.0
    velocity: float = 1500.0
    duration: float = 0.18
    # The displayed domain is a square of this side length (m).
    length: float = 120.0
    # Equal x/y grid spacing (m); the Courant number controls the time step.
    dx: float = 1.0
    courant: float = 0.4

    def __post_init__(self):
        # Reject nonphysical or nonfinite values before allocating wavefield arrays.
        for name in ('frequency', 'velocity', 'duration', 'length', 'dx', 'courant'):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be finite and positive')
        # A conservative stability limit for this 2D eighth-order spatial stencil.
        if self.courant > 0.55:
            raise ValueError('Courant number must be at most 0.55 for this spatial stencil.')
        # Both ends of the domain must coincide with grid nodes.
        if self.dx > self.length or not np.isclose(self.length / self.dx, round(self.length / self.dx)):
            raise ValueError('Grid spacing must divide the model length exactly.')
        # Keep enough time samples to include the delayed source pulse.
        if self.duration < 4 / self.frequency:
            raise ValueError('Recording must include at least four wavelet periods.')
        # Limit memory and calculation time for an interactive classroom demo.
        if self.nx > 401 or self.duration / self.dt > 6000:
            raise ValueError('Model exceeds the interactive grid/time-step budget.')

    @property
    def nx(self):
        # N intervals need N+1 nodes, including x=0 and x=length.
        return int(round(self.length / self.dx)) + 1

    @property
    def dt(self):
        # Rearrange C = v*dt/dx to obtain the time step in seconds.
        return self.courant * self.dx / self.velocity


def ricker(t, frequency):
    """Unit-peak Ricker wavelet, delayed by 1.5 central periods."""
    # Shift the peak to t0=1.5/f so the wavelet starts near zero at t=0.
    a = (np.pi * frequency * (t - 1.5 / frequency)) ** 2
    # Evaluate the Ricker formula elementwise for the entire time array.
    return (1 - 2*a) * np.exp(-a)


def awe_2d_explicit_solver(UUo, UUm, dx, dt, v, damping):
    """Eighth-order space, second-order time; overwrite previous field UUm.

    Damped equation: p_tt + 2*sigma*p_t = v**2 * Laplacian(p).
    damping is sigma*dt; a centered time derivative damps the outer sponge.
    """
    ## . . Define Courant number (squared) and spatial stencil
    # The factor 1/dx² is absorbed into C²; lap below is an unscaled stencil sum.
    C2 = (v*dt/dx)**2
    # UUo is p at time n; UUm is p at n-1. Four edge nodes are excluded on each side.
    # The eighth-order derivative needs neighbors at offsets 1, 2, 3, and 4.
    center = UUo[4:-4, 4:-4]
    # Each 1D second derivative has center coefficient -205/72.
    # Add x and y derivatives, so the center coefficient is doubled.
    lap = (-205/72 * 2) * center
    # enumerate(..., 1) pairs each coefficient with its distance k from the center.
    for k, weight in enumerate((8/5, -1/5, 8/315, -1/560), 1):
        # Array order is [row, column] = [y, x], not [x, y].
        ny, nx = UUo.shape
        # The four slices are neighbors in +y, -y, +x, and -x.
        # Every slice has the same shape as center, so NumPy updates all interior nodes.
        lap += weight * (UUo[4+k:ny-4+k, 4:-4] + UUo[4-k:ny-4-k, 4:-4]
                         + UUo[4:-4, 4+k:nx-4+k] + UUo[4:-4, 4-k:nx-4-k])
    ## . . Update solution in place; the old previous field is no longer needed
    # d = sigma*dt is dimensionless and nonzero only in the absorbing region.
    d = damping[4:-4, 4:-4]
    # Centered differences in time give
    # (1+d)*p_next = 2*p_now - (1-d)*p_previous + C²*lap.
    # The right-hand side is evaluated before overwriting p_previous.
    # The outermost four rows/columns remain at their initialized value of zero.
    UUm[4:-4, 4:-4] = (2*center - (1-d)*UUm[4:-4, 4:-4] + C2*lap)/(1+d)
    # Return the reused array, which now holds p at time n+1.
    return UUm


def point_weights(points, model, pad):
    """Bilinear sampling/injection weights for arbitrary physical coordinates."""
    # Each input row is a physical (x, y) coordinate in metres.
    points = np.asarray(points, dtype=float)
    # Validate the shape before unpacking the coordinate columns.
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError('Locations must be finite (x, y) pairs.')
    # Only the visible square can contain a source or receiver.
    if np.any(points < 0) or np.any(points > model.length):
        raise ValueError('Locations must lie inside the displayed model.')
    # Convert metres to fractional grid indices; pad shifts into the larger sponge grid.
    q = points / model.dx + pad
    # floor identifies the lower-index corner; .T separates the x/y columns.
    x, y = np.floor(q).astype(int).T
    # Fractional offsets (0 to 1) locate the point inside its grid cell.
    fx, fy = (q - np.floor(q)).T
    # Return y indices, x indices, and weights, each with shape (number_of_points, 4).
    # Corner order: (x,y), (x+1,y), (x,y+1), (x+1,y+1).
    # The four bilinear weights sum to one; use the same weights to sample or inject.
    return (np.stack((y,y,y+1,y+1), 1), np.stack((x,x+1,x,x+1), 1),
            np.stack(((1-fx)*(1-fy),fx*(1-fy),(1-fx)*fy,fx*fy), 1))


def simulate(model, source, receivers, progress=None):
    """Record forward data, then reinject their time reversal from zero fields.

    Imaging condition: integral of reverse pressure squared in a +/- half-period
    window about T - t0. It uses emission time, never source coordinates.
    Optional progress(percent, phase) reports completed time steps from the worker.
    Movie frames are decimated; receiver recordings and imaging use every step.
    """
    # At least one recording is needed; cap receiver count for responsiveness.
    if not 1 <= len(receivers) <= 64:
        raise ValueError('Place between 1 and 64 receivers.')
    # Add 28 grid nodes on each side to absorb outgoing waves outside the displayed area.
    pad = 28
    # Precompute source and receiver interpolation indices/weights once per run.
    sw = point_weights([source], model, pad)
    rw = point_weights(receivers, model, pad)
    # Full computational width includes the visible grid plus padding on both sides.
    n = model.nx + 2*pad
    # Read the physical sampling intervals from the validated model.
    dt, dx = model.dt, model.dx
    # ceil ensures the final sample reaches (or slightly exceeds) the requested duration.
    t = np.arange(int(np.ceil(model.duration/dt)) + 1)*dt
    # Evaluate the source forcing history at every simulation time sample.
    F = ricker(t, model.frequency)
    ## . . Quadratic absorbing sponge outside the visible model
    # Indices along one axis of the full square grid.
    j = np.arange(n)
    # Distance beyond the visible square, clipped to zero inside it.
    # Normalize by the sponge width excluding the four untouched outer nodes.
    depth = np.maximum(np.maximum(pad-j, j-(n-pad-1)), 0)/(pad-4)
    # Broadcast column/row depths to a 2D array; use the larger depth at corners.
    # Quadratic growth turns damping on gradually to reduce artificial reflections.
    sigma = 3*model.velocity/(pad*dx)*np.maximum(depth[:,None],depth[None,:])**2
    # Convert damping rate sigma (1/s) to the dimensionless factor used by the update.
    damping = sigma*dt
    # np.s_ stores a reusable pair of slices selecting only the displayed domain.
    crop = np.s_[pad:pad+model.nx, pad:pad+model.nx]
    # Keep at most 150 roughly evenly spaced movie frames to control memory usage.
    indices = np.unique(np.linspace(0,len(t)-1,min(150,len(t)), dtype=int))
    # Each row is a time sample; each column is a receiver trace.
    data = np.zeros((len(t), len(receivers)))
    # This list will hold the forward movie followed by the reverse movie.
    movies = []
    # Accumulate reverse-field squared amplitude on the visible grid (not full sponge).
    image = np.zeros((model.nx,model.nx))
    # A source peak emitted at t0 should refocus near reverse time T-t0.
    focus_time = t[-1] - 1.5/model.frequency
    # Remember the last progress report so the UI is not updated at every time step.
    last_percent = -1
    # First run: one source, many receivers. Second run: receivers become sources.
    for reverse in (False, True):
        ## . . Initialize wavefields; reverse propagation starts from rest
        # Start the current field at zero throughout the full computational grid.
        UUo = np.zeros((n,n))
        # A zero previous field also supplies the at-rest initial condition.
        UUm = np.zeros_like(UUo)
        # Store selected snapshots for this propagation direction.
        frames = []
        # Forward forcing acts at the original source; reverse forcing acts at receivers.
        locations = rw if reverse else sw
        # Unpack the four grid-corner indices and weights for every injection point.
        yy, xx, weights = locations
        # Advance through time with the same dt for both propagation directions.
        for it in range(len(t)):
            # Forward occupies the first half of total progress, reversal the second half.
            percent = int(100 * (int(reverse) * len(t) + it) / (2 * len(t)))
            # The optional callback sends progress to the app without coupling the solver to Panel.
            if progress is not None and percent != last_percent:
                progress(percent, "Time reversal" if reverse else "Forward propagation")
                last_percent = percent
            # Data and frame at t[it], before advancing to the next time step.
            if not reverse:
                # Gather four corner values for every receiver, multiply by weights, then
                # sum axis=1 (the four corners) to obtain one pressure sample per receiver.
                data[it] = np.sum(UUo[rw[0],rw[1]]*rw[2],axis=1)
            # Movie sampling does not change the calculation or the receiver sampling rate.
            if it in indices:
                # Copy the cropped field so later in-place updates cannot change stored frames.
                # float32 reduces movie memory; propagation itself uses float64.
                frames.append(UUo[crop].astype(np.float32).copy())
            # Imaging condition: integrate reverse pressure squared over a one-period
            # window centered at T-t0. No forward/reverse cross-correlation is used.
            if reverse and abs(t[it]-focus_time) <= 0.5/model.frequency:
                # A rectangular time-integration rule: I += p_reverse² * dt.
                image += UUo[crop]**2 * dt
            # The final sample is recorded, but no extra time step beyond it is needed.
            if it == len(t)-1:
                break
            # Compute the homogeneous wave-equation update into the previous-field buffer.
            tmp = awe_2d_explicit_solver(UUo,UUm,dx,dt,model.velocity,damping)
            # Negative indexing reads receiver data from last sample to first in reverse time.
            # For the forward run, wrap the scalar wavelet sample as a one-source array.
            forcing = data[-1-it] if reverse else np.array([F[it]])
            # dt² forcing, scaled to convenient arbitrary pressure units.
            # Broadcast forcing[:,None] across the four interpolation corners.
            # add.at sums repeated indices correctly when multiple injection points overlap.
            # The C² scaling corresponds to dt² times a v²/dx²-scaled forcing term;
            # this adds a source term rather than prescribing pressure at the source.
            np.add.at(tmp,(yy,xx), weights*forcing[:,None]*(model.velocity*dt/dx)**2)
            # Swap references: the old current field becomes previous; tmp becomes current.
            # This reuses two large arrays rather than allocating a third on every step.
            UUm, UUo = UUo, tmp
        # Stack snapshots into one array with axes [frame, y, x].
        movies.append(np.stack(frames))
    if progress is not None:
        progress(100, "Complete")
    # argmax finds the strongest focus; unravel_index converts flat index to (row,col).
    peak_y, peak_x = np.unravel_index(np.argmax(image), image.shape)
    # Package numerical results for the app. Convert the image peak from indices
    # to physical (x,y) metres; the padding is already absent from the image.
    return dict(model=model, t=t, wavelet=F, data=data, forward=movies[0],
                reverse=movies[1], frame_times=t[indices], image=image,
                focus_time=focus_time, peak=(peak_x*dx,peak_y*dx))
