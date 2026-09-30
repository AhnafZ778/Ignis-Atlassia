/* Render the historical hero from imported archive windows, never from NRT rows. */
document.addEventListener("DOMContentLoaded",()=>{
  const $=id=>document.getElementById(id);
  const timeline=$("archive-timeline"),status=$("archive-status");
  if(!timeline)return;
  const formatNumber=value=>new Intl.NumberFormat("en-US").format(value||0);
  const monthLabel=value=>{
    const [year,month]=value.split("-").map(Number);
    return new Intl.DateTimeFormat("en-US",{month:"short",year:"2-digit",timeZone:"UTC"}).format(new Date(Date.UTC(year,month-1,1)));
  };
  const setText=(id,value)=>{const node=$(id);if(node)node.textContent=value;};
  const showUnavailable=message=>{
    status.textContent="NO VERIFIED ARCHIVE";
    status.className="archive-status is-unavailable";
    timeline.innerHTML=`<div class="archive-empty"><strong>Archive metadata unavailable</strong><span>${message}</span><a href="./data.html">Open data sources ↗</a></div>`;
    setText("archive-scope-label","No verified archive windows are available in this checkout.");
    setText("archive-window-label","No complete windows");
    setText("archive-footprint-label","No imported extent");
    setText("archive-footprint-note","The hero will populate after a non-synthetic regional FIRMS archive is imported.");
    setText("archive-pair-months","—");setText("archive-record-count","—");setText("archive-date-range","—");
  };
  const render=data=>{
    if(!data||!data.timeline?.length){showUnavailable("A clean checkout does not assume a local database or credentials.");return;}
    const months=data.timeline;
    status.textContent=data.status==="verified-pair-windows"?"VERIFIED PAIR":"PARTIAL WINDOWS";
    status.className=`archive-status ${data.status==="verified-pair-windows"?"is-ready":"is-partial"}`;
    const monthGrid=document.createElement("div");monthGrid.className="archive-month-grid";monthGrid.style.setProperty("--archive-months",months.length);
    months.forEach((item,index)=>{
      const mark=document.createElement("span");mark.className="archive-month-mark";mark.textContent=index%3===0?monthLabel(item.month):"";mark.title=item.month;monthGrid.append(mark);
    });
    const rows=[
      ["MODIS","modis","modis-row"],["VIIRS S-NPP","viirs_snpp","viirs-row"]
    ];
    const fragment=document.createDocumentFragment();
    const legend=document.createElement("div");legend.className="archive-timeline-legend";legend.innerHTML='<span><i class="archive-dot modis"></i> MODIS · Terra + Aqua</span><span><i class="archive-dot viirs"></i> VIIRS · Suomi NPP</span><span><i class="archive-dot pair"></i> Paired month</span>';
    fragment.append(legend,monthGrid);
    rows.forEach(([label,key,rowClass])=>{
      const row=document.createElement("div");row.className=`archive-sensor-row ${rowClass}`;
      const name=document.createElement("strong");name.textContent=label;row.append(name);
      const cells=document.createElement("div");cells.className="archive-cell-grid";cells.style.setProperty("--archive-months",months.length);
      months.forEach(item=>{const cell=document.createElement("span");const present=!!item[key];cell.className=`archive-cell ${present?"is-present":"is-missing"}${item.paired?" is-paired":""}`;cell.title=`${label} · ${monthLabel(item.month)} · ${present?"imported":"no complete window"}`;cell.setAttribute("aria-label",cell.title);cells.append(cell);});
      row.append(cells);fragment.append(row);
    });
    timeline.replaceChildren(fragment);
    const first=months[0].month,last=months[months.length-1].month;
    const modis=data.sources.find(item=>item.source_id==="MODIS_SP"),viirs=data.sources.find(item=>item.source_id==="VIIRS_SNPP_SP");
    const total=(modis?.observation_rows||0)+(viirs?.observation_rows||0);
    setText("archive-scope-label",`${data.scope_label} · ${first} → ${last} · records only`);
    setText("archive-window-label",`${data.paired_month_count} paired months`);
    setText("archive-pair-months",formatNumber(data.paired_month_count));
    setText("archive-record-count",formatNumber(total));
    setText("archive-date-range",`${first} → ${last}`);
    if(data.scope_bbox){
      const [west,south,east,north]=data.scope_bbox;
      setText("archive-footprint-label",`${west}° W · ${south}° N to ${east}° W · ${north}° N`);
      setText("archive-footprint-note",`${data.scope_label} · ${data.limitation}`);
    }
  };
  fetch("/api/archive-overview",{headers:{Accept:"application/json"}}).then(response=>{if(!response.ok)throw new Error("Archive endpoint unavailable");return response.json();}).then(render).catch(()=>showUnavailable("The local archive overview could not be read."));
});
