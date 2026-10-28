/* Native mode navigation; changing modes never resets a backup or a conversion. */
export function mountModes(){
 const tabs=[document.getElementById('tab-share'),document.getElementById('tab-backup')];
 const select=tab=>{for(const t of tabs){const chosen=t===tab;t.setAttribute('aria-selected',String(chosen));t.tabIndex=chosen?0:-1;document.getElementById(t.getAttribute('aria-controls')).hidden=!chosen;}};
 for(const [i,tab]of tabs.entries()){
  tab.addEventListener('click',()=>select(tab));
  tab.addEventListener('keydown',event=>{
   const next=event.key==='Home'?0:event.key==='End'?1:['ArrowLeft','ArrowRight'].includes(event.key)?1-i:null;
   if(next===null)return;event.preventDefault();select(tabs[next]);tabs[next].focus();
  });
 }
}
