/* Real static aliases preserve the full public selection and meaningful fragment. */
(() => {const p=new URLSearchParams(location.search),target=new URL(document.querySelector('meta[name="fireatlas-canonical"]').content,document.baseURI);for(const [k,v]of p)target.searchParams.set(k,v);target.hash=location.hash||target.hash;location.replace(target.href);})();
