import React from 'react';
import {AbsoluteFill,Sequence,Freeze,Img,interpolate,Easing,staticFile,useCurrentFrame,useVideoConfig} from 'remotion';
import {Video,Audio} from '@remotion/media';
import manifest from './manifest.json';
import captions from '../public/captions.json';

type Shot=typeof manifest[number];
const ink='#073e32',green='#00ae7c';
const font='"Be Vietnam Pro",sans-serif';
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const FontStyles=()=> <style>{`@font-face{font-family:'Be Vietnam Pro';src:url('${staticFile('fonts/BeVietnamPro-Regular.woff2')}')}@font-face{font-family:'Be Vietnam Pro';src:url('${staticFile('fonts/BeVietnamPro-SemiBold.woff2')}');font-weight:600}@font-face{font-family:'Be Vietnam Pro';src:url('${staticFile('fonts/BeVietnamPro-Bold.woff2')}');font-weight:700}`}</style>;

const Media:React.FC<{shot:Shot}>=({shot})=>{
  const {fps}=useVideoConfig();
  const available=Math.max(.1,shot.sourceDuration-shot.trim);
  const playFrames=Math.min(Math.round(shot.duration*fps),Math.max(1,Math.floor(available*fps/shot.rate)-1));
  const hold=Math.round(shot.duration*fps)-playFrames;
  return <>
    <Sequence name={`${shot.id} recording`} durationInFrames={playFrames}>
      <Video src={staticFile(shot.file)} trimBefore={Math.round(shot.trim*fps)} playbackRate={shot.rate} muted objectFit="contain" style={{width:'100%',height:'100%'}}/>
    </Sequence>
    {hold>0?<Sequence name={`${shot.id} result hold`} from={playFrames} durationInFrames={hold}>
      <Freeze frame={Math.max(0,Math.floor((shot.sourceDuration-.09)*fps))}>
        <Video src={staticFile(shot.file)} muted objectFit="contain" style={{width:'100%',height:'100%'}}/>
      </Freeze>
    </Sequence>:null}
  </>;
};

const Camera:React.FC<{shot:Shot}>=({shot})=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig();
  return <AbsoluteFill style={{overflow:'hidden',background:'#f5faf7'}}>
    <AbsoluteFill style={{scale:interpolate(frame,[0,1.6*fps,(shot.duration-1.6)*fps,shot.duration*fps],[1,shot.zoom,shot.zoom,1],{...clamp,easing:Easing.inOut(Easing.cubic)}),transformOrigin:shot.focus}}>
      <Media shot={shot}/>
    </AbsoluteFill>
  </AbsoluteFill>;
};

const Chapter:React.FC<{text:string}>=({text})=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig();
  return <div style={{position:'absolute',left:38,bottom:25,display:'flex',alignItems:'center',gap:10,color:'#fff',padding:'9px 16px',borderRadius:9,background:'rgba(5,51,40,.88)',fontSize:16,fontWeight:600,letterSpacing:1.1,opacity:interpolate(frame,[0,.3*fps],[0,1],clamp)}}><span style={{width:7,height:7,borderRadius:7,background:'#55e6af'}}/>{text}</div>;
};

const Note:React.FC<{text:string}>=({text})=><div style={{position:'absolute',top:86,right:30,padding:'10px 16px',borderRadius:10,fontSize:17,fontWeight:600,color:ink,background:'rgba(239,255,247,.96)',boxShadow:'0 3px 20px #00201418',border:'1px solid #bde7d5'}}>{text}</div>;

const MobileInset:React.FC<{rate:number}>=({rate})=><div style={{position:'absolute',right:28,top:166,width:250,height:577,borderRadius:18,overflow:'hidden',border:'4px solid #f3fff8',boxShadow:'0 10px 45px #00291d40',background:'#fff'}}>
  <div style={{height:34,display:'flex',alignItems:'center',padding:'0 12px',fontSize:14,fontWeight:600,color:'#fff',background:ink}}>Bảng viết · Đồng bộ trực tiếp</div>
  <Video src={staticFile('footage/mobile.mp4')} playbackRate={rate} muted objectFit="contain" style={{width:250,height:541,background:'#fff'}}/>
</div>;

const CaptionLayer=()=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),ms=frame/fps*1000;
  const entry=(captions as {startMs:number;endMs:number;text:string}[]).find(c=>ms>=c.startMs&&ms<c.endMs);
  if(!entry)return null;
  return <div style={{position:'absolute',left:100,right:100,bottom:82,display:'flex',justifyContent:'center'}}>
    <div style={{maxWidth:1620,padding:'12px 24px 14px',borderRadius:12,background:'rgba(3,31,25,.92)',color:'#fff',fontSize:33,fontWeight:600,lineHeight:1.48,textAlign:'center',textShadow:'0 1px 3px #0006',boxShadow:'0 4px 22px #0002'}}>{entry.text}</div>
  </div>;
};

const Intro=()=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig();
  return <AbsoluteFill style={{background:ink}}>
    <AbsoluteFill style={{scale:interpolate(frame,[0,8*fps],[1.02,1.06],clamp),opacity:.22}}><Img src={staticFile('stills/feedback.png')} style={{width:'100%',height:'100%',objectFit:'cover',filter:'blur(1.5px)'}}/></AbsoluteFill>
    <AbsoluteFill style={{background:'linear-gradient(90deg,rgba(0,32,23,.92),rgba(0,45,33,.45))'}}/>
    <div style={{position:'absolute',left:112,top:100,color:'#93e8c4',fontSize:25,fontWeight:600,letterSpacing:1.6}}>MATHMATE</div>
    <div style={{position:'absolute',left:112,top:330,color:'#fff',fontWeight:700,fontSize:86,lineHeight:1.25,letterSpacing:-2,opacity:interpolate(frame,[0,.5*fps],[0,1],clamp),translate:`0 ${interpolate(frame,[0,.7*fps],[22,0],clamp)}px`}}>Biết sai ở đâu.<br/><span style={{color:'#a1efd0'}}>Biết học tiếp gì.</span></div>
    <div style={{position:'absolute',left:116,top:603,color:'#dbf6ea',fontSize:29,lineHeight:1.5}}>Một hành trình học toán, từ mục tiêu đến phản hồi.</div>
    <div style={{position:'absolute',left:115,bottom:184,width:100,height:4,borderRadius:4,background:'#5cdfab'}}/>
  </AbsoluteFill>;
};

const Close=()=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig();
  return <AbsoluteFill style={{background:ink,color:'#fff'}}>
    <AbsoluteFill style={{opacity:.11,scale:1.04}}><Img src={staticFile('stills/feedback.png')} style={{width:'100%',height:'100%',objectFit:'cover'}}/></AbsoluteFill>
    <AbsoluteFill style={{background:'linear-gradient(90deg,#003226d9,#003226b0)'}}/>
    <div style={{position:'absolute',left:112,top:300,opacity:interpolate(frame,[0,.6*fps],[0,1],clamp)}}>
      <div style={{fontSize:92,fontWeight:700,letterSpacing:-2}}>MathMate<span style={{color:'#73e4b7'}}>.</span></div>
      <div style={{fontSize:36,lineHeight:1.6,color:'#e7fff3',marginTop:25}}>Học có định hướng.<br/>Làm bài có phản hồi.</div>
      <div style={{display:'flex',gap:14,marginTop:48}}>{['Học sinh','Kiến thức','Giáo viên'].map(t=><div key={t} style={{padding:'10px 20px',borderRadius:99,border:'1px solid #65bb9970',fontSize:20,color:'#c7f3df'}}>{t}</div>)}</div>
    </div>
  </AbsoluteFill>;
};

const Progress=()=>{
  const frame=useCurrentFrame(),{durationInFrames}=useVideoConfig();
  return <div style={{position:'absolute',left:0,top:0,height:4,width:`${frame/durationInFrames*100}%`,background:green}}/>;
};

export const CoachDemo=()=>{
  const {fps}=useVideoConfig();
  return <AbsoluteFill style={{background:'#eff7f2',fontFamily:font}}>
    <FontStyles/>
    <Sequence name="Opening" durationInFrames={8*fps}><Intro/></Sequence>
    {manifest.map(shot=><Sequence key={shot.id} name={shot.label} from={shot.from*fps} durationInFrames={shot.duration*fps} premountFor={Math.round(.4*fps)}>
      <Camera shot={shot}/><Chapter text={shot.label}/>
      {shot.id==='handwriting'?<><MobileInset rate={shot.rate}/><Note text={shot.rate>1.02?'Hai trình duyệt mô phỏng hai thiết bị · Nét viết được phát nhanh':'Hai trình duyệt mô phỏng hai thiết bị'}/></>:null}
      {shot.id==='ocr'?<Sequence durationInFrames={7*fps}><Note text="Đã rút ngắn thời gian xử lý"/></Sequence>:null}
    </Sequence>)}
    <Sequence name="Closing" from={174*fps} durationInFrames={6*fps}><Close/></Sequence>
    <Audio src={staticFile('audio/narration.mp3')} volume={1}/>
    <CaptionLayer/>
    <Progress/>
  </AbsoluteFill>;
};
