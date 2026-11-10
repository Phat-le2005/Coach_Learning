import React from 'react';
import {AbsoluteFill, Composition, registerRoot} from 'remotion';
const Card = () => <AbsoluteFill style={{background:'#edf5ef',color:'#173c2b',justifyContent:'center',alignItems:'center',fontFamily:'Arial',fontSize:60}}>Kiểm tra bộ dựng — 1920 × 1080</AbsoluteFill>;
const Root = () => <Composition id="ToolchainCheck" component={Card} width={1920} height={1080} fps={30} durationInFrames={30}/>;
registerRoot(Root);
