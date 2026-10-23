from dataclasses import replace
import numpy as np
import pytest
from aquifer import Model, simulate, DAY, radial_grid


def test_zero_rate_and_zero_production():
    for model in (Model(rate_m3_day=0), Model(production_days=0)):
        result = simulate(model)
        assert np.all(result['pressure'] == model.initial_mpa*1e6)
        assert result['produced_volume'] == 0
        assert result['times'][-1] == model.total_days*DAY


def test_volume_balance_pumping_recovery_and_closed_boundary():
    m = Model()
    result = simulate(m)
    t, p = result['times'], result['pressure']
    assert not result['cutoff']
    assert result['produced_volume'] == pytest.approx(m.rate_m3_day*m.production_days)
    assert result['balance_error'] < 1e-7
    assert np.all(np.diff(p[t <= m.production_days*DAY, 0]) <= 1e-6)
    assert np.all(np.diff(p[t >= m.production_days*DAY, 0]) >= -1e-6)
    assert p[-1, 0] < m.initial_mpa*1e6
    volume_release = np.sum(result['drawdown'] * result['capacity'], axis=1)
    expected = m.rate_m3_day*np.minimum(t/DAY, m.production_days)
    np.testing.assert_allclose(volume_release, expected, rtol=1e-7, atol=1e-7)
    assert result['equilibrium_mpa'] < m.initial_mpa


def test_cutoff_event_and_progress():
    updates = []
    result = simulate(Model(rate_m3_day=10000), lambda p, phase: updates.append(p))
    assert result['cutoff']
    assert 0 < result['times'][-1] < 10*DAY
    assert np.min(result['pressure']) >= -1e-7
    assert abs(result['pressure'][-1, 0]) < 1e-5
    assert result['balance_error'] < 1e-7
    assert updates == sorted(updates)
    assert updates[0] == 0 and updates[-1] == 100


def test_grid_volume_and_convergence():
    m = Model(total_days=2, production_days=1)
    r, capacity, _ = radial_grid(m)
    expected = np.pi*m.thickness*((0.1+m.boundary_distance)**2-0.1**2)*m.storage
    assert capacity.sum() == pytest.approx(expected)
    np.testing.assert_allclose(r[1:]/r[:-1], r[1]/r[0])
    coarse = simulate(m)
    fine = simulate(replace(m, nodes=480, time_steps=1200, growth=1.05))
    comparison = np.array([0.001, 0.01, 0.1, 0.5, 1., 1.01, 1.1, 2.])*DAY
    pc = np.interp(comparison, coarse['times'], coarse['drawdown'][:, 0])
    pf = np.interp(comparison, fine['times'], fine['drawdown'][:, 0])
    np.testing.assert_allclose(pc, pf, rtol=0.015, atol=100)


def test_invalid_inputs():
    for kw in ({'porosity': 1}, {'permeability_md': 0}, {'production_days': 31},
               {'rate_m3_day': -1}, {'initial_mpa': float('nan')}, {'total_days': 0}):
        with pytest.raises(ValueError):
            Model(**kw)
