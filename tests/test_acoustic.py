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
