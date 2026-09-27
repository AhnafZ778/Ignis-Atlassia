(() => {
  const button=document.getElementById("install-app"), status=document.getElementById("install-status");
  let promptEvent=null;
  const standalone=()=>matchMedia("(display-mode: standalone)").matches || navigator.standalone===true;
  function update() {
    if(standalone()) {status.textContent="Running as an installed web app.";button.hidden=true;}
    else if(!window.isSecureContext) {status.textContent="Home-screen installation and offline recovery need HTTPS. This address supports the online mobile website only.";button.hidden=true;}
    else {status.textContent=promptEvent?"Ready to install on this device.":"Use your browser’s Install app or Add to Home Screen menu. Availability varies by browser.";button.hidden=!promptEvent;}
  }
  window.addEventListener("beforeinstallprompt",event=>{event.preventDefault();promptEvent=event;update();});
  window.addEventListener("appinstalled",()=>{promptEvent=null;status.textContent="FireAtlas installed. Launch it from your home screen.";button.hidden=true;});
  button.addEventListener("click",async()=>{if(!promptEvent)return;await promptEvent.prompt();await promptEvent.userChoice;promptEvent=null;update();});
  update();
})();
