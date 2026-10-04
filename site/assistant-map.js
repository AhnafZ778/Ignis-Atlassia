/* Reproducible display aggregation. Measurements remain in the returned bundle.
   Heat = Gaussian-smoothed occupied 1 km cells, never inferred burned area.
   Kernels and normalization are fixed in geography and for the entire study. */
(function(root){
  'use strict';
  const SOURCES=['MODIS_SP','VIIRS_SNPP_SP'],SIGMA_KM=1;
  const key=c=>`${c.grid_x},${c.grid_y}`;
  function createIndex(bundle){
    const frames=bundle.frames,records=new Map(),prefix={},first={};
    for(const r of bundle.observations){if(!records.has(r.date))records.set(r.date,[]);records.get(r.date).push(r);}
    for(const source of ['joint',...SOURCES]){
      const seen=new Map();prefix[source]=[];first[source]=new Map();
      frames.forEach((f,i)=>{for(const c of f.cells){if(source!=='joint'&&!c.sources.includes(source))continue;const id=key(c);if(!first[source].has(id))first[source].set(id,i);const old=seen.get(id);seen.set(id,{...c,observed_days:(old?.observed_days||0)+1,first_index:old?.first_index??i,last_index:i,sources:[...new Set([...(old?.sources||[]),...c.sources])]});}prefix[source].push([...seen.values()]);});
    }
    // Gaussian concentration maxima evaluated at occupied grid centers across
    // all frames. Projection is locally adjusted to true km at each latitude.
    const maxima={};for(const source of ['joint'])for(const scope of ['daily','history']){
      let maximum=0;for(let i=0;i<frames.length;i++){const cells=scope==='history'?prefix[source][i]:frames[i].cells.filter(c=>source==='joint'||c.sources.includes(source));const weighted=cells.map(c=>({...c,value:scope==='history'?c.observed_days:1}));const latitude=weighted.length?weighted[0].latitude:0,cos=Math.cos(latitude*Math.PI/180),bins=new Map();for(const c of weighted){const id=Math.floor(c.longitude*111.32*cos)+','+Math.floor(c.latitude*111.32);if(!bins.has(id))bins.set(id,[]);bins.get(id).push(c);}for(const c of weighted){const x=Math.floor(c.longitude*111.32*cos),y=Math.floor(c.latitude*111.32),rx=Math.ceil(3*cos/Math.cos(c.latitude*Math.PI/180))+1,near=[];for(let dx=-rx;dx<=rx;dx++)for(let dy=-4;dy<=4;dy++)near.push(...(bins.get((x+dx)+','+(y+dy))||[]));maximum=Math.max(maximum,concentration(near,c));}}
      maxima[source+':'+scope]=maximum||1;
    }
    for(const source of SOURCES)for(const scope of ['daily','history'])maxima[source+':'+scope]=maxima['joint:'+scope];
    return {bundle,records,prefix,first,maxima};
  }
  function concentration(cells,target){let value=0;for(const c of cells){const dy=(c.latitude-target.latitude)*111.32,dx=(c.longitude-target.longitude)*111.32*Math.cos(target.latitude*Math.PI/180),d=dx*dx+dy*dy;if(d<=9*SIGMA_KM*SIGMA_KM)value+=(c.value??1)*Math.exp(-d/(2*SIGMA_KM*SIGMA_KM));}return value;}
  function frame(index,i,source='joint',scope='daily'){
    i=Math.max(0,Math.min(index.bundle.frames.length-1,Number(i)));const f=index.bundle.frames[i];
    const cells=scope==='history'?index.prefix[source][i]:f.cells.filter(c=>source==='joint'||c.sources.includes(source));
    const rows=scope==='history'?index.bundle.observations.filter(r=>r.date<=f.date_utc&&(source==='joint'||r.source_id===source)):(index.records.get(f.date_utc)||[]).filter(r=>source==='joint'||r.source_id===source);
    const fresh=f.cells.filter(c=>(source==='joint'||c.sources.includes(source))&&index.first[source].get(key(c))===i);
    return {date:f.date_utc,index:i,cells,records:rows,newCells:fresh,maximum:index.maxima[source+':'+scope],scope,source,weighted:cells.map(c=>({...c,value:scope==='history'?c.observed_days:1}))};
  }
  const ramp=t=>{const stops=[[255,242,178],[254,196,79],[252,141,60],[227,74,51],[179,0,0]];t=Math.max(0,Math.min(1,t))*4;const i=Math.min(3,Math.floor(t)),f=t-i;return stops[i].map((n,c)=>Math.round(n+(stops[i+1][c]-n)*f));};
  function drawHeat(g,width,height,data,project){
    if(!width||!height||!data?.weighted.length)return;
        // Render to a coarse scalar field then colorize once. Additive values are
        // normalized to the same study maximum, not a per-day auto contrast.
        const step=4,w=Math.ceil(width/step),h=Math.ceil(height/step),values=new Float32Array(w*h),maximum=data.maximum;
        for(const c of data.weighted){const p=project([c.latitude,c.longitude]),east=project([c.latitude,c.longitude+SIGMA_KM/(111.32*Math.cos(c.latitude*Math.PI/180))]),north=project([c.latitude+SIGMA_KM/111.32,c.longitude]);const sx=Math.max(.35,Math.abs(east.x-p.x)/step),sy=Math.max(.35,Math.abs(north.y-p.y)/step),cx=p.x/step,cy=p.y/step,rx=sx*3,ry=sy*3;
          for(let y=Math.max(0,Math.floor(cy-ry));y<Math.min(h,Math.ceil(cy+ry));y++)for(let x=Math.max(0,Math.floor(cx-rx));x<Math.min(w,Math.ceil(cx+rx));x++){const d=((x-cx)/sx)**2+((y-cy)/sy)**2;if(d<=9)values[y*w+x]+=c.value*Math.exp(-d/2);}}
        const temp=document.createElement('canvas');temp.width=w;temp.height=h;const tg=temp.getContext('2d'),img=tg.createImageData(w,h);
        for(let i=0;i<values.length;i++){const t=Math.min(1,values[i]/maximum);if(t<.008)continue;const rgb=ramp(t),j=i*4;img.data[j]=rgb[0];img.data[j+1]=rgb[1];img.data[j+2]=rgb[2];img.data[j+3]=Math.round(215*Math.min(1,Math.sqrt(t)));}tg.putImageData(img,0,0);g.imageSmoothingEnabled=true;g.drawImage(temp,0,0,width,height);
  }
  function install(L){
    return L.Layer.extend({initialize(options={}){this.options=options;this.data=null;},
      onAdd(map){this._map=map;this.canvas=L.DomUtil.create('canvas','mission-heat-canvas');this.canvas.setAttribute('aria-hidden','true');this.canvas.style.pointerEvents='none';map.getPane('overlayPane').append(this.canvas);map.on('moveend zoomend resize',this.redraw,this);this.redraw();},
      onRemove(map){map.off('moveend zoomend resize',this.redraw,this);this.canvas.remove();this._map=null;},
      setData(data){this.data=data;if(this._map)this.redraw();return this;},
      redraw(){if(!this._map||!this.canvas)return;const m=this._map,size=m.getSize();this.canvas.width=size.x;this.canvas.height=size.y;L.DomUtil.setPosition(this.canvas,m.containerPointToLayerPoint([0,0]));const g=this.canvas.getContext('2d');g.clearRect(0,0,size.x,size.y);if(this.data){this.canvas.dataset.date=this.data.date;this.canvas.dataset.scope=this.data.scope;this.canvas.dataset.source=this.data.source;this.canvas.dataset.maximum=String(this.data.maximum);}if(!this.data?.weighted.length){this.canvas.dataset.cells='0';return;}
        drawHeat(g,size.x,size.y,this.data,p=>m.latLngToContainerPoint(p));this.canvas.dataset.cells=String(this.data.cells.length);this.canvas.dataset.date=this.data.date;this.canvas.dataset.scope=this.data.scope;this.canvas.dataset.source=this.data.source;this.canvas.dataset.maximum=String(this.data.maximum);
      }
    });
  }
  const api={createIndex,frame,key,concentration,ramp,drawHeat,install,SIGMA_KM};root.FireAtlasMap=api;if(typeof module==='object'&&module.exports)module.exports=api;
})(typeof window==='object'?window:globalThis);
