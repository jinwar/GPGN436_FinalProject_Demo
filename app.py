"""Run with: panel serve app.py --show"""
import asyncio
import numpy as np
import panel as pn
from bokeh.events import Tap
from bokeh.models import ColumnDataSource, LinearColorMapper, ColorBar, Span
from bokeh.palettes import RdBu11, Inferno256, Category10
from bokeh.plotting import figure
from acoustic import Model, simulate

pn.extension()


def make_app():
    # All mutable state belongs to this browser session.
    state = {'source': (60., 60.), 'receivers': [], 'result': None, 'busy': False}
    mode = pn.widgets.RadioButtonGroup(name='Mouse action', options=['Source', 'Receiver', 'Delete'], value='Receiver')
    frequency = pn.widgets.IntSlider(name='Ricker central frequency (Hz)', start=40, end=200, step=5, value=100)
    velocity = pn.widgets.IntSlider(name='Acoustic velocity (m/s)', start=1000, end=3000, step=100, value=1500)
    duration = pn.widgets.FloatSlider(name='Recording duration (s)', start=.12, end=.4, step=.02, value=.18)
    ring = pn.widgets.Button(name='Load receiver ring', button_type='default')
    clear = pn.widgets.Button(name='Clear receivers')
    run = pn.widgets.Button(name='Run forward + time reversal', button_type='primary')
    view = pn.widgets.RadioButtonGroup(options=['Forward', 'Time reversal', 'Focus image'], value='Forward')
    player = pn.widgets.Player(name='Playback', start=0, end=149, value=0, interval=60, disabled=True, width=530)
    gain = pn.widgets.FloatSlider(name='Wavefield display gain', start=1, end=20, step=1, value=5)
    status = pn.pane.Alert('Click to place receivers, or load a ring for a clear focusing demonstration.', alert_type='info')
    details = pn.pane.Markdown()
    time_label = pn.pane.Markdown('Place sensors, then run the simulation.')
    points = ColumnDataSource(dict(x=[60.], y=[60.]))
    receivers = ColumnDataSource(dict(x=[], y=[]))
    pixels = ColumnDataSource(dict(image=[np.zeros((121,121))], x=[-.5], y=[-.5], dw=[121.], dh=[121.]))
    mapper = LinearColorMapper(palette=list(reversed(RdBu11)), low=-1, high=1)
    plot = figure(title='Acoustic model • click to place sensors', x_range=(0,120), y_range=(0,120),
                  width=620, height=570, tools='tap,reset', x_axis_label='x (m)', y_axis_label='y (m)', match_aspect=True)
    plot.image(source=pixels, image='image', x='x', y='y', dw='dw', dh='dh', color_mapper=mapper)
    plot.scatter('x','y', source=points, marker='star', size=20, color='#f9b234', line_color='black', legend_label='Source')
    plot.scatter('x','y', source=receivers, marker='triangle', size=11, color='#00bbcc', line_color='black', legend_label='Receivers')
    plot.add_layout(ColorBar(color_mapper=mapper, width=10), 'right')
    plot.legend.location = 'top_left'
    traces = figure(title='Receiver recordings (common amplitude scale, vertically offset)', width=620, height=260,
                    x_axis_label='Recording time (s)', y_axis_label='Receiver number', tools='pan,wheel_zoom,reset')
    trace_data = ColumnDataSource(dict(xs=[],ys=[],color=[]))
    traces.multi_line(xs='xs', ys='ys', color='color', source=trace_data, line_width=1.4)
    cursor = Span(location=0,dimension='height',line_color='#e67e22',line_dash='dashed')
    traces.add_layout(cursor)
    wave = figure(title='Source Ricker wavelet', width=300, height=160, x_axis_label='Time (s)', tools='')
    wave_data = ColumnDataSource(dict(t=[], f=[]))
    wave.line('t','f',source=wave_data, color='#386cb0',line_width=2)

    def reset_result(*events):
        if state['busy']:
            return
        state['result'] = None
        player.direction = 0
        player.value = 0
        player.disabled = True
        player.loop_policy = 'once'
        trace_data.data = dict(xs=[],ys=[],color=[])
        pixels.data = dict(image=[np.zeros((121,121))],x=[-.5],y=[-.5],dw=[121.],dh=[121.])
        mapper.palette = list(reversed(RdBu11)); mapper.low=-1; mapper.high=1
        time_label.object = 'Configuration changed — run to update the wavefields.'
        m = Model(frequency=frequency.value,velocity=velocity.value,duration=duration.value)
        from acoustic import ricker
        t = np.linspace(0,4/m.frequency,300)
        wave_data.data = dict(t=t,f=ricker(t,m.frequency))
        details.object = f'**{m.nx} × {m.nx}** visible grid · Δx = {m.dx:.2f} m · Δt = {1000*m.dt:.3f} ms\n\n{len(state["receivers"])} receivers · homogeneous medium'
        status.object = 'Ready to simulate. Use a surrounding receiver array for the clearest focus.'
        status.alert_type = 'info'

    def sync_points():
        points.data = dict(x=[state['source'][0]],y=[state['source'][1]])
        receivers.data = dict(x=[p[0] for p in state['receivers']],y=[p[1] for p in state['receivers']])
        reset_result()

    def tap(event):
        if state['busy'] or event.x is None or event.y is None or not (0 <= event.x <= 120 and 0 <= event.y <= 120):
            return
        p = (event.x,event.y)
        if mode.value == 'Source':
            state['source'] = p
        elif mode.value == 'Receiver':
            if len(state['receivers']) >= 64:
                status.object = 'Maximum 64 receivers. Delete a receiver before adding another.'
                return
            state['receivers'].append(p)
        elif state['receivers']:
            distances = np.linalg.norm(np.array(state['receivers'])-p,axis=1)
            if min(distances) < 8:
                state['receivers'].pop(int(np.argmin(distances)))
        sync_points()

    def load_ring(event):
        a = np.linspace(0,2*np.pi,32,endpoint=False)
        state['receivers'] = list(zip(60+46*np.cos(a),60+46*np.sin(a)))
        sync_points()

    def clear_receivers(event):
        state['receivers'] = []
        sync_points()

    def render(*events):
        r = state['result']
        if r is None:
            return
        m = r['model']
        if view.value == 'Focus image':
            player.direction = 0
            field = r['image'] / max(float(r['image'].max()),1e-30)
            mapper.palette=Inferno256; mapper.low=0; mapper.high=1
            time_label.object = f'**Focus energy** near reverse time {r["focus_time"]:.4f} s · peak at ({r["peak"][0]:.1f}, {r["peak"][1]:.1f}) m'
        else:
            key = 'forward' if view.value == 'Forward' else 'reverse'
            field = r[key][player.value]
            scale = r[key + '_scale']/gain.value
            mapper.palette=list(reversed(RdBu11)); mapper.low=-scale; mapper.high=scale
            t = r['frame_times'][player.value]
            cursor.location = t if key == 'forward' else r['t'][-1]-t
            time_label.object = f'**{view.value}** · elapsed {t:.4f} s · frame {player.value+1}/{len(r["frame_times"])}'
        pixels.data = dict(image=[field],x=[-m.dx/2],y=[-m.dx/2],dw=[m.length+m.dx],dh=[m.length+m.dx])
        player.disabled = view.value == 'Focus image'

    @pn.io.with_lock
    async def calculate(event):
        if not state['receivers']:
            status.object='Place at least one receiver before running.'; status.alert_type='warning'
            return
        state['busy'] = True
        player.direction = 0
        player.disabled = True
        controls = [run,ring,clear,frequency,velocity,duration,mode]
        for widget in controls:
            widget.disabled=True
        run.loading=True
        status.object='Computing forward recordings and reverse-time propagation…'; status.alert_type='info'
        try:
            model = Model(frequency=frequency.value,velocity=velocity.value,duration=duration.value)
            result = await asyncio.to_thread(simulate,model,state['source'],list(state['receivers']))
            for key in ('forward', 'reverse'):
                result[key + '_scale'] = max(float(np.max(np.abs(result[key]))), 1e-30)
            state['result']=result
            player.end=len(result['frame_times'])-1; player.value=0
            view.value='Forward'
            data=result['data']; norm=max(float(np.max(np.abs(data))),1e-30)
            trace_data.data=dict(xs=[result['t']]*data.shape[1],
                ys=[i+1+.4*data[:,i]/norm for i in range(data.shape[1])],
                color=[Category10[10][i%10] for i in range(data.shape[1])])
            render()
            status.object='Simulation complete. Press ▶ to animate; switch to Time reversal or Focus image.'
            farthest=max(np.linalg.norm(np.asarray(state['receivers'])-state['source'],axis=1))
            if model.duration < farthest/model.velocity+3/model.frequency:
                status.object+=' Recording is short: some arrivals may be truncated; increase duration.'
            if len(state['receivers']) < 8:
                status.object+=' Sparse receiver coverage can produce ambiguous focusing.'
            status.alert_type='success'
        except Exception as exc:
            status.object=f'Simulation failed: {exc}'; status.alert_type='danger'
        finally:
            state['busy']=False; run.loading=False
            for widget in controls:
                widget.disabled=False

    plot.on_event(Tap,tap)
    ring.on_click(load_ring); clear.on_click(clear_receivers); run.on_click(calculate)
    for widget in (frequency,velocity,duration):
        widget.param.watch(reset_result,'value')
    for widget in (player,view,gain):
        widget.param.watch(render,'value')
    reset_result()
    return pn.template.FastListTemplate(
        title='Acoustic time-reversal lab', accent_base_color='#176b86', header_background='#123e52',
        sidebar=[pn.pane.Markdown('### Experiment\nClick the model to place a source or receivers. **Source** replaces the star; **Delete** removes a nearby receiver.'),
                 mode,ring,clear,frequency,velocity,duration,wave,details,run,gain,
                 pn.pane.Markdown('### Physics\nEighth-order spatial differences, second-order time stepping, and an outer absorbing sponge.\n\nThe focus image integrates reversed pressure squared around the expected focusing time. Finite receiver coverage limits reconstruction; amplitudes are arbitrary.')],
        main=[status,pn.Row(view),time_label,pn.pane.Bokeh(plot),player,pn.pane.Bokeh(traces)],
        sidebar_width=330)


make_app().servable()
