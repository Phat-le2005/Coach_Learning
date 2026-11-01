import type { MathNode } from "./expression";
import type { SceneLayer } from "./scene";

function hasPlaneCoordinate(node:MathNode):boolean{
  if(node.kind==="variable")return node.name==="y"||node.name==="z";
  if(node.kind==="binary")return hasPlaneCoordinate(node.left)||hasPlaneCoordinate(node.right);
  if(node.kind==="guard")return hasPlaneCoordinate(node.argument)||hasPlaneCoordinate(node.node);
  return node.kind==="unary"||node.kind==="call"?hasPlaneCoordinate(node.node):false;
}

/** Match both y=f(x) and f(x)=y, retaining domain guards and named-function ASTs. */
export function explicitSceneCurve(layer:SceneLayer):MathNode|null{
  if(layer.relations.length!==1||layer.relations[0].operator!=="=")return null;
  const {left,right}=layer.relations[0];
  if(left.kind==="variable"&&left.name==="y"&&!hasPlaneCoordinate(right))return right;
  if(right.kind==="variable"&&right.name==="y"&&!hasPlaneCoordinate(left))return left;
  return null;
}
