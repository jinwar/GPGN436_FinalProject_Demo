"""2D acoustic finite differences, in the array/time-loop style of GPGN436/536.

Arrays use [y, x]. Units are metres and seconds; amplitudes are arbitrary.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Model:
    frequency: float = 100.0
    velocity: float = 1500.0
    duration: float = 0.18
    length: float = 120.0
    dx: float = 1.0
    courant: float = 0.4

    def __post_init__(self):
        for name in ('frequency', 'velocity', 'duration', 'length', 'dx', 'courant'):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.courant > 0.55:
            raise ValueError('Courant number must be at most 0.55 for this spatial stencil.')
        if self.dx > self.length or not np.isclose(self.length / self.dx, round(self.length / self.dx)):
            raise ValueError('Grid spacing must divide the model length exactly.')
        if self.duration < 4 / self.frequency:
            raise ValueError('Recording must include at least four wavelet periods.')
        if self.nx > 401 or self.duration / self.dt > 6000:
            raise ValueError('Model exceeds the interactive grid/time-step budget.')

    @property
    def nx(self):
        return int(round(self.length / self.dx)) + 1

    @property
    def dt(self):
        return self.courant * self.dx / self.velocity


def ricker(t, frequency):
    """Unit-peak Ricker wavelet, delayed by 1.5 central periods."""
    a = (np.pi * frequency * (t - 1.5 / frequency)) ** 2
    return (1 - 2*a) * np.exp(-a)


def awe_2d_explicit_solver(UUo, UUm, dx, dt, v, damping):
    """Eighth-order space, second-order time; overwrite previous field UUm.

    Damped equation: p_tt + 2*sigma*p_t = v**2 * Laplacian(p).
    damping is sigma*dt; a centered time derivative damps the outer sponge.
    """
    ## . . Define Courant number (squared) and spatial stencil
    C2 = (v*dt/dx)**2
    center = UUo[4:-4, 4:-4]
    lap = (-205/72 * 2) * center
    for k, weight in enumerate((8/5, -1/5, 8/315, -1/560), 1):
        ny, nx = UUo.shape
        lap += weight * (UUo[4+k:ny-4+k, 4:-4] + UUo[4-k:ny-4-k, 4:-4]
                         + UUo[4:-4, 4+k:nx-4+k] + UUo[4:-4, 4-k:nx-4-k])
    ## . . Update solution in place; the old previous field is no longer needed
    d = damping[4:-4, 4:-4]
    UUm[4:-4, 4:-4] = (2*center - (1-d)*UUm[4:-4, 4:-4] + C2*lap)/(1+d)
    return UUm


def point_weights(points, model, pad):
    """Bilinear sampling/injection weights for arbitrary physical coordinates."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError('Locations must be finite (x, y) pairs.')
    if np.any(points < 0) or np.any(points > model.length):
        raise ValueError('Locations must lie inside the displayed model.')
    q = points / model.dx + pad
    x, y = np.floor(q).astype(int).T
    fx, fy = (q - np.floor(q)).T
    return (np.stack((y,y,y+1,y+1), 1), np.stack((x,x+1,x,x+1), 1),
            np.stack(((1-fx)*(1-fy),fx*(1-fy),(1-fx)*fy,fx*fy), 1))


def simulate(model, source, receivers, progress=None):
    """Record forward data, then reinject their time reversal from zero fields.

    Imaging condition: integral of reverse pressure squared in a +/- half-period
    window about T - t0. It uses emission time, never source coordinates.
    Optional progress(percent, phase) reports completed time steps from the worker.
    Movie frames are decimated; receiver recordings and imaging use every step.
    """
    if not 1 <= len(receivers) <= 64:
        raise ValueError('Place between 1 and 64 receivers.')
    pad = 28
    sw = point_weights([source], model, pad)
    rw = point_weights(receivers, model, pad)
    n = model.nx + 2*pad
    dt, dx = model.dt, model.dx
    t = np.arange(int(np.ceil(model.duration/dt)) + 1)*dt
    F = ricker(t, model.frequency)
    ## . . Quadratic absorbing sponge outside the visible model
    j = np.arange(n)
    depth = np.maximum(np.maximum(pad-j, j-(n-pad-1)), 0)/(pad-4)
    sigma = 3*model.velocity/(pad*dx)*np.maximum(depth[:,None],depth[None,:])**2
    damping = sigma*dt
    crop = np.s_[pad:pad+model.nx, pad:pad+model.nx]
    indices = np.unique(np.linspace(0,len(t)-1,min(150,len(t)), dtype=int))
    data = np.zeros((len(t), len(receivers)))
    movies = []
    image = np.zeros((model.nx,model.nx))
    focus_time = t[-1] - 1.5/model.frequency
    last_percent = -1
    for reverse in (False, True):
        ## . . Initialize wavefields; reverse propagation starts from rest
        UUo = np.zeros((n,n))
        UUm = np.zeros_like(UUo)
        frames = []
        locations = rw if reverse else sw
        yy, xx, weights = locations
        for it in range(len(t)):
            percent = int(100 * (int(reverse) * len(t) + it) / (2 * len(t)))
            if progress is not None and percent != last_percent:
                progress(percent, "Time reversal" if reverse else "Forward propagation")
                last_percent = percent
            # Data and frame at t[it], before advancing to the next time step.
            if not reverse:
                data[it] = np.sum(UUo[rw[0],rw[1]]*rw[2],axis=1)
            if it in indices:
                frames.append(UUo[crop].astype(np.float32).copy())
            if reverse and abs(t[it]-focus_time) <= 0.5/model.frequency:
                image += UUo[crop]**2 * dt
            if it == len(t)-1:
                break
            tmp = awe_2d_explicit_solver(UUo,UUm,dx,dt,model.velocity,damping)
            forcing = data[-1-it] if reverse else np.array([F[it]])
            # dt² forcing, scaled to convenient arbitrary pressure units.
            np.add.at(tmp,(yy,xx), weights*forcing[:,None]*(model.velocity*dt/dx)**2)
            UUm, UUo = UUo, tmp
        movies.append(np.stack(frames))
    if progress is not None:
        progress(100, "Complete")
    peak_y, peak_x = np.unravel_index(np.argmax(image), image.shape)
    return dict(model=model, t=t, wavelet=F, data=data, forward=movies[0],
                reverse=movies[1], frame_times=t[indices], image=image,
                focus_time=focus_time, peak=(peak_x*dx,peak_y*dx))
