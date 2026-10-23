"""Launch: panel serve app.py --address 127.0.0.1 --port 5007"""
from concurrent.futures import ThreadPoolExecutor
from queue import SimpleQueue
from time import perf_counter
import numpy as np
import panel as pn
from bokeh.models import ColumnDataSource, Span, Range1d
from bokeh.plotting import figure
from aquifer import Model, simulate, DAY

pn.extension()


def make_app():
    state = dict(result=None, busy=False)
    permeability = pn.widgets.FloatInput(name='Permeability (mD)', value=100., start=0.001, step=10.)
    porosity = pn.widgets.FloatInput(name='Porosity (%)', value=20., start=0.1, end=99., step=1.)
    rate = pn.widgets.FloatInput(name='Production rate (m³/day)', value=100., start=0., step=10.)
    radius = pn.widgets.FloatInput(name='Well wall to outer boundary (m)', value=500., start=0.1, step=100.)
    initial = pn.widgets.FloatInput(name='Initial gauge pressure (MPa)', value=10., start=0.001, step=1.)
    thickness = pn.widgets.FloatInput(name='Aquifer thickness (m)', value=20., start=0.1, step=5.)
    production = pn.widgets.FloatInput(name='Production time (days)', value=10., start=0., step=1.)
    total = pn.widgets.FloatInput(name='Total simulation time (days)', value=30., start=0.001, step=1.)
    resolution = pn.widgets.Select(name='Radial grid nodes', options=[120, 240, 480], value=240)
    inputs = [permeability, porosity, rate, radius, initial, thickness, production, total, resolution]
    run = pn.widgets.Button(name='Run aquifer simulation', button_type='primary', sizing_mode='stretch_width')
    progress = pn.indicators.Progress(value=0, max=100, visible=False, sizing_mode='stretch_width')
    progress_text = pn.pane.Markdown('', visible=False)
    status = pn.pane.Alert('Choose reservoir properties, then run the simulation.', alert_type='info')
    properties = pn.pane.Markdown()
    summary = pn.pane.Markdown('')
    timestamp = pn.pane.Markdown('**Ready to simulate**')
    view = pn.widgets.RadioButtonGroup(options=['Reservoir pressure', 'Drawdown'], value='Reservoir pressure')
    player = pn.widgets.Player(name='Playback', start=0, end=1, value=0, interval=45,
                               disabled=True, loop_policy='once', sizing_mode='stretch_width')
    curve = ColumnDataSource(dict(r=[], y=[]))
    profile = figure(title='Reservoir pressure versus radius', height=370, sizing_mode='stretch_width',
                     x_axis_type='log', x_axis_label='Radius from well center (m)',
                     y_axis_label='Reservoir pressure (MPa gauge)', tools='pan,wheel_zoom,box_zoom,reset,save')
    profile.line('r', 'y', source=curve, line_width=3, color='#147d92')
    profile.scatter('r', 'y', source=curve, size=3, alpha=0.35, color='#147d92')
    history = figure(title='Well pressure during pumping and recovery', height=270,
                     sizing_mode='stretch_width', x_axis_label='Time (days)',
                     y_axis_label='Gauge pressure (MPa)', tools='pan,wheel_zoom,box_zoom,reset,save')
    trace = ColumnDataSource(dict(t=[], p=[]))
    history.line('t', 'p', source=trace, line_width=2.5, color='#147d92', legend_label='Well pressure')
    shutin_line = Span(location=10, dimension='height', line_color='#d97706', line_dash='dashed')
    cursor = Span(location=0, dimension='height', line_color='#475569', line_dash='dotted')
    zero = Span(location=0, dimension='width', line_color='#dc2626', line_dash='dashed')
    for line in (shutin_line, cursor, zero):
        history.add_layout(line)
    history.legend.location = 'bottom_right'

    def model():
        return Model(permeability_md=permeability.value, porosity=porosity.value/100,
                     rate_m3_day=rate.value, boundary_distance=radius.value,
                     production_days=production.value, total_days=total.value,
                     initial_mpa=initial.value, thickness=thickness.value, nodes=resolution.value)

    def reset(*events):
        if state['busy']:
            return
        player.direction = 0
        player.disabled = True
        state['result'] = None
        curve.data = dict(r=[], y=[])
        trace.data = dict(t=[], p=[])
        summary.object = ''
        timestamp.object = '**Ready to simulate**'
        progress.visible = progress_text.visible = False
        try:
            m = model()
            properties.object = (f'**Hydraulic diffusivity:** {m.diffusivity:.3g} m²/s\n\n'
                f'**Grid:** {m.nodes} logarithmically spaced nodes · well radius 0.10 m')
            run.disabled = False
            status.object = 'Ready. Pump at constant rate, then shut in and observe recovery.'
            status.alert_type = 'info'
        except (ValueError, TypeError) as exc:
            run.disabled = True
            status.object = str(exc)
            status.alert_type = 'warning'

    def render(*events):
        result = state['result']
        if result is None:
            return
        i = min(player.value, len(result['times'])-1)
        m = result['model']
        t = result['times'][i]/DAY
        pressure_mode = view.value == 'Reservoir pressure'
        field = result['pressure'] if pressure_mode else result['drawdown']
        curve.data = dict(r=result['radius'], y=field[i]/1e6)
        profile.title.text = 'Reservoir pressure versus radius' if pressure_mode else 'Radial pressure drawdown'
        profile.yaxis.axis_label = 'Reservoir pressure (MPa gauge)' if pressure_mode else 'Drawdown (MPa)'
        upper = m.initial_mpa if pressure_mode else max(float(result['drawdown'].max()/1e6), 0.01)
        profile.y_range = Range1d(-upper*0.03, upper*1.06)
        cursor.location = t
        phase = 'Pumping' if t < m.production_days and m.rate_m3_day > 0 else 'Shut-in'
        if result['cutoff'] and i == len(result['times'])-1:
            phase = 'Stopped at pressure cutoff'
        timestamp.object = (f'**{phase} · {t:.6g} days** · well pressure '
                            f'**{result["pressure"][i,0]/1e6:.4f} MPa gauge** · frame {i+1}/{len(field)}')

    def calculate(event):
        if state['busy']:
            return
        m = model()
        state['busy'] = True
        player.direction = 0
        player.disabled = True
        for widget in inputs + [run, view]:
            widget.disabled = True
        status.object = 'Calculating radial pressure diffusion…'
        status.alert_type = 'info'
        progress.value = 0
        progress.visible = progress_text.visible = True
        progress_text.object = '**Preparing · 0%**'
        started = perf_counter()
        updates = SimpleQueue()
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(simulate, m, lambda p, phase: updates.put((p, phase)))

        def poll():
            while not updates.empty():
                percent, phase = updates.get()
                progress.value = percent
                progress_text.object = f'**{phase} · {percent}%**'
            if not future.done():
                return
            poller.stop()
            try:
                result = future.result()
                state['result'] = result
                player.end = len(result['times'])-1
                player.value = 0
                profile.x_range = Range1d(0.1, result['radius'][-1])
                trace.data = dict(t=result['times']/DAY, p=result['pressure'][:,0]/1e6)
                history.x_range = Range1d(0, m.total_days)
                history.y_range = Range1d(-0.03*m.initial_mpa, 1.05*m.initial_mpa)
                shutin_line.location = m.production_days
                render()
                elapsed = perf_counter()-started
                if result['cutoff']:
                    status.object = (f'The requested flow rate cannot be maintained. Well pressure reached '
                        f'zero gauge pressure at {result["times"][-1]/DAY:.6g} days. '
                        'Simulation stopped; play back the results up to the cutoff.')
                    status.alert_type = 'warning'
                else:
                    status.object = 'Simulation complete. Press ▶ to animate pumping and shut-in recovery.'
                    status.alert_type = 'success'
                progress.value = 100
                progress_text.object = f'**Calculation finished in {elapsed:.2f} s**'
                summary.object = (f'**Water produced:** {result["produced_volume"]:,.3f} m³ · '
                    f'**Volume-balance error:** {result["balance_error"]:.2e}\n\n'
                    f'**Eventual uniform pressure after shut-in:** {result["equilibrium_mpa"]:.4f} MPa gauge. '
                    'A closed reservoir retains a net pressure decline after production.\n\n'
                    'Orange dashed line: scheduled shut-in. Dotted line: animation time. '
                    'Frames use variable time spacing to resolve startup and shut-in.')
            except Exception as exc:
                status.object = f'Simulation failed: {exc}'
                status.alert_type = 'danger'
                progress_text.object = '**Calculation failed**'
            finally:
                executor.shutdown(wait=False)
                state['busy'] = False
                for widget in inputs + [run, view]:
                    widget.disabled = False
                player.disabled = state['result'] is None

        poller = pn.state.add_periodic_callback(poll, period=100)

    for widget in inputs:
        widget.param.watch(reset, 'value')
    player.param.watch(render, 'value')
    view.param.watch(render, 'value')
    run.on_click(calculate)
    reset()
    physics = pn.pane.Markdown('''### Model assumptions
Homogeneous, confined sandstone; fully penetrating well; closed outer boundary.

**Fixed water properties:** viscosity 1 mPa·s; compressibility 4.4 × 10⁻¹⁰ Pa⁻¹.

**Sandstone pore-volume compressibility:** 4.5 × 10⁻¹⁰ Pa⁻¹ (illustrative).

All pressures are **gauge pressures**. Pumping stops the simulation at zero gauge pressure.

Implicit radial diffusion with annular volume conservation. No wellbore storage, skin, or vertical flow.''')
    return pn.template.FastListTemplate(
        title='Confined aquifer · pumping and recovery', header_background='#123e52', accent_base_color='#147d92',
        sidebar_width=330, sidebar=[pn.pane.Markdown('### Reservoir & well'),
            permeability, porosity, radius, thickness, initial,
            pn.pane.Markdown('### Production schedule'), rate, production, total,
            pn.Accordion(('Numerical grid', pn.Column(resolution, properties)), active=[]),
            run, progress_text, progress, physics],
        main=[status, timestamp, pn.pane.Bokeh(profile), pn.Column(view, player), pn.pane.Bokeh(history), summary])


make_app().servable()
