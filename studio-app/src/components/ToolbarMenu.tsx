import {useEffect,useRef,type ReactNode} from 'react';
/** Fixed-position menu stays outside the scrolling toolbar, below its toggle. */
export function ToolbarMenu({children}:{children:ReactNode}) {
 const ref=useRef<HTMLDetailsElement>(null);
 const position=()=>{const menu=ref.current;if(!menu?.open)return;const summary=menu.querySelector('summary');if(summary)menu.style.setProperty('--whiteboard-menu-top',`${summary.getBoundingClientRect().bottom+8}px`);};
 useEffect(()=>{
  const menu=ref.current,bar=menu?.closest('.whiteboard-bar');
  const observer=typeof ResizeObserver==='undefined'?null:new ResizeObserver(position);
  if(bar)observer?.observe(bar);
  window.addEventListener('resize',position);window.addEventListener('scroll',position,true);
  return()=>{observer?.disconnect();window.removeEventListener('resize',position);window.removeEventListener('scroll',position,true);};
 },[]);
 return <details ref={ref} className="whiteboard-more" onToggle={position}><summary>More</summary><div>{children}</div></details>;
}
