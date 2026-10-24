const menuButton=document.getElementById("mobile-menu-button");
const sidebar=document.getElementById("primary-sidebar");
const overlay=document.getElementById("sidebar-overlay");
function setMenu(open){
  sidebar?.classList.toggle("is-open",open);
  document.body.classList.toggle("menu-open",open);
  if(overlay)overlay.hidden=!open;
  menuButton?.setAttribute("aria-expanded",String(open));
  menuButton?.setAttribute("aria-label",open?"Cerrar menú principal":"Abrir menú principal");
}
menuButton?.addEventListener("click",()=>setMenu(menuButton.getAttribute("aria-expanded")!=="true"));
overlay?.addEventListener("click",()=>setMenu(false));
sidebar?.querySelectorAll("a").forEach(link=>link.addEventListener("click",()=>setMenu(false)));
document.addEventListener("keydown",event=>{if(event.key==="Escape")setMenu(false)});
window.addEventListener("resize",()=>{if(window.innerWidth>1024)setMenu(false)});
document.getElementById("logout-button")?.addEventListener("click",async(event)=>{const button=event.currentTarget;button.disabled=true;try{await window.VoxTraceAPI.request("/auth/logout",{method:"POST"})}catch(error){}finally{window.location.assign("/login")}})
