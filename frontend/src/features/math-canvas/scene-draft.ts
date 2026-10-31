import type { GraphCamera } from "./expression";
import { compileGraphScene, normalizeRelation, type GraphSceneDocument, type SceneRow } from "./scene";

export interface SceneDraft { rows:SceneRow[]; combine:GraphSceneDocument["combine"]; parameters:Record<string,number>; domain:number; camera:GraphCamera; note:string }
/** Restore only bounded editor data. No cookies, credentials, or source stroke claims are cached. */
export function parseSceneDraft(raw:string|null):SceneDraft|null {
  if(!raw||raw.length>16000)return null;
  try{
    const data=JSON.parse(raw) as SceneDraft;
    if(!Array.isArray(data.rows)||!data.rows.length||data.rows.length>8||!["OVERLAY","AND","OR"].includes(data.combine))return null;
    if(data.rows.some((row)=>!row||typeof row.id!=="string"||!/^[a-zA-Z0-9-]{1,36}$/.test(row.id)||typeof row.expression!=="string"||row.expression.length>500||typeof row.visible!=="boolean"||!/^#[0-9a-fA-F]{6}$/.test(row.color)))return null;
    if(new Set(data.rows.map((row)=>row.id)).size!==data.rows.length)return null;
    if(!data.parameters||Object.keys(data.parameters).length>6||Object.entries(data.parameters).some(([name,value])=>! /^[a-df-w]$/.test(name)||!Number.isFinite(value)||Math.abs(value)>5))return null;
    if(!Number.isFinite(data.domain)||data.domain<1||data.domain>10||typeof data.note!=="string"||data.note.length>1000)return null;
    if(!data.camera||!Array.isArray(data.camera.position)||!Array.isArray(data.camera.target)||data.camera.position.length!==3||data.camera.target.length!==3||[...data.camera.position,...data.camera.target].some((value)=>!Number.isFinite(value)||Math.abs(value)>800))return null;
    const zoom=data.camera.zoom;
    if(data.camera.position[2]!==16||data.camera.target[2]!==0||typeof zoom!=="number"||!Number.isFinite(zoom)||zoom<.1||zoom>20)return null;
    return data;
  }catch{return null;}
}
export function appendSceneRow(rows:SceneRow[], row:SceneRow):SceneRow[]|null {
  const empty=rows.findIndex((item)=>!item.expression.trim());
  if(empty>=0)return rows.map((item,index)=>index===empty?row:item);
  return rows.length<8?[...rows,row]:null;
}

/** Reopening a selection reuses its formula; retrying OCR updates its original row. */
export function importSceneFormula(rows:SceneRow[], row:SceneRow, sourceRowId:string|null=null):{rows:SceneRow[];sourceRowId:string}|null {
  const source=rows.find((item)=>item.id===sourceRowId);
  if(source)return {rows:rows.map((item)=>item.id===source.id?{...item,expression:row.expression}:item),sourceRowId:source.id};
  const key=(expression:string)=>{
    try{
      const compiled=compileGraphScene({version:2,dimension:"2D",combine:"OVERLAY",rows:[{...row,expression}]});
      const layer=compiled.layers[0];
      return layer?JSON.stringify({definition:layer.definition,relations:layer.relations}):normalizeRelation(expression);
    }catch{return expression.trim();}
  };
  const existing=rows.find((item)=>key(item.expression)===key(row.expression));
  if(existing)return {rows,sourceRowId:existing.id};
  const next=appendSceneRow(rows,row);
  return next?{rows:next,sourceRowId:row.id}:null;
}
