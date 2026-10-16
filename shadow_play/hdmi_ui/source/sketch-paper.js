/* Keep the drawing's physical paper aspect independent of panel dimensions. */
(() => {
  'use strict';
  const finite=v=>typeof v==='number'&&Number.isFinite(v);
  const positive=v=>finite(v)&&v>0;
  const clamp=v=>finite(v)?Math.max(0,Math.min(1,v)):v===Infinity?1:0;
  function fit(width,height,aspect) {
    if(!positive(width)||!positive(height))return{x:0,y:0,width:0,height:0};
    if(!positive(aspect))return{x:0,y:0,width,height};
    const w=Math.min(width,height*aspect),h=Math.min(height,width/aspect);
    return{x:(width-w)/2,y:(height-h)/2,width:w,height:h};
  }
  function pointFromDisplay(px,py,rect) {
    if(!positive(rect?.width)||!positive(rect?.height))return[0,0];
    const x=finite(rect.x)?rect.x:0,y=finite(rect.y)?rect.y:0;
    return[clamp(finite(px)?(px-x)/rect.width:0),clamp(finite(py)?(py-y)/rect.height:0)];
  }
  function displayPoint(nx,ny,rect) {
    const x=finite(rect?.x)?rect.x:0,y=finite(rect?.y)?rect.y:0;
    return[x+clamp(nx)*(positive(rect?.width)?rect.width:0),y+clamp(ny)*(positive(rect?.height)?rect.height:0)];
  }
  globalThis.ShadowSketchPaper=Object.freeze({fit,pointFromDisplay,displayPoint});
})();
