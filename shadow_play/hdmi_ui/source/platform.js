/* Deployment-only local persistence. No chat host, training API, or network. */
(() => {
  const key='shadow-theatre-hdmi-state-v1';
  let snapshot=null;
  try{snapshot=JSON.parse(localStorage.getItem(key)||'null');}catch{}
  if(snapshot?.privateContent){snapshot.privateContent.page='home';snapshot.privateContent.menuOpen=false;}
  globalThis.openai={widgetState:snapshot,async setWidgetState(value){
    const json=JSON.stringify(value);
    if(new TextEncoder().encode(json).length>16384)throw new Error('UI state exceeds 16 KiB');
    localStorage.setItem(key,json);this.widgetState=value;
  }};
})();
