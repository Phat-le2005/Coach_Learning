import React from 'react';
import {Composition,registerRoot} from 'remotion';
import {CoachDemo} from './video';

const Root=()=> <Composition id="CoachLearningDemo" component={CoachDemo} width={1920} height={1080} fps={30} durationInFrames={5400}/>;
registerRoot(Root);
