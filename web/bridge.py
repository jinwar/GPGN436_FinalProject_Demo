"""Adapt unchanged teaching solvers to compact browser results (SI conversions explicit)."""
import json
import time
import numpy as np
import acoustic
import aquifer


def run(request_json, progress):
    request = json.loads(request_json)
    start = time.perf_counter()
    if request['kind'] == 'acoustic':
        model = acoustic.Model(**request['params'])
        # Movie arrays plus the Python/JS copy must fit ordinary student laptops.
        if model.nx > 241:
            raise ValueError('Browser demo: use dx >= 0.5 m to limit movie memory.')
        result = acoustic.simulate(model, request['source'], request['receivers'], progress)
        payload = {key: result[key] for key in
                   ('t', 'wavelet', 'data', 'forward', 'reverse', 'frame_times', 'image', 'peak', 'focus_time')}
        payload['peak'] = [float(x) for x in result['peak']]
        payload['focus_time'] = float(result['focus_time'])
        payload['nx'] = model.nx
        payload['dt'] = model.dt
    elif request['kind'] == 'aquifer':
        model = aquifer.Model(**request['params'])
        result = aquifer.simulate(model, progress)
        # Playback uses a bounded subset; well history and conservation use every step.
        indices = np.unique(np.r_[np.linspace(0, len(result['times']) - 1, 180).astype(int),
                                  np.argmin(abs(result['times'] / aquifer.DAY - model.production_days))])
        payload = dict(radius=result['radius'], times=result['times'] / aquifer.DAY,
                       frame_times=result['times'][indices] / aquifer.DAY,
                       pressure=(result['pressure'][indices] / 1e6).astype(np.float32),
                       drawdown=(result['drawdown'][indices] / 1e6).astype(np.float32),
                       well=result['pressure'][:, 0] / 1e6,
                       cutoff=result['cutoff'], produced_volume=result['produced_volume'],
                       balance_error=result['balance_error'], equilibrium_mpa=float(result['equilibrium_mpa']))
    else:
        raise ValueError('Unknown demo')
    payload['elapsed'] = time.perf_counter() - start
    return payload
