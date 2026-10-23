import numpy as np
import pytest
from acoustic import Model, ricker, simulate


def test_ricker_frequency():
    t = np.arange(0,.2,.0001)
    for f in (40,100,200):
        spectrum = abs(np.fft.rfft(ricker(t,f)))
        peak = np.fft.rfftfreq(len(t),t[1])[spectrum.argmax()]
        assert abs(peak-f) <= 5


def test_travel_time_and_reciprocity():
    m = Model()
    a, b = (40.3,60.2), (80.7,60.6)
    r = simulate(m,a,[b])
    other = simulate(m,b,[a])
    np.testing.assert_allclose(r['data'],other['data'],atol=1e-12)
    arrival = np.linalg.norm(np.array(a)-b)/m.velocity + 1.5/m.frequency
    peak = r['t'][np.argmax(abs(r['data'][:,0]))]
    assert abs(peak-arrival) < .5/m.frequency
    assert np.isfinite(r['forward']).all()
    assert np.max(abs(r['data'])) > 1e-4


def test_refocus_off_center_source():
    m = Model()
    a = np.linspace(0,2*np.pi,32,endpoint=False)
    receivers = np.column_stack((60+46*np.cos(a),60+46*np.sin(a)))
    source = (51.3,65.2)
    r = simulate(m,source,receivers)
    assert np.isfinite(r['reverse']).all()
    assert np.linalg.norm(np.array(r['peak'])-source) < m.velocity/m.frequency/2
    assert r['image'].max() > 0
    # The image should concentrate energy near the source, not on injection sites.
    iy, ix = np.rint(np.array(source)[::-1]/m.dx).astype(int)
    assert r['image'][iy,ix] > 5*np.median(r['image'])


def test_invalid_inputs():
    with pytest.raises(ValueError):
        Model(frequency=0)
    with pytest.raises(ValueError):
        simulate(Model(),(60,60),[])
    with pytest.raises(ValueError):
        simulate(Model(),(-1,60),[(30,30)])


def test_progress_covers_both_passes_without_changing_results():
    updates = []
    model = Model(frequency=40, duration=.12)
    args = (model, (60, 60), [(30, 30)])
    expected = simulate(*args)
    actual = simulate(*args, progress=lambda percent, phase: updates.append((percent, phase)))
    percentages = [percent for percent, _ in updates]
    assert percentages[0] == 0
    assert percentages[-1] == 100
    assert percentages == sorted(set(percentages))
    assert {phase for _, phase in updates} == {'Forward propagation', 'Time reversal', 'Complete'}
    np.testing.assert_array_equal(actual['data'], expected['data'])
    np.testing.assert_array_equal(actual['reverse'], expected['reverse'])


def test_user_grid_and_courant():
    m = Model(dx=2.0, courant=.5, velocity=2000)
    assert m.nx == 61
    assert m.dt == pytest.approx(.0005)
    r = simulate(m, (60, 60), [(30, 30)])
    assert r['forward'].shape[1:] == (61, 61)
    assert r['t'][1] == pytest.approx(m.dt)
    assert np.isfinite(r['reverse']).all()
    for kwargs in ({'dx': 0}, {'dx': .1}, {'dx': 7}, {'courant': 0}, {'courant': .56}, {'courant': float('nan')}):
        with pytest.raises(ValueError):
            Model(**kwargs)
