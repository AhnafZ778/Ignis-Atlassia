export function heatMapProjection(bounds:number[]) {
  const [west,south,east,north]=bounds;
  if(bounds.length!==4 || !bounds.every(Number.isFinite) || east<=west || north<=south)throw Error('The saved map has invalid bounds.');
  const ratio=(east-west)*Math.cos((south+north)*Math.PI/360)/(north-south);
  const width=Math.min(564,323*ratio),height=Math.min(323,564/ratio);
  const x=52+(564-width)/2,y=122+(323-height)/2;
  return {x,y,width,height,project:(lon:number,lat:number)=>[x+(lon-west)/(east-west)*width,y+(north-lat)/(north-south)*height] as const};
}

export function heatMapLabels(bounds:number[], points:{longitude:number;latitude:number}[]) {
  const frame=heatMapProjection(bounds);
  const [west,south,east,north]=bounds;
  const labels:{x:number;y:number;text:string}[]=[];
  for(const {longitude,latitude} of points){
    if(!Number.isFinite(longitude) || !Number.isFinite(latitude) || longitude<west || longitude>east || latitude<south || latitude>north)continue;
    const [x,y]=frame.project(longitude,latitude);
    if(labels.some(label=>Math.abs(label.x-x)<135 && Math.abs(label.y-y)<34))continue;
    labels.push({x,y,text:latitude.toFixed(3)+'°, '+longitude.toFixed(3)+'°'});
    if(labels.length===6)break;
  }
  return labels;
}
