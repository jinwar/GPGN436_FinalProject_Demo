const $ = id => document.getElementById(id);
const configs = {
  acoustic: {
    title: 'Acoustic time reversal', run: 'Run forward + time reversal',
    fields: [
      ['frequency','Central frequency (Hz)',100,40,200,5],
      ['velocity','Wave speed (m/s)',1500,1000,3000,100],
      ['duration','Recording duration (s)',.18,.12,.4,.02],
      ['dx','Grid spacing (m)',1,[.5,.6,.75,1,1.2,1.5,2,2.4,3,4]],
      ['courant','Courant number',.4,.1,.55,.01]
    ],
    views:['Forward','Time reversal','Focus image'],
    explanation:'A homogeneous 120 × 120 m medium, eighth-order spatial differences and second-order time stepping. An outer sponge absorbs outgoing waves. Recorded signals are reinjected in reverse order. Focus energy uses the known emission time, not the source location. Sparse arrays and coarse grids can produce artifacts. Click the model to place geometry; calculations use arbitrary pressure units.'
  },
  aquifer: {
    title: 'Confined aquifer', run: 'Run aquifer simulation',
    fields: [
      ['permeability_md','Permeability (mD)',100,.001,100000, 'any'],
      ['porosity','Porosity (%)',20,.1,99,.1],
      ['rate_m3_day','Production rate (m³/day)',100,0,100000,'any'],
      ['boundary_distance','Well wall to boundary (m)',500,.1,100000,'any'],
      ['initial_mpa','Initial gauge pressure (MPa)',10,.001,1000,'any'],
      ['thickness','Aquifer thickness (m)',20,.1,10000,'any'],
      ['production_days','Production time (days)',10,0,100000,'any'],
      ['total_days','Total simulation time (days)',30,.001,100000,'any'],
      ['nodes','Radial grid nodes',240,[120,240,480]]
    ],
    views:['Reservoir pressure','Drawdown'],
    explanation:'Radial flow in homogeneous confined sandstone with a closed outer boundary and a 0.10 m well radius. A conservative logarithmic grid and implicit backward Euler scheme solve pressure diffusion. Production is constant until shut-in, then recovery begins. The run stops at zero well gauge pressure. No wellbore storage or skin is included. Playback samples variable time steps; read the displayed time.'
  }
};
let kind, worker, ready=false, busy=false, result=null, timer=null;
let source=[60,60], receivers=[];
let maxima={}, runParams={};
const colors=['#087d90','#c55f42','#7261a8','#3c8d62','#b27a22','#385da5'];
function status(message){ $('status').textContent=message; }
function stop(){clearInterval(timer);timer=null;$('play').textContent='Play';}
function lock(){
  $('run').disabled=!ready||busy; $('run').textContent=ready?configs[kind].run:'Loading Python…';
  $('cancel').disabled=!busy;
  document.querySelectorAll('#inputs input,#inputs select,#geometry button,#geometry select').forEach(el=>el.disabled=busy);
  $('play').disabled=!result||busy; $('frame').disabled=!result||busy;
}
function startWorker(){
  if(worker) worker.terminate();
  ready=false;busy=false;lock();
  const active = new Worker('./worker.js',{type:'module'}); worker=active;
  active.onmessage=({data})=>{
    if(worker!==active)return;
    if(data.type==='ready'){ready=true;status('Python is ready. Set up your experiment and run the simulation.');lock();}
    if(data.type==='progress'){$('progress').value=data.percent;status(`${data.phase} · ${data.percent}%`);}
    if(data.type==='error'){busy=false;status(`Could not run: ${data.message}. ${ready?'Check the inputs and try again.':'Check your connection and reload this page.'}`);lock();}
    if(data.type==='result'){
      result=data.result;busy=false;maxima={};
      if(kind==='acoustic') for(const key of ['forward','reverse','image']) maxima[key]=absMax(result[key]);
      $('frame').max=result.frame_times.length-1;
      $('frame').value=kind==='aquifer'?result.frame_times.length-1:0;
      $('progress').value=100;status(`Complete in ${result.elapsed.toFixed(2)} s · Python ran in this browser.`);
      if(kind==='acoustic'){
        const error=Math.hypot(result.peak[0]-source[0],result.peak[1]-source[1]);
        $('diagnostics').textContent=`Strongest focus: (${result.peak[0].toFixed(1)}, ${result.peak[1].toFixed(1)}) m · Distance from source: ${error.toFixed(2)} m · Expected reverse focus time: ${result.focus_time.toFixed(4)} s. The star marks the true source for comparison only.`;
      } else {
        $('diagnostics').textContent=`${result.cutoff?'Stopped at zero well gauge pressure. ':''}Produced volume: ${result.produced_volume.toFixed(2)} m³ · Relative volume-balance error: ${result.balance_error.toExponential(2)} · Eventual uniform pressure: ${result.equilibrium_mpa.toFixed(4)} MPa.`;
      }
      lock();draw();
    }
  };
  active.onerror=event=>{ready=false;busy=false;status(`Python could not load: ${event.message}. Check your connection and reload.`);lock();};
}
function absMax(value){
  if(typeof value==='number')return Math.abs(value);
  let max=0;for(const item of value)max=Math.max(max,absMax(item));return max;
}
function params(){
  const p={};for(const [name] of configs[kind].fields)p[name]=Number($(`param-${name}`).value);
  if(kind==='aquifer')p.porosity/=100;return p;
}
function invalidate(){
  stop();result=null;maxima={};$('frame').value=0;$('frame').max=0;
  $('diagnostics').textContent='';$('frame-label').textContent='';$('scale').textContent='';
  $('progress').value=0;lock();details();draw();
  if(ready)status('Inputs changed. Run the simulation to calculate new results.');
}
function details(){
  const p=params();
  if(kind==='acoustic'){
    const nx=Math.round(120/p.dx)+1;
    $('details').textContent=`${nx} × ${nx} grid · Δt = ${(1000*p.courant*p.dx/p.velocity).toFixed(3)} ms · ${receivers.length} receivers`;
    const warnings=[];
    if(p.velocity/(2.5*p.frequency*p.dx)<6)warnings.push('Coarse sampling: fewer than 6 points per wavelength at 2.5 × central frequency.');
    if(receivers.length<8)warnings.push('A sparse receiver array may produce an ambiguous focus.');
    $('warning').textContent=warnings.join(' ');
  }else{
    $('details').textContent='Closed outer boundary · Pressure in MPa · Well radius 0.10 m';
    $('warning').textContent=p.production_days>p.total_days?'Production time must not exceed total simulation time.':'';
  }
}
function selectLab(){
  const next=location.hash==='#aquifer'?'aquifer':'acoustic';
  if(kind===next)return;
  if(busy){worker.terminate();worker=null;ready=false;busy=false;}
  kind=next; const c=configs[kind];
  $('lab-title').textContent=c.title;$('explanation').textContent=c.explanation;
  $('source-link').href=`https://github.com/jinwar/GPGN436_FinalProject_Demo/tree/main/${kind}`;
  $('inputs').replaceChildren();
  for(const [name,label,value,min,max,step] of c.fields){
    const wrap=document.createElement('div'), l=document.createElement('label');l.htmlFor=`param-${name}`;l.textContent=label;
    const input=document.createElement(Array.isArray(min)?'select':'input');input.id=l.htmlFor;
    if(Array.isArray(min))for(const option of min)input.add(new Option(option,option));
    else{input.type='number';input.min=min;input.max=max;input.step=step;input.required=true;}
    input.value=value;input.addEventListener('change',invalidate);wrap.append(l,input);$('inputs').append(wrap);
  }
  $('view').replaceChildren(...c.views.map(v=>new Option(v,v)));
  for(const id of ['geometry','gain-label','wave-card'])$(id).style.display=kind==='acoustic'?'':'none';
  $('plot-title').textContent=kind==='acoustic'?'Wavefield and acquisition geometry':'Radial pressure profile';
  $('history-title').textContent=kind==='acoustic'?'Receiver recordings · individually normalized and offset':'Well gauge pressure through time';
  ['acoustic','aquifer'].forEach(k=>$(k+'-tab').classList.toggle('active',kind===k));
  invalidate();if(!worker)startWorker();
}
// Plot coordinates are explicit, so clicks and physical axes share one transform.
function axes(canvas,xmin,xmax,ymin,ymax,xlabel,ylabel,log=false,square=false){
  const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
  const box={x:75,y:22,w:canvas.width-100,h:canvas.height-78};
  if(square){box.w=box.h=Math.min(box.w,box.h);box.x=(canvas.width-box.w)/2;}
  const lx=v=>log?Math.log10(v):v;
  const X=v=>box.x+(lx(v)-lx(xmin))/(lx(xmax)-lx(xmin))*box.w;
  const Y=v=>box.y+box.h-(v-ymin)/(ymax-ymin)*box.h;
  ctx.font='13px system-ui';ctx.lineWidth=1;
  for(let i=0;i<=4;i++){
    const t=i/4, x=box.x+t*box.w,y=box.y+box.h-t*box.h;
    ctx.strokeStyle='#e6edf1';ctx.beginPath();ctx.moveTo(x,box.y);ctx.lineTo(x,box.y+box.h);ctx.moveTo(box.x,y);ctx.lineTo(box.x+box.w,y);ctx.stroke();
    ctx.fillStyle='#526b7b';ctx.textAlign='center';
    const xv=log?10**(lx(xmin)+t*(lx(xmax)-lx(xmin))):xmin+t*(xmax-xmin);
    ctx.fillText(format(xv),x,box.y+box.h+22);ctx.textAlign='right';ctx.fillText(format(ymin+t*(ymax-ymin)),box.x-9,y+4);
  }
  ctx.strokeStyle='#9fb2be';ctx.strokeRect(box.x,box.y,box.w,box.h);
  ctx.textAlign='center';ctx.fillStyle='#345466';ctx.fillText(xlabel,box.x+box.w/2,canvas.height-8);
  ctx.save();ctx.translate(18,box.y+box.h/2);ctx.rotate(-Math.PI/2);ctx.fillText(ylabel,0,0);ctx.restore();
  return {ctx,box,X,Y};
}
function format(v){return v===0?'0':Math.abs(v)<.01||Math.abs(v)>=10000?v.toExponential(1):Number(v.toPrecision(4)).toString();}
function line(a,x,y,color=colors[0]){
  const {ctx,X,Y}=a;ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();
  for(let i=0;i<x.length;i++){const px=X(x[i]),py=Y(y[i]);if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);}ctx.stroke();
}
function cursor(a,t){a.ctx.save();a.ctx.strokeStyle='#df8f19';a.ctx.lineWidth=2;a.ctx.setLineDash([5,4]);a.ctx.beginPath();a.ctx.moveTo(a.X(t),a.box.y);a.ctx.lineTo(a.X(t),a.box.y+a.box.h);a.ctx.stroke();a.ctx.restore();}
function blank(canvas,message){const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.font='16px system-ui';ctx.fillStyle='#68818f';ctx.textAlign='center';ctx.fillText(message,canvas.width/2,canvas.height/2);}
function heatmap(a,field,max,focus){
  const n=field.length, pixels=new ImageData(n,n), gain=focus?1:Number($('gain').value);
  for(let y=0;y<n;y++)for(let x=0;x<n;x++){
    const value=field[n-1-y][x],v=Math.max(-1,Math.min(1,value/(max||1)*gain)),i=4*(y*n+x);
    if(focus){pixels.data[i]=Math.round(250*v);pixels.data[i+1]=Math.round(35+185*v);pixels.data[i+2]=Math.round(65*(1-v));}
    else{pixels.data[i]=Math.round(255*(1+Math.min(0,v)));pixels.data[i+1]=Math.round(255*(1-Math.abs(v)));pixels.data[i+2]=Math.round(255*(1-Math.max(0,v)));}
    pixels.data[i+3]=255;
  }
  const off=document.createElement('canvas');off.width=n;off.height=n;off.getContext('2d').putImageData(pixels,0,0);
  a.ctx.imageSmoothingEnabled=false;a.ctx.drawImage(off,a.box.x,a.box.y,a.box.w,a.box.h);
}
function draw(){
  const f=Number($('frame').value),view=$('view').value;
  $('frame-number').textContent=result?`${f+1} / ${result.frame_times.length}`:'0 / 0';
  if(kind==='acoustic'){
    const a=axes($('primary'),0,120,0,120,'x (m)','y (m)',false,true);
    if(result){
      const key=view==='Forward'?'forward':view==='Time reversal'?'reverse':'image';
      heatmap(a,key==='image'?result.image:result[key][f],maxima[key],key==='image');
      $('frame-label').textContent=key==='image'?'Focus energy integrated near the expected refocusing time.':`${view} time: ${result.frame_times[f].toFixed(4)} s`;
      $('scale').textContent=key==='image'?'Color: dark = 0 · yellow = maximum normalized focus energy':`Color: blue = negative · white = zero · red = positive. Saturates at ±${format(maxima[key]/Number($('gain').value))} (arbitrary pressure units).`;
    }
    a.ctx.font='24px system-ui';a.ctx.textAlign='center';a.ctx.textBaseline='middle';a.ctx.fillStyle='#f4b229';a.ctx.strokeStyle='#162e43';a.ctx.lineWidth=2;a.ctx.strokeText('★',a.X(source[0]),a.Y(source[1]));a.ctx.fillText('★',a.X(source[0]),a.Y(source[1]));
    a.ctx.font='17px system-ui';for(const [x,y] of receivers){a.ctx.fillStyle='#00bac9';a.ctx.strokeText('▲',a.X(x),a.Y(y));a.ctx.fillText('▲',a.X(x),a.Y(y));}a.ctx.textBaseline='alphabetic';
    if(result){
      const count=receivers.length, h=axes($('history'),0,result.t.at(-1),-.8,count-.2,'Recording time (s)','Receiver index (offset)');
      for(let j=0;j<count;j++){
        const vals=Array.from(result.data,row=>row[j]),max=absMax(vals)||1;
        line(h,result.t,vals.map(v=>j+.38*v/max),colors[j%colors.length]);
      }
      cursor(h,view==='Time reversal'?result.t.at(-1)-result.frame_times[f]:result.frame_times[f]);
      const w=axes($('wavelet'),0,result.t.at(-1),-.5,1.1,'Time (s)','Amplitude');line(w,result.t,result.wavelet);
    }else{blank($('history'),'Receiver recordings appear after a run.');blank($('wavelet'),'Source wavelet appears after a run.');}
  }else if(result){
    const values=view==='Drawdown'?result.drawdown:result.pressure;
    const max=view==='Drawdown'?Math.max(absMax(result.drawdown),.001):runParams.initial_mpa;
    const a=axes($('primary'),result.radius[0],result.radius.at(-1),0,max*1.05,'Radius from well center (m, logarithmic)',`${view} (MPa)`,true);
    line(a,result.radius,values[f]);
    const h=axes($('history'),0,Math.max(result.times.at(-1),1e-10),0,runParams.initial_mpa*1.05,'Time (days)','Well pressure (MPa)');
    line(h,result.times,result.well);cursor(h,result.frame_times[f]);
    $('frame-label').textContent=`Time: ${format(result.frame_times[f])} days · ${result.frame_times[f]<runParams.production_days?'Pumping':'Shut-in recovery'}`;
    $('scale').textContent='Pressure is gauge pressure. Playback frames have unequal physical time intervals.';
  }else{blank($('primary'),'Run the simulation to view the pressure profile.');blank($('history'),'Well pressure history appears after a run.');}
}
$('parameters').addEventListener('submit',event=>{
  event.preventDefault();if(!ready||busy)return;
  if(kind==='acoustic'&&!receivers.length){status('Place at least one receiver or load the receiver ring.');return;}
  invalidate();runParams=params();busy=true;lock();status('Starting simulation…');
  worker.postMessage({kind,params:runParams,source,receivers});
});
$('cancel').onclick=()=>{stop();status('Calculation cancelled. Restarting Python…');startWorker();};
$('ring').onclick=()=>{receivers=Array.from({length:24},(_,i)=>[60+46*Math.cos(i*2*Math.PI/24),60+46*Math.sin(i*2*Math.PI/24)]);invalidate();};
$('clear').onclick=()=>{receivers=[];invalidate();};
$('primary').onclick=event=>{
  if(kind!=='acoustic'||busy)return;
  const canvas=$('primary'),rect=canvas.getBoundingClientRect(),size=Math.min(canvas.width-100,canvas.height-78),left=(canvas.width-size)/2;
  const x=((event.clientX-rect.left)*canvas.width/rect.width-left)/size*120;
  const y=(1-((event.clientY-rect.top)*canvas.height/rect.height-22)/size)*120;
  if(x<0||x>120||y<0||y>120)return;
  if($('mode').value==='Source')source=[x,y];
  else if($('mode').value==='Receiver'){
    if(receivers.length>=64){status('Maximum 64 receivers. Remove a receiver first.');return;}receivers.push([x,y]);
  }else{
    let closest=-1,distance=8;receivers.forEach((p,i)=>{const d=Math.hypot(p[0]-x,p[1]-y);if(d<distance){closest=i;distance=d;}});if(closest>=0)receivers.splice(closest,1);
  }
  invalidate();
};
$('view').onchange=()=>{stop();draw();};$('gain').oninput=draw;$('frame').oninput=()=>{stop();draw();};
$('play').onclick=()=>{
  if(timer){stop();return;}if(!result)return;
  if(Number($('frame').value)>=$('frame').max)$('frame').value=0;
  $('play').textContent='Pause';timer=setInterval(()=>{
    const next=Number($('frame').value)+1;
    if(next>Number($('frame').max)){stop();return;}$('frame').value=next;draw();
  },80);
};
window.addEventListener('hashchange',selectLab);
selectLab();
