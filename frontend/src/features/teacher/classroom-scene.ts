import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { classroomActivity, type ClassroomActivity, type ClassroomSeat } from "./classroom-model";
import { CLASSROOM_COLUMNS, classroomSeatPosition, TEACHER_CAMERA } from "./classroom-layout";
import { celebrationProgress, defaultDeskStyle, type ClassroomStyles } from "./classroom-personalization";
import { createCozyModels, type DeskAccessories, type MamRig, type PupilRig } from "./cozy-models";

export interface ClassroomSceneController {
  select(studentId?: string): void;
  setMotion(enabled: boolean): void;
  setCustomizations(styles: ClassroomStyles): void;
  celebrate(): void;
  greetMascot(): void;
  snapshot(): string | null;
  dispose(): void;
}

interface Person extends PupilRig {
  id: string;
  accessories: DeskAccessories;
  ring: THREE.Mesh;
  disk: THREE.Mesh<THREE.CircleGeometry, THREE.MeshBasicMaterial>;
  activity: ClassroomActivity;
  celebratedAt: number;
  selectedAt: number;
}

/** One renderer per mounted classroom. All resources and observers are owned here. */
export function createClassroomScene(
  holder: HTMLDivElement,
  seats: readonly ClassroomSeat[],
  labels: readonly (HTMLButtonElement | null)[],
  onSelect: (studentId: string) => void,
  onUnavailable: () => void,
  onMascot: () => void,
  bubble?: HTMLDivElement | null,
): ClassroomSceneController {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.3;
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.setAttribute("aria-hidden", "true");
  holder.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  const staticRoom = new THREE.Group();
  scene.add(staticRoom);
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  const palette = new Map<number, THREE.MeshStandardMaterial>();
  const people: Person[] = [];
  const targets: THREE.Mesh[] = [];
  const anchors: THREE.Vector3[] = [];
  let disposed = false;
  let unavailable = false;
  let visible = true;
  let motion = true;
  let frame = 0;
  let lastFrame = 0;
  let resizeObserver: ResizeObserver | undefined;
  let intersectionObserver: IntersectionObserver | undefined;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const compact = window.matchMedia("(max-width: 640px)");
  const camera = new THREE.PerspectiveCamera(TEACHER_CAMERA.fov, 1, .1, 100);
  const cameraTarget = new THREE.Vector3(TEACHER_CAMERA.target.x, TEACHER_CAMERA.target.y, TEACHER_CAMERA.target.z);
  const cameraOffset = new THREE.Vector3(TEACHER_CAMERA.position.x, TEACHER_CAMERA.position.y, TEACHER_CAMERA.position.z).sub(cameraTarget);
  const focusCorners = [-3.35, 3.35].flatMap((x) => [.95, 2.15].flatMap((y) => [-7.5, 5.6].map((z) => new THREE.Vector3(x, y, z))));
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const projected = new THREE.Vector3();
  let pointerStart: { x: number; y: number } | null = null;
  let selectedId: string | undefined;
  let hoveredId: string | undefined;
  let mascot: MamRig | null = null;
  let mascotGreeting = -1;
  let customizations: ClassroomStyles = {};

  function geometry<T extends THREE.BufferGeometry>(value: T): T { geometries.add(value); return value; }
  function material<T extends THREE.Material>(value: T): T { materials.add(value); return value; }
  function color(value: number) {
    let result = palette.get(value);
    if (!result) { result = material(new THREE.MeshStandardMaterial({ color: value, roughness: .78 })); palette.set(value, result); }
    return result;
  }

  function schedule() {
    if (!disposed && !unavailable && visible && !document.hidden && !frame) frame = requestAnimationFrame(draw);
  }

  function draw(now: number) {
    frame = 0;
    if (disposed || unavailable || !visible || document.hidden) return;
    const moving = motion && !reducedMotion.matches;
    if (moving && now - lastFrame < 1000 / 30) { schedule(); return; }
    lastFrame = now;
    const t = moving ? now * .001 : 0;
    people.forEach((person, index) => {
      const active = moving && person.activity !== "offline";
      const a = t * 1.7 + index * .9;
      const selected = person.id === selectedId;
      const cheer = active ? celebrationProgress(person.celebratedAt, now) : 0;
      const wave = active && selected && now - person.selectedAt < 1300;
      const desiredYaw = selected ? Math.max(-.42, Math.min(.42, Math.atan2(camera.position.x - person.body.position.x, camera.position.z - person.body.position.z))) : 0;
      person.head.rotation.y += (desiredYaw - person.head.rotation.y) * (moving ? .18 : 1);
      person.head.rotation.x = selected || cheer > 0 ? -.23 : -.08;
      person.head.rotation.z = active ? Math.sin(a) * .028 : 0;
      person.body.position.y = .02 + (active ? Math.sin(a) * .012 : 0);
      person.eyes.forEach((eye) => { eye.scale.y = active && !wave && Math.sin(t * .75 + index * 2) > .997 ? .009 : .069; });
      person.left.rotation.set(-1.42, 0, -.15);
      person.right.rotation.set(-1.42, 0, .15);
      person.happyMouth.visible = cheer > 0 || wave;
      person.smile.visible = !person.happyMouth.visible;
      if (cheer > 0) {
        person.right.rotation.set(0, 0, 2.35 + Math.sin(t * 8 + index) * .1);
        person.left.rotation.set(0, 0, -2.35 + Math.sin(t * 8 + index) * .1);
        person.body.position.y += Math.abs(Math.sin(t * 9 + index)) * .065 * cheer;
      } else if (person.activity === "help") {
        person.right.rotation.set(0, 0, 2.35 + (active ? Math.sin(t * 3 + index) * .12 : 0));
      } else if (wave) {
        person.right.rotation.set(0, 0, 2.1 + Math.sin(t * 9) * .15);
      } else if (person.activity === "studying") {
        person.right.rotation.x = -1.42 + (active ? Math.sin(t * 5 + index) * .07 : 0);
      }
      person.disk.material.opacity = selected ? .24 : person.id === hoveredId ? .13 : .045;
    });
    if (mascot) {
      const greeting = moving && mascotGreeting >= 0 && now - mascotGreeting < 2000;
      mascot.body.position.y = .05 + (moving ? Math.sin(t * 1.8) * .018 : 0);
      mascot.head.rotation.x = -.22;
      mascot.right.rotation.z = greeting ? Math.sin(t * 8) * .25 : 0;
      mascot.leaves.rotation.z = moving ? Math.sin(t * 1.7) * .06 : 0;
      mascot.eyes.forEach((eye) => { eye.scale.y = moving && Math.sin(t * .8) > .998 ? .008 : .049; });
    }
    try { renderer.render(scene, camera); } catch { loseContext(); return; }
    if (moving) schedule();
  }

  function positionLabels(width: number, height: number) {
    if (compact.matches) return;
    for (let column = 0; column < CLASSROOM_COLUMNS; column++) {
      const positions = anchors.flatMap((anchor, index) => {
        const label = labels[index];
        if (!label || index % CLASSROOM_COLUMNS !== column) return [];
        projected.copy(anchor).project(camera);
        return [{ label, x: (projected.x * .5 + .5) * width, y: (-projected.y * .5 + .5) * height }];
      }).sort((left, right) => left.y - right.y);
      let previousBottom = 45;
      for (const position of positions) {
        const halfHeight = position.label.offsetHeight / 2;
        const halfWidth = position.label.offsetWidth / 2;
        const y = Math.max(position.y, previousBottom + halfHeight + 6);
        position.label.style.left = `${Math.max(halfWidth + 8, Math.min(width - halfWidth - 8, position.x))}px`;
        position.label.style.top = `${y}px`;
        previousBottom = y + halfHeight;
      }
    }
    const selected = people.find((person) => person.id === selectedId);
    if (bubble && selected) {
      projected.set(0, 1.5, selected.body.position.z).project(camera);
      bubble.style.left = `${(projected.x * .5 + .5) * width}px`;
      bubble.style.top = `${(-projected.y * .5 + .5) * height}px`;
    }
  }

  function frameCamera(width: number, height: number) {
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    // Frame faces and desktops from the teacher's position. Let the surrounding
    // room extend to the edges instead of shrinking the pupils to fit its floor.
    let distance = 1;
    for (let attempt = 0; attempt < 8; attempt++) {
      camera.position.copy(cameraTarget).addScaledVector(cameraOffset, distance);
      camera.lookAt(cameraTarget);
      camera.updateMatrixWorld(true);
      let overflow = 1;
      for (const corner of focusCorners) {
        projected.copy(corner).project(camera);
        overflow = Math.max(overflow, Math.abs(projected.x) / .94, Math.abs(projected.y) / .92);
      }
      if (overflow <= 1.002) break;
      distance *= overflow * 1.01;
    }
  }

  function resize() {
    const width = holder.clientWidth;
    const height = holder.clientHeight - (compact.matches ? 112 : 0);
    if (disposed || !width || height <= 0) return;
    renderer.setSize(width, height, false);
    renderer.domElement.style.height = `${height}px`;
    frameCamera(width, height);
    positionLabels(width, height);
    schedule();
  }

  function pointerDown(event: PointerEvent) { pointerStart = { x: event.clientX, y: event.clientY }; }
  function pointerUp(event: PointerEvent) {
    if (!pointerStart || Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 10) { pointerStart = null; return; }
    pointerStart = null;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(targets)[0];
    if (typeof hit?.object.userData.studentId === "string") onSelect(hit.object.userData.studentId);
    if (hit?.object.userData.mascot) onMascot();
  }
  function pointerMove(event: PointerEvent) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(targets)[0];
    const next = typeof hit?.object.userData.studentId === "string" ? hit.object.userData.studentId : undefined;
    renderer.domElement.style.cursor = hit ? "pointer" : "default";
    if (next !== hoveredId) { hoveredId = next; schedule(); }
  }
  function pointerCancel() { pointerStart = null; }
  function visibilityChange() { if (!document.hidden) schedule(); }
  function loseContext(event?: Event) {
    event?.preventDefault();
    if (unavailable || disposed) return;
    unavailable = true;
    cancelAnimationFrame(frame); frame = 0;
    onUnavailable();
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    cancelAnimationFrame(frame);
    resizeObserver?.disconnect(); intersectionObserver?.disconnect();
    reducedMotion.removeEventListener("change", schedule);
    compact.removeEventListener("change", resize);
    document.removeEventListener("visibilitychange", visibilityChange);
    renderer.domElement.removeEventListener("pointerdown", pointerDown);
    renderer.domElement.removeEventListener("pointerup", pointerUp);
    renderer.domElement.removeEventListener("pointercancel", pointerCancel);
    renderer.domElement.removeEventListener("pointermove", pointerMove);
    renderer.domElement.removeEventListener("webglcontextlost", loseContext);
    geometries.forEach((item) => item.dispose());
    materials.forEach((item) => item.dispose());
    textures.forEach((item) => item.dispose());
    scene.clear(); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
  }

  try {
    const sphere = geometry(new THREE.SphereGeometry(1, 20, 14));
    const cube = geometry(new THREE.BoxGeometry(1, 1, 1));
    const cylinder = geometry(new THREE.CylinderGeometry(1, 1, 1, 16));
    const ringShape = geometry(new THREE.TorusGeometry(1, .035, 6, 48));
    const circle = geometry(new THREE.CircleGeometry(.85, 32));
    const hitShape = geometry(new THREE.BoxGeometry(1.8, 2.6, 1.9));
    const hitMaterial = material(new THREE.MeshBasicMaterial({ visible: false }));
    const models = createCozyModels({ geometry, material, color });

    function mesh(parent: THREE.Object3D, shape: THREE.BufferGeometry, tint: number, x: number, y: number, z: number, sx: number, sy: number, sz: number) {
      const result = new THREE.Mesh(shape, color(tint));
      result.position.set(x, y, z); result.scale.set(sx, sy, sz);
      result.castShadow = true; result.receiveShadow = true; parent.add(result);
      return result;
    }
    function ball(parent: THREE.Object3D, tint: number, x: number, y: number, z: number, sx: number, sy = sx, sz = sx) { return mesh(parent, sphere, tint, x, y, z, sx, sy, sz); }
    function block(parent: THREE.Object3D, tint: number, x: number, y: number, z: number, sx: number, sy: number, sz: number) { return mesh(parent, cube, tint, x, y, z, sx, sy, sz); }
    function roundBlock(parent: THREE.Object3D, tint: number, x: number, y: number, z: number, sx: number, sy: number, sz: number) { return mesh(parent, models.roundedGeometry, tint, x, y, z, sx, sy, sz); }

    scene.add(new THREE.HemisphereLight(0xfff8e9, 0x9caf9f, 2.1));
    const sun = new THREE.DirectionalLight(0xffefd9, 2.7);
    sun.position.set(-5, 12, 8); sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    Object.assign(sun.shadow.camera, { left: -10, right: 10, top: 10, bottom: -10 });
    sun.shadow.normalBias = .035; sun.shadow.radius = 3; scene.add(sun);

    block(staticRoom, 0xdec9aa, 0, -.28, -1.5, 12.6, .48, 17.3);
    block(staticRoom, 0xf0e4cc, 0, -.01, -1.5, 12.4, .08, 17.1);
    for (let x = -6; x < 6.3; x += .8) block(staticRoom, 0xdccbaf, x, .034, -1.5, .018, .006, 17);
    block(staticRoom, 0xd3e1cc, 0, .046, -1.2, 1.65, .012, 14.6);
    block(staticRoom, 0xe7eddb, 0, 1.55, -10.05, 12.6, 3.2, .2);
    block(staticRoom, 0xb6ceae, 0, .28, -9.9, 12.6, .55, .16);
    block(staticRoom, 0xf1ebd8, -6.2, 1.4, -1.5, .18, 2.9, 17.1);
    block(staticRoom, 0xc3d2b5, -6.05, .26, -1.5, .14, .5, 17.1);
    block(staticRoom, 0xf1ebd8, 6.2, 1.4, -1.5, .18, 2.9, 17.1);
    block(staticRoom, 0xc3d2b5, 6.05, .26, -1.5, .14, .5, 17.1);
    // The teaching board is behind the camera. The rear wall has a small
    // classroom noticeboard instead of putting the pupils' backs to the board.
    block(staticRoom, 0xbaa384, 0, 2.05, -9.89, 5.3, 1.25, .14);
    block(staticRoom, 0xe9e0c8, 0, 2.05, -9.79, 5.1, 1.08, .1);
    const boardCanvas = document.createElement("canvas"); boardCanvas.width = 1024; boardCanvas.height = 210;
    const boardContext = boardCanvas.getContext("2d");
    if (boardContext) {
      boardContext.fillStyle = "#e9e0c8"; boardContext.fillRect(0, 0, 1024, 210);
      boardContext.fillStyle = "#31594e"; boardContext.textAlign = "center"; boardContext.textBaseline = "middle";
      boardContext.font = "600 40px Segoe UI, Arial"; boardContext.fillText("LỚP MÌNH · CÙNG NHAU TIẾN BỘ", 512, 105);
      const boardTexture = new THREE.CanvasTexture(boardCanvas); boardTexture.colorSpace = THREE.SRGBColorSpace; textures.add(boardTexture);
      const board = new THREE.Mesh(geometry(new THREE.PlaneGeometry(4.85, .95)), material(new THREE.MeshBasicMaterial({ map: boardTexture })));
      board.position.set(0, 2.05, -9.72); scene.add(board);
    }
    for (const side of [-1, 1]) for (const z of [-6.5, -2, 2.5]) {
      block(staticRoom, 0xe8f3ec, side * 6.03, 1.85, z, .08, 1.65, 2.5);
      block(staticRoom, 0xadd1ce, side * 5.97, 1.85, z, .05, 1.45, 2.3);
      block(staticRoom, 0xf4efe4, side * 5.92, 1.85, z, .06, 1.5, .07);
      block(staticRoom, 0xf4efe4, side * 5.92, 1.85, z, .06, .07, 2.35);
      for (const edge of [-1, 1]) roundBlock(staticRoom, side < 0 ? 0xd4c7e6 : 0xd7e5d8, side * 5.89, 1.85, z + edge * 1.25, .11, 1.85, .24);
    }
    block(staticRoom, 0xc09d74, 4.55, .5, -9.25, 1.7, 1, 1);
    for (let index = 0; index < 3; index++) block(staticRoom, [0x779f80, 0xe0b777, 0x8eacc0][index], 4.05 + index * .4, 1.14, -9.3, .23, .28, .45);
    const clock = mesh(staticRoom, cylinder, 0xf8f3e5, 4.55, 2.45, -9.89, .45, .12, .45); clock.rotation.x = Math.PI / 2;
    block(staticRoom, 0x526d5f, 4.55, 2.57, -9.79, .035, .25, .035);
    block(staticRoom, 0x526d5f, 4.67, 2.45, -9.79, .25, .035, .035);
    for (const [x, z] of [[-5.3, 5.8], [5.3, -9.1]]) {
      mesh(staticRoom, cylinder, 0xc59b7e, x, .29, z, .31, .5, .31);
      block(staticRoom, 0x74906c, x, .9, z, .07, 1, .07);
      for (let leaf = 0; leaf < 5; leaf++) {
        const angle = leaf * 1.8;
        ball(staticRoom, 0x77a16d, x + Math.sin(angle) * .24, 1 + leaf * .1, z + Math.cos(angle) * .24, .18, .4, .13).rotation.z = Math.sin(angle) * .8;
      }
    }

    seats.forEach((seat, index) => {
      const { x, z, column } = classroomSeatPosition(index);
      const desk = new THREE.Group(); desk.position.set(x, 0, z + .8); staticRoom.add(desk);
      roundBlock(desk, 0xceb08a, 0, .91, 0, 1.85, .13, 1.04);
      roundBlock(desk, 0xe9cda2, 0, .99, 0, 1.91, .1, 1.1);
      for (const dx of [-.73, .73]) for (const dz of [-.36, .36]) block(desk, 0x819c8e, dx, .45, dz, .075, .9, .075);
      const chair = new THREE.Group(); chair.position.set(x, 0, z - .13); staticRoom.add(chair);
      roundBlock(chair, 0x9fb8a1, 0, .48, 0, .73, .12, .68);
      roundBlock(chair, 0x9fb8a1, 0, .87, -.28, .73, .65, .1);
      for (const dx of [-.25, .25]) for (const dz of [-.2, .2]) block(chair, 0x6f8b79, dx, .23, dz, .055, .46, .055);
      anchors.push(new THREE.Vector3(column === 0 ? -4.5 : 4.5, .8, z + .5));
      const student = seat.student;
      if (!student) return;
      block(desk, 0x7d9f87, .12, 1.033, 0, .78, .026, .55);
      block(desk, 0xf9f4df, .12, 1.045, 0, .7, .025, .48);
      block(desk, 0xc2d7c1, .12, 1.061, 0, .015, .008, .46);
      for (let line = 0; line < 3; line++) block(desk, 0xb9c8b5, .18, 1.062, -.12 + line * .1, .24, .006, .012);
      mesh(desk, cylinder, 0xe8b24e, -.48, 1.07, .04, .025, .45, .025).rotation.z = 1.28;
      const activity = classroomActivity(student);
      const rig = models.pupil(scene, student.id, x, z, activity === "offline");
      const accessories = models.accessories(scene, x, z);
      models.applyStyle(rig, accessories, customizations[student.id] ?? defaultDeskStyle(student.id));
      const disk = new THREE.Mesh(circle, material(new THREE.MeshBasicMaterial({ color: 0x82b894, transparent: true, opacity: .07, depthWrite: false })));
      disk.rotation.x = -Math.PI / 2; disk.position.set(x, .045, z); scene.add(disk);
      const ring = new THREE.Mesh(ringShape, material(new THREE.MeshBasicMaterial({ color: 0x2f805b, transparent: true, opacity: .9 })));
      ring.rotation.x = Math.PI / 2; ring.position.set(x, .06, z); ring.scale.setScalar(.85); ring.visible = false; scene.add(ring);
      const hit = new THREE.Mesh(hitShape, hitMaterial); hit.position.set(x, 1.1, z + .35); hit.userData.studentId = student.id;
      scene.add(hit); targets.push(hit);
      people.push({ ...rig, id: student.id, accessories, ring, disk, activity, celebratedAt: activity === "completed" ? performance.now() : -1, selectedAt: -1 });
    });

    mascot = models.mam(scene);
    const mascotHit = new THREE.Mesh(geometry(new THREE.BoxGeometry(.95, 1.55, .9)), hitMaterial);
    mascotHit.position.set(0, .8, 3.6); mascotHit.userData.mascot = true; scene.add(mascotHit); targets.push(mascotHit);

    // Merge the immobile room, desks and chairs by material. Avatars remain
    // independent so hands and heads can animate and seats stay selectable.
    staticRoom.updateMatrixWorld(true);
    const batches = new Map<THREE.Material, THREE.BufferGeometry[]>();
    staticRoom.traverse((object) => {
      if (!(object instanceof THREE.Mesh) || Array.isArray(object.material)) return;
      const parts = batches.get(object.material) ?? [];
      const clone = object.geometry.clone().applyMatrix4(object.matrixWorld);
      const normalized = clone.index ? clone.toNonIndexed() : clone;
      if (normalized !== clone) clone.dispose();
      parts.push(normalized);
      batches.set(object.material, parts);
    });
    for (const [surface, parts] of batches) {
      const merged = mergeGeometries(parts, false);
      parts.forEach((part) => part.dispose());
      if (!merged) throw new Error("Unable to batch classroom geometry");
      const batch = new THREE.Mesh(geometry(merged), surface); batch.castShadow = true; batch.receiveShadow = true; scene.add(batch);
    }
    scene.remove(staticRoom); staticRoom.clear();

    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    renderer.domElement.addEventListener("pointercancel", pointerCancel);
    renderer.domElement.addEventListener("pointermove", pointerMove);
    renderer.domElement.addEventListener("webglcontextlost", loseContext);
    document.addEventListener("visibilitychange", visibilityChange);
    reducedMotion.addEventListener("change", schedule);
    compact.addEventListener("change", resize);
    resizeObserver = new ResizeObserver(resize); resizeObserver.observe(holder);
    intersectionObserver = new IntersectionObserver((entries) => { visible = entries[0].isIntersecting; if (visible) schedule(); });
    intersectionObserver.observe(holder);
    resize();
    return {
      select(studentId) { selectedId = studentId; people.forEach((person) => { person.ring.visible = person.id === studentId; if (person.id === studentId) person.selectedAt = performance.now(); }); positionLabels(holder.clientWidth, renderer.domElement.clientHeight); schedule(); },
      setMotion(enabled) { motion = enabled; schedule(); },
      setCustomizations(styles) { customizations = styles; people.forEach((person) => models.applyStyle(person, person.accessories, styles[person.id] ?? defaultDeskStyle(person.id))); schedule(); },
      celebrate() { const now = performance.now(); people.forEach((person) => { person.celebratedAt = now; }); mascotGreeting = now; schedule(); },
      greetMascot() { mascotGreeting = performance.now(); schedule(); },
      snapshot() {
        if (disposed || unavailable) return null;
        const rings = people.map((person) => ({ ring: person.ring.visible, disk: person.disk.material.opacity }));
        const size = renderer.getSize(new THREE.Vector2());
        const ratio = renderer.getPixelRatio();
        try {
          renderer.setPixelRatio(1); renderer.setSize(1440, 1080, false); frameCamera(1440, 1080);
          people.forEach((person) => { person.ring.visible = false; person.disk.material.opacity = 0; person.eyes.forEach((eye) => { eye.scale.y = .069; }); });
          renderer.render(scene, camera);
          return renderer.domElement.toDataURL("image/png");
        } catch { return null; }
        finally { renderer.setPixelRatio(ratio); renderer.setSize(size.x, size.y, false); frameCamera(size.x, size.y); people.forEach((person, index) => { person.ring.visible = rings[index].ring; person.disk.material.opacity = rings[index].disk; }); schedule(); }
      },
      dispose,
    };
  } catch (error) { dispose(); throw error; }
}
