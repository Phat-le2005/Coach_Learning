import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { avatarSeed } from "./classroom-model";
import { BAG_COLORS, type DeskStyle } from "./classroom-personalization";

interface Resources {
  geometry<T extends THREE.BufferGeometry>(value: T): T;
  material<T extends THREE.Material>(value: T): T;
  color(value: number): THREE.MeshStandardMaterial;
}

export interface PupilRig {
  body: THREE.Group;
  head: THREE.Group;
  left: THREE.Group;
  right: THREE.Group;
  eyes: THREE.Mesh[];
  smile: THREE.Mesh;
  happyMouth: THREE.Mesh;
  glasses: THREE.Group;
}

export interface DeskAccessories {
  bagMaterial: THREE.MeshStandardMaterial;
  plant: THREE.Group;
  star: THREE.Group;
}

export interface MamRig { body: THREE.Group; head: THREE.Group; right: THREE.Group; leaves: THREE.Group; eyes: THREE.Mesh[] }

export function createCozyModels(resources: Resources) {
  const { geometry, material, color } = resources;
  const sphere = geometry(new THREE.SphereGeometry(1, 24, 16));
  const rounded = geometry(new RoundedBoxGeometry(1, 1, 1, 3, .15));
  const cylinder = geometry(new THREE.CylinderGeometry(1, 1, 1, 16));
  const cap = geometry(new THREE.SphereGeometry(1, 24, 16, 0, Math.PI * 2, 0, 1.55));
  const smileShape = geometry(new THREE.TorusGeometry(.083, .013, 6, 16, Math.PI));
  const glassesShape = geometry(new THREE.TorusGeometry(.12, .016, 6, 20));
  const starPath = new THREE.Shape();
  for (let point = 0; point < 10; point++) {
    const angle = Math.PI / 2 + point * Math.PI / 5;
    const radius = point % 2 ? .45 : 1;
    const x = Math.cos(angle) * radius, y = Math.sin(angle) * radius;
    if (point === 0) starPath.moveTo(x, y); else starPath.lineTo(x, y);
  }
  starPath.closePath();
  const starShape = geometry(new THREE.ExtrudeGeometry(starPath, { depth: .18, bevelEnabled: true, bevelSize: .045, bevelThickness: .045, bevelSegments: 2, steps: 1 }));

  function mesh(parent: THREE.Object3D, shape: THREE.BufferGeometry, tint: number, x: number, y: number, z: number, sx: number, sy = sx, sz = sx) {
    const object = new THREE.Mesh(shape, color(tint));
    object.position.set(x, y, z); object.scale.set(sx, sy, sz);
    object.castShadow = true; object.receiveShadow = true; parent.add(object);
    return object;
  }
  function ball(parent: THREE.Object3D, tint: number, x: number, y: number, z: number, sx: number, sy = sx, sz = sx) { return mesh(parent, sphere, tint, x, y, z, sx, sy, sz); }
  function box(parent: THREE.Object3D, tint: number, x: number, y: number, z: number, sx: number, sy: number, sz: number) { return mesh(parent, rounded, tint, x, y, z, sx, sy, sz); }

  // Batch fixed pieces within each movable body part; the rig still animates
  // head, shoulders, eyelids and accessories without a mesh per fingertip.
  function batch(group: THREE.Group) {
    group.updateWorldMatrix(true, true);
    const inverse = group.matrixWorld.clone().invert();
    const pieces = new Map<THREE.Material, THREE.BufferGeometry[]>();
    group.traverse((node) => {
      if (!(node instanceof THREE.Mesh) || Array.isArray(node.material)) return;
      const clone = node.geometry.clone().applyMatrix4(inverse.clone().multiply(node.matrixWorld));
      const normalized = clone.index ? clone.toNonIndexed() : clone;
      if (normalized !== clone) clone.dispose();
      const list = pieces.get(node.material) ?? []; list.push(normalized); pieces.set(node.material, list);
    });
    group.clear();
    for (const [surface, list] of pieces) {
      const merged = mergeGeometries(list, false); list.forEach((part) => part.dispose());
      if (!merged) throw new Error("Cannot batch a cozy classroom model");
      const object = new THREE.Mesh(geometry(merged), surface); object.castShadow = true; object.receiveShadow = true; group.add(object);
    }
  }

  function pupil(parent: THREE.Object3D, studentId: string, x: number, z: number, offline: boolean): PupilRig {
    const seed = avatarSeed(studentId);
    const skin = [0xf3c49d, 0xffd3ad, 0xdeac83, 0xffceac][seed % 4];
    const hair = [0x45312d, 0x593c32, 0x302b35, 0x694733][Math.floor(seed / 3) % 4];
    const cloth = offline ? 0xa5b2ad : [0x94c4aa, 0xbbaee0, 0xeac0a2, 0xa4c7df][Math.floor(seed / 7) % 4];
    const body = new THREE.Group(); body.position.set(x, .02, z); parent.add(body);
    const uniform = new THREE.Group(); body.add(uniform);
    box(uniform, cloth, 0, .85, 0, .64, .69, .46);
    for (const dx of [-.16, .16]) {
      box(uniform, 0x617987, dx, .5, .16, .25, .24, .49);
      box(uniform, 0x617987, dx, .3, .37, .2, .43, .2);
      box(uniform, 0xf0eadd, dx, .115, .47, .27, .18, .4);
      box(uniform, 0x6c7e7a, dx, .07, .49, .28, .065, .41);
      box(uniform, 0xfff9e9, dx, 1.13, .235, .22, .085, .08).rotation.z = dx < 0 ? -.35 : .35;
    }
    box(uniform, 0xe3b579, 0, 1.025, .25, .065, .18, .055);
    ball(uniform, 0x4e8c68, -.15, .91, .244, .028, .04, .012);
    batch(uniform);

    const head = new THREE.Group(); head.position.set(0, 1.52, 0); body.add(head);
    const features = new THREE.Group(); head.add(features);
    ball(features, skin, 0, -.01, 0, .525, .505, .465);
    for (const side of [-1, 1]) {
      ball(features, skin, side * .52, -.045, 0, .09, .115, .075);
      ball(features, 0xe5a78e, side * .55, -.045, .04, .035, .06, .025);
      ball(features, 0xeca997, side * .27, -.14, .395, .085, .042, .016);
    }
    mesh(features, cap, hair, 0, .075, -.025, .545, .475, .48);
    const style = seed % 4;
    if (style === 0) {
      for (let index = 0; index < 4; index++) ball(features, hair, -.29 + index * .18, .28 + Math.sin(index) * .025, .35, .16, .15, .17).rotation.z = -.18;
      ball(features, hair, -.1, .39, .24, .24, .12, .2).rotation.z = -.18;
    } else {
      for (let index = 0; index < 3; index++) ball(features, hair, -.27 + index * .24, .25 - index * .02, .36, .19, .15, .16);
      if (style === 1) for (const side of [-1, 1]) {
        ball(features, hair, side * .43, -.15, -.015, .17, .29, .25);
        ball(features, 0xc7b2dd, side * .45, -.23, .09, .055, .055, .035);
      }
      if (style === 2) for (const side of [-1, 1]) {
        ball(features, hair, side * .44, .22, -.1, .18, .19, .18);
        ball(features, 0xe4b387, side * .45, .06, .02, .065, .04, .05);
      }
      if (style === 3) ball(features, hair, .02, .38, -.37, .24, .23, .19);
    }
    for (const dx of [-.17, .17]) {
      box(features, hair, dx, .1, .448, .1, .022, .019).rotation.z = dx < 0 ? .08 : -.08;
      ball(features, 0xfff9ed, dx - .012, -.023, .487, .012);
    }
    batch(features);
    const eyes = [-.17, .17].map((dx) => ball(head, 0x362e31, dx, -.052, .46, .047, .069, .031));
    const smile = new THREE.Mesh(smileShape, color(0x985e4e)); smile.position.set(0, -.115, .472); smile.rotation.z = Math.PI; head.add(smile);
    const happyMouth = ball(head, 0x965e50, 0, -.13, .472, .065, .07, .018); happyMouth.visible = false;
    const glasses = new THREE.Group(); head.add(glasses);
    for (const dx of [-.17, .17]) mesh(glasses, glassesShape, 0x536167, dx, -.052, .496, 1, 1, 1);
    box(glasses, 0x536167, 0, -.052, .499, .11, .02, .02);
    for (const dx of [-.31, .31]) box(glasses, 0x536167, dx, -.035, .405, .04, .024, .17);
    batch(glasses);

    function arm(side: number) {
      const shoulder = new THREE.Group(); shoulder.position.set(side * .34, 1.12, 0); body.add(shoulder);
      ball(shoulder, cloth, 0, -.15, .02, .13, .23, .13);
      ball(shoulder, skin, 0, -.4, .06, .095, .17, .095);
      ball(shoulder, skin, 0, -.6, .06, .12, .12, .065);
      for (const dx of [-.065, 0, .065]) ball(shoulder, skin, dx, -.69, .06, .029, .065, .03);
      batch(shoulder);
      shoulder.rotation.set(-1.42, 0, side * .15);
      return shoulder;
    }
    return { body, head, left: arm(-1), right: arm(1), eyes, smile, happyMouth, glasses };
  }

  function accessories(parent: THREE.Object3D, x: number, z: number): DeskAccessories {
    const props = new THREE.Group(); props.position.set(x, 0, z); parent.add(props);
    const bagMaterial = material(new THREE.MeshStandardMaterial({ color: BAG_COLORS.mint.color, roughness: .72 }));
    const bag = new THREE.Mesh(rounded, bagMaterial); bag.position.set(.78, .48, -.27); bag.scale.set(.43, .58, .27); bag.castShadow = true; props.add(bag);
    box(props, 0xfff5df, .78, .39, -.113, .3, .2, .05);
    box(props, 0x719287, .78, .53, -.08, .27, .025, .025);
    const handle = new THREE.Mesh(glassesShape, color(0x719287)); handle.position.set(.78, .78, -.27); handle.scale.set(.72, .62, .72); props.add(handle);
    const plant = new THREE.Group(); plant.position.set(.67, 1.06, .55); props.add(plant);
    mesh(plant, cylinder, 0xf5ead9, 0, .075, 0, .095, .15, .095);
    box(plant, 0x4c8765, 0, .23, 0, .025, .24, .025);
    ball(plant, 0x8dbb83, -.06, .27, 0, .065, .13, .035).rotation.z = .6;
    ball(plant, 0x70a77a, .06, .31, 0, .065, .13, .035).rotation.z = -.6;
    batch(plant);
    const star = new THREE.Group(); star.position.set(.67, 1.06, .55); props.add(star);
    mesh(star, cylinder, 0xd8c8aa, 0, .035, 0, .1, .06, .1);
    box(star, 0xba9f6d, 0, .15, 0, .025, .24, .025);
    mesh(star, starShape, 0xf2cc75, 0, .31, .01, .15, .15, .15);
    batch(star);
    return { bagMaterial, plant, star };
  }

  function applyStyle(rig: PupilRig, props: DeskAccessories, style: DeskStyle) {
    rig.glasses.visible = style.glasses;
    props.bagMaterial.color.setHex(BAG_COLORS[style.bagColor].color);
    props.plant.visible = style.decoration === "plant";
    props.star.visible = style.decoration === "star";
  }

  function mam(parent: THREE.Object3D): MamRig {
    const body = new THREE.Group(); body.position.set(0, .05, 3.6); parent.add(body);
    const torso = new THREE.Group(); body.add(torso);
    ball(torso, 0x96cda5, 0, .53, 0, .38, .46, .29);
    ball(torso, 0xe9edc8, 0, .4, .285, .24, .23, .024);
    for (const side of [-1, 1]) box(torso, 0x6a9f7b, side * .19, .09, .08, .18, .13, .25);
    batch(torso);
    const head = new THREE.Group(); head.position.set(0, .79, .04); body.add(head);
    const features = new THREE.Group(); head.add(features);
    for (const side of [-1, 1]) ball(features, 0xe4ad98, side * .25, -.09, .24, .06, .03, .015);
    batch(features);
    const eyes = [-.14, .14].map((x) => ball(head, 0x2d523d, x, 0, .25, .034, .049, .021));
    const mouth = new THREE.Mesh(smileShape, color(0x4b795a)); mouth.position.set(0, -.1, .262); mouth.rotation.z = Math.PI; mouth.scale.setScalar(.7); head.add(mouth);
    const leaves = new THREE.Group(); leaves.position.set(0, .96, 0); body.add(leaves);
    box(leaves, 0x548760, 0, .13, 0, .04, .3, .04).rotation.z = -.2;
    ball(leaves, 0x73aa78, -.13, .26, 0, .2, .1, .055).rotation.z = -.4;
    ball(leaves, 0x98c67d, .14, .33, 0, .23, .11, .06).rotation.z = .45;
    const left = ball(body, 0x86bc97, -.39, .49, .01, .13, .26, .11); left.rotation.z = .75;
    const right = new THREE.Group(); right.position.set(.32, .65, 0); body.add(right);
    ball(right, 0x86bc97, .09, .08, .02, .12, .25, .1).rotation.z = -.6;
    return { body, head, right, leaves, eyes };
  }

  return { pupil, accessories, applyStyle, mam, roundedGeometry: rounded };
}
