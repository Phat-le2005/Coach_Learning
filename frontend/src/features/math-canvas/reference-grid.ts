import * as THREE from "three";

/** Both 3D viewers use the horizontal Oxz floor with mathematical y upright. */
export function createReferenceGrid(domain:number,spatial:boolean){
  const grid=new THREE.GridHelper(2*domain,Math.min(40,Math.max(4,Math.round(2*domain))),0x49617d,0x25384f);
  if(!spatial)grid.rotation.x=Math.PI/2;
  return grid;
}
