import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { classroomActivity, type ClassroomActivity, type ClassroomSeat } from "./classroom-model";
import { CLASSROOM_COLUMNS, classroomSeatPosition, classroomWideSeatPosition, TEACHER_CAMERA } from "./classroom-layout";
import { celebrationProgress, defaultDeskStyle, type ClassroomStyles } from "./classroom-personalization";
import { createCozyModels, type DeskAccessories, type MamRig, type PupilRig, type TeacherRig } from "./cozy-models";

export type StationKey = "classes" | "materials" | "theory" | "submissions" | "analytics";
export type StationPhase = "walking" | "interacting" | "ready";

export interface SceneHoverInfo {
  kind: "student" | "prop" | "mascot";
  id: string;
  title: string;
  subtitle: string;
  badge: string;
  x: number;
  y: number;
}

export const SPATIAL_STATIONS: Record<
  StationKey,
  {
    doorEntry: [number, number, number];
    waypoint: [number, number, number];
    lookAt: [number, number, number];
    camPos: [number, number, number];
    camTarget: [number, number, number];
    doorPinPos: [number, number, number];
    propPinPos: [number, number, number];
    classroomDoorApproach: [number, number, number];
    classroomDoorLookAt: [number, number, number];
  }
> = {
  // PHÒNG 1: LỚP HỌC CHÍNH (Trải ngang 5 cột × 2 hàng tràn màn hình 16:9)
  classes: {
    doorEntry: [-0.85, 0, 4.35],
    waypoint: [-0.85, 0, 4.35],
    lookAt: [0, 1.0, -1.0],
    camPos: [0, 5.9, 9.8],
    camTarget: [0, 1.15, -0.25],
    doorPinPos: [0, 2.1, 4.35],
    propPinPos: [0, 2.1, 4.35],
    classroomDoorApproach: [-0.85, 0, 4.35],
    classroomDoorLookAt: [0, 1.0, -1.0],
  },
  // PHÒNG 2: PHÒNG CHẤM BÀI GIÁO VIÊN (Cửa 3: Tường Phải - Hành Lang Trước Lớp)
  submissions: {
    doorEntry: [-5.35, 0, 0.65],
    waypoint: [0, 0, -1.05],
    lookAt: [0, 1.05, 1.2],
    camPos: [0, 3.25, 4.25],
    camTarget: [0, 1.12, -0.2],
    doorPinPos: [9.8, 2.1, 3.35],
    propPinPos: [0, 1.85, -0.15],
    classroomDoorApproach: [8.45, 0, 3.35],
    classroomDoorLookAt: [10.2, 1.25, 3.35],
  },
  // PHÒNG 4: STUDIO SƠ ĐỒ LÝ THUYẾT (Cửa 1: Tường Trái - Hành Lang Trước Lớp)
  theory: {
    doorEntry: [-5.35, 0, 0.65],
    waypoint: [1.55, 0, -1.25],
    lookAt: [0, 1.65, -2.1],
    camPos: [0, 2.75, 4.35],
    camTarget: [0, 1.48, -1.3],
    doorPinPos: [-9.8, 2.1, 3.35],
    propPinPos: [0, 2.5, -2.1],
    classroomDoorApproach: [-8.45, 0, 3.35],
    classroomDoorLookAt: [-10.2, 1.25, 3.35],
  },
  // PHÒNG 3: THƯ VIỆN HỌC LIỆU & ĐỀ THI (Cửa 4: Tường Phải - Sau)
  materials: {
    doorEntry: [-5.35, 0, 0.65],
    waypoint: [0, 0, -1.1],
    lookAt: [0, 1.05, 1.2],
    camPos: [0, 3.3, 4.3],
    camTarget: [0, 1.12, -0.2],
    doorPinPos: [9.8, 2.1, -2.1],
    propPinPos: [0, 1.85, -0.15],
    classroomDoorApproach: [8.45, 0, -2.1],
    classroomDoorLookAt: [10.2, 1.25, -2.1],
  },
  // PHÒNG 5: PHÒNG LAB PHÂN TÍCH MẦM XANH AI (Cửa 2: Tường Trái - Sau)
  analytics: {
    doorEntry: [-5.35, 0, 0.65],
    waypoint: [0, 0, -1.25],
    lookAt: [0, 1.25, 1.2],
    camPos: [0, 3.25, 4.25],
    camTarget: [0, 1.18, -0.2],
    doorPinPos: [-9.8, 2.1, -2.1],
    propPinPos: [0, 2.1, -0.2],
    classroomDoorApproach: [-8.45, 0, -2.1],
    classroomDoorLookAt: [-10.2, 1.25, -2.1],
  },
};

export const STATION_PIN_ORDER: StationKey[] = ["submissions", "theory", "materials", "analytics"];

export interface ClassroomSceneController {
  select(studentId?: string): void;
  setMotion(enabled: boolean): void;
  setCustomizations(styles: ClassroomStyles): void;
  celebrate(): void;
  greetMascot(): void;
  snapshot(): string | null;
  dispose(): void;
  setStation(stationKey: string): void;
  skipStationAnimation(): void;
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
  onStationSelect?: (station: string) => void,
  onStationPhaseChange?: (station: string, phase: StationPhase) => void,
  stationPinElements?: readonly (HTMLElement | null)[],
  onHoverChange?: (hover: SceneHoverInfo | null) => void,
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
  const compact = window.matchMedia("(max-width: 640px)");
  const camera = new THREE.PerspectiveCamera(TEACHER_CAMERA.fov, 1, 0.1, 100);
  const cameraTarget = new THREE.Vector3(0, 1.15, -0.25);
  const cameraOffset = new THREE.Vector3(0, 5.9, 9.8).sub(cameraTarget);
  const overviewCamPos = new THREE.Vector3(0, 5.9, 9.8);
  const overviewCamTarget = cameraTarget.clone();
  const focusCorners = [-8.6, 8.6].flatMap((x) =>
    [0.65, 2.35].flatMap((y) => [-4.2, 4.4].map((z) => new THREE.Vector3(x, y, z))),
  );
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const projected = new THREE.Vector3();
  let pointerStart: { x: number; y: number } | null = null;
  let selectedId: string | undefined;
  let hoveredId: string | undefined;
  let hoveredDoorId: string | undefined;
  let mascot: MamRig | null = null;
  let mascotGreeting = -1;
  let customizations: ClassroomStyles = {};
  let currentStation: StationKey = "classes";
  let visibleRoom: StationKey = "classes";
  let prevRoomForTransition: StationKey = "classes";
  let doorStage: "none" | "walk-to-exit-door" | "open-exit-door" | "walk-from-entry-door" = "none";
  let doorAnimStartTime = 0;
  let activeExitDoorPivot: THREE.Group | null = null;
  let activeExitDoorSign: number = 1;
  let activeEntryDoorPivot: THREE.Group | null = null;
  let activeEntryDoorSign: number = 1;
  const classroomDoorPivots: Partial<Record<StationKey, { pivot: THREE.Group; sign: number; id: string }>> = {};
  const returnDoorPivots: Partial<Record<StationKey, { pivot: THREE.Group; sign: number; id: string }>> = {};
  const allDoors: { id: string; pivot: THREE.Group; sign: number }[] = [];
  let setRoomVisibilityFn: ((activeKey: StationKey) => void) | null = null;
  let stationPhase: StationPhase = "ready";
  let pathQueue: THREE.Vector3[] = [];
  let isWalking = false;
  let walkStartTime = 0;
  let interactionStartTime = 0;
  const openProgress: Record<StationKey, number> = {
    classes: 0,
    submissions: 0,
    theory: 0,
    materials: 0,
    analytics: 0,
  };

  const targetCamPos = overviewCamPos.clone();
  const currentCamLookAt = overviewCamTarget.clone();
  const targetCamLookAt = overviewCamTarget.clone();
  const teacherTargetLookAt = new THREE.Vector3(0, 1.0, -1.5);
  let teacherRig: TeacherRig | null = null;

  // Interactive 3D Station Prop Rigs
  let ledgerCoverPivot: THREE.Group | null = null;
  let ledgerPage1Pivot: THREE.Group | null = null;
  let ledgerPage2Pivot: THREE.Group | null = null;
  let ledgerGlowRing: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial> | null = null;

  let archiveDrawer: THREE.Group | null = null;
  let archiveCoverPivot: THREE.Group | null = null;
  let archivePagePivot: THREE.Group | null = null;
  let archiveGlowRing: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial> | null = null;

  let boardNodesGroup: THREE.Group | null = null;
  let boardGlowRing: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial> | null = null;

  let aiBarsGroup: THREE.Group | null = null;
  let aiOrbitRing: THREE.Mesh | null = null;
  let aiGlowRing: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial> | null = null;

  function geometry<T extends THREE.BufferGeometry>(value: T): T {
    geometries.add(value);
    return value;
  }
  function material<T extends THREE.Material>(value: T): T {
    materials.add(value);
    return value;
  }
  function color(value: number) {
    let result = palette.get(value);
    if (!result) {
      result = material(new THREE.MeshStandardMaterial({ color: value, roughness: 0.78 }));
      palette.set(value, result);
    }
    return result;
  }

  function buildClassroomWalkPath(
    from: THREE.Vector3,
    to: THREE.Vector3,
    isGoingToDoor = false,
  ): THREE.Vector3[] {
    const FRONT_AISLE_Z = 3.65;
    const MID_AISLE_Z = -0.15;
    const SAFE_VERTICAL_GAPS = [-8.15, -4.65, -1.55, 1.55, 4.65, 8.15];

    const getHomeAisleZ = (z: number) => (z >= 0.8 ? FRONT_AISLE_Z : MID_AISLE_Z);
    const nearestVerticalGap = (x: number, targetX: number) => {
      const midX = (x + targetX) * 0.5;
      let best = SAFE_VERTICAL_GAPS[0];
      let bestDist = Infinity;
      for (const gx of SAFE_VERTICAL_GAPS) {
        const d = Math.abs(gx - x) + Math.abs(gx - midX) * 0.5;
        if (d < bestDist) {
          bestDist = d;
          best = gx;
        }
      }
      return best;
    };

    const waypoints: THREE.Vector3[] = [];
    const pushWaypoint = (x: number, z: number) => {
      const prev = waypoints.length > 0 ? waypoints[waypoints.length - 1] : from;
      if (Math.hypot(prev.x - x, prev.z - z) > 0.12) {
        waypoints.push(new THREE.Vector3(x, 0, z));
      }
    };

    if (isGoingToDoor) {
      // Target is one of the 4 side doors at x = ±8.45, z = 1.9 or -2.1
      const sideX = to.x < 0 ? -8.15 : 8.15;
      const startOnSameSideWalkway =
        Math.sign(from.x) === Math.sign(sideX) && Math.abs(from.x) >= 7.55;

      if (!startOnSameSideWalkway) {
        // 1. Step into the safe horizontal corridor (Front Corridor z = 3.65 or Middle Aisle z = -0.15)
        const aisleZ = getHomeAisleZ(from.z);
        if (Math.abs(from.x) >= 7.55) {
          // Starting on opposite side wall walkway -> walk along that side walkway to aisleZ first
          const oppSideX = from.x < 0 ? -8.15 : 8.15;
          pushWaypoint(oppSideX, aisleZ);
        } else {
          pushWaypoint(from.x, aisleZ);
        }
        // 2. Walk horizontally along the safe aisle all the way out to the destination Side Wall Walkway
        pushWaypoint(sideX, aisleZ);
      }

      // 3. Walk straight along the clear Side Wall Walkway (outside all student desks) to the door's Z
      pushWaypoint(sideX, to.z);
      // 4. Step to the door threshold
      pushWaypoint(to.x, to.z);
      return waypoints;
    }

    // Walking to Podium or a Student Desk inside the Main Classroom
    const targetAisleZ = getHomeAisleZ(to.z);

    if (Math.abs(from.x) >= 7.55) {
      // Starting from a Side Door / Side Wall Walkway -> walk along the side wall walkway first!
      const sideX = from.x < 0 ? -8.15 : 8.15;
      pushWaypoint(sideX, from.z);
      pushWaypoint(sideX, targetAisleZ);
      pushWaypoint(to.x, targetAisleZ);
      pushWaypoint(to.x, to.z);
      return waypoints;
    }

    const startAisleZ = getHomeAisleZ(from.z);
    pushWaypoint(from.x, startAisleZ);

    if (Math.abs(startAisleZ - targetAisleZ) > 0.2) {
      // Moving between Row 0 (Front Corridor) and Row 1 (Middle Aisle): use a vertical gap between columns
      const gapX = nearestVerticalGap(from.x, to.x);
      pushWaypoint(gapX, startAisleZ);
      pushWaypoint(gapX, targetAisleZ);
    }

    pushWaypoint(to.x, targetAisleZ);
    pushWaypoint(to.x, to.z);
    return waypoints;
  }

  function schedule() {
    if (!disposed && !unavailable && visible && !document.hidden && !frame) {
      frame = requestAnimationFrame(draw);
    }
  }

  function notifyPhase(station: StationKey, phase: StationPhase) {
    stationPhase = phase;
    onStationPhaseChange?.(station, phase);
  }

  function updateStationProps(t: number, delta: number) {
    // Smoothly damp openProgress for each station (1 when active and interacting/ready, 0 otherwise)
    for (const key of STATION_PIN_ORDER) {
      const shouldOpen = currentStation === key && (stationPhase === "interacting" || stationPhase === "ready");
      if (currentStation === key && stationPhase === "interacting") {
        const elapsed = Math.max(0, performance.now() - interactionStartTime);
        openProgress[key] = Math.min(1, elapsed / 520);
      } else {
        openProgress[key] = THREE.MathUtils.damp(openProgress[key], shouldOpen ? 1 : 0, 6.0, delta);
      }
    }

    // 1. Submissions Station: Emerald Grading Ledger cover & pages flipping open
    const subP = openProgress.submissions;
    if (ledgerCoverPivot && ledgerPage1Pivot && ledgerPage2Pivot) {
      // Smooth ease-out curve for book opening
      const coverEase = 1 - Math.pow(1 - subP, 3);
      ledgerCoverPivot.rotation.z = coverEase * 2.82;
      const p1 = Math.max(0, Math.min(1, (subP - 0.18) / 0.65));
      const p1Ease = 1 - Math.pow(1 - p1, 2.5);
      ledgerPage1Pivot.rotation.z = p1Ease * 2.74;
      ledgerPage1Pivot.position.y = 0.042 + Math.sin(p1Ease * Math.PI) * 0.035;

      const p2 = Math.max(0, Math.min(1, (subP - 0.36) / 0.64));
      const p2Ease = 1 - Math.pow(1 - p2, 2.5);
      ledgerPage2Pivot.rotation.z = p2Ease * 2.68;
      ledgerPage2Pivot.position.y = 0.044 + Math.sin(p2Ease * Math.PI) * 0.04;
    }
    if (ledgerGlowRing) {
      ledgerGlowRing.material.opacity = currentStation === "submissions" ? 0.45 + Math.sin(t * 3.5) * 0.15 : 0.15;
    }

    // 2. Materials Station: Archive Drawer sliding out & Exam Portfolio opening
    const matP = openProgress.materials;
    if (archiveDrawer && archiveCoverPivot && archivePagePivot) {
      const matEase = 1 - Math.pow(1 - matP, 3);
      archiveDrawer.position.z = 0.42 + matEase * 0.38;
      archiveCoverPivot.rotation.z = -matEase * 2.75;
      const pageP = Math.max(0, Math.min(1, (matP - 0.22) / 0.78));
      const pageEase = 1 - Math.pow(1 - pageP, 2.5);
      archivePagePivot.rotation.z = -pageEase * 2.65;
      archivePagePivot.position.y = 0.048 + Math.sin(pageEase * Math.PI) * 0.04;
    }
    if (archiveGlowRing) {
      archiveGlowRing.material.opacity = currentStation === "materials" ? 0.45 + Math.sin(t * 3.5) * 0.15 : 0.15;
    }

    // 3. Theory Station: Smartboard Mindmap nodes popping out & pulsing
    const thP = openProgress.theory;
    if (boardNodesGroup) {
      const thEase = 1 - Math.pow(1 - thP, 3);
      const scale = 0.28 + thEase * 0.72;
      boardNodesGroup.scale.set(scale, scale, 1);
      boardNodesGroup.position.z = 0.12 + thEase * 0.08;
    }
    if (boardGlowRing) {
      boardGlowRing.material.opacity = currentStation === "theory" ? 0.45 + Math.sin(t * 3.5) * 0.15 : 0.15;
    }

    // 4. Analytics Station: AI Hub 3D Hologram Bars & Orbit Ring
    const anP = openProgress.analytics;
    if (aiBarsGroup && aiOrbitRing) {
      const anEase = 1 - Math.pow(1 - anP, 3);
      aiBarsGroup.scale.y = 0.2 + anEase * 0.8 + (anP > 0.8 ? Math.sin(t * 3) * 0.05 : 0);
      aiOrbitRing.rotation.z = t * 1.4;
      aiOrbitRing.rotation.x = Math.PI / 2 + Math.sin(t * 2) * 0.18;
      aiOrbitRing.position.y = 1.28 + anEase * 0.22 + Math.sin(t * 2.5) * 0.04;
    }
    if (aiGlowRing) {
      aiGlowRing.material.opacity = currentStation === "analytics" ? 0.45 + Math.sin(t * 3.5) * 0.15 : 0.15;
    }
  }

  function draw(now: number) {
    frame = 0;
    if (disposed || unavailable || !visible || document.hidden) return;
    const moving = motion;
    const rawDelta = lastFrame > 0 ? (now - lastFrame) * 0.001 : 0.016;
    const delta = Math.min(Math.max(rawDelta, 0.008), 0.08);
    lastFrame = now;

    // 1. Smooth framerate-independent camera damping
    let cameraMoved = false;
    if (moving) {
      const prevDist = camera.position.distanceTo(targetCamPos) + currentCamLookAt.distanceTo(targetCamLookAt);
      if (prevDist > 0.002) {
        camera.position.x = THREE.MathUtils.damp(camera.position.x, targetCamPos.x, 4.5, delta);
        camera.position.y = THREE.MathUtils.damp(camera.position.y, targetCamPos.y, 4.5, delta);
        camera.position.z = THREE.MathUtils.damp(camera.position.z, targetCamPos.z, 4.5, delta);
        currentCamLookAt.x = THREE.MathUtils.damp(currentCamLookAt.x, targetCamLookAt.x, 4.8, delta);
        currentCamLookAt.y = THREE.MathUtils.damp(currentCamLookAt.y, targetCamLookAt.y, 4.8, delta);
        currentCamLookAt.z = THREE.MathUtils.damp(currentCamLookAt.z, targetCamLookAt.z, 4.8, delta);
        camera.lookAt(currentCamLookAt);
        camera.updateMatrixWorld(true);
        cameraMoved = true;
      }
    }

    const t = moving ? now * 0.001 : 0;

    // 2. Pupil animations
    people.forEach((person, index) => {
      const active = moving && person.activity !== "offline";
      const a = t * 1.7 + index * 0.9;
      const selected = person.id === selectedId;
      const cheer = active ? celebrationProgress(person.celebratedAt, now) : 0;
      const wave = active && selected && now - person.selectedAt < 1300;
      const desiredYaw = selected
        ? Math.max(
            -0.42,
            Math.min(
              0.42,
              Math.atan2(camera.position.x - person.body.position.x, camera.position.z - person.body.position.z),
            ),
          )
        : 0;
      person.head.rotation.y += (desiredYaw - person.head.rotation.y) * (moving ? 0.18 : 1);
      person.head.rotation.x = selected || cheer > 0 ? -0.23 : -0.08;
      person.head.rotation.z = active ? Math.sin(a) * 0.028 : 0;
      person.body.position.y = 0.02 + (active ? Math.sin(a) * 0.012 : 0);
      person.eyes.forEach((eye) => {
        eye.scale.y = active && !wave && Math.sin(t * 0.75 + index * 2) > 0.997 ? 0.009 : 0.069;
      });
      person.left.rotation.set(-1.42, 0, -0.15);
      person.right.rotation.set(-1.42, 0, 0.15);
      person.happyMouth.visible = cheer > 0 || wave;
      person.smile.visible = !person.happyMouth.visible;
      if (cheer > 0) {
        person.right.rotation.set(0, 0, 2.35 + Math.sin(t * 8 + index) * 0.1);
        person.left.rotation.set(0, 0, -2.35 + Math.sin(t * 8 + index) * 0.1);
        person.body.position.y += Math.abs(Math.sin(t * 9 + index)) * 0.065 * cheer;
      } else if (person.activity === "help") {
        person.right.rotation.set(0, 0, 2.35 + (active ? Math.sin(t * 3 + index) * 0.12 : 0));
      } else if (wave) {
        person.right.rotation.set(0, 0, 2.1 + Math.sin(t * 9) * 0.15);
      } else if (person.activity === "studying") {
        person.right.rotation.x = -1.42 + (active ? Math.sin(t * 5 + index) * 0.07 : 0);
      }
      person.disk.material.opacity = selected ? 0.24 : person.id === hoveredId ? 0.13 : 0.045;
    });

    // 3. Mầm Xanh Mascot animation
    if (mascot) {
      const greeting = moving && ((mascotGreeting >= 0 && now - mascotGreeting < 2000) || currentStation === "analytics");
      mascot.body.position.y =
        0.05 + (moving ? Math.sin(t * (greeting ? 5.5 : 1.8)) * (greeting ? 0.045 : 0.018) : 0);
      mascot.head.rotation.x = -0.22;
      mascot.right.rotation.z = greeting ? Math.sin(t * 8) * 0.28 : 0;
      mascot.leaves.rotation.z = moving ? Math.sin(t * 1.7) * 0.06 : 0;
      mascot.eyes.forEach((eye) => {
        eye.scale.y = moving && Math.sin(t * 0.8) > 0.998 ? 0.008 : 0.049;
      });
    }

    // 4a. Animate 3D Hinged Doors (Opening on exit, closing behind on entry, cracking open on hover)
    for (const door of allDoors) {
      let targetDoorAngle = 0;
      if (doorStage === "open-exit-door" && door.pivot === activeExitDoorPivot) {
        const p = Math.min(1, Math.max(0, (now - doorAnimStartTime) / 460));
        const ease = 1 - Math.pow(1 - p, 2.5);
        targetDoorAngle = ease * 1.42 * door.sign;
      } else if (doorStage === "walk-from-entry-door" && door.pivot === activeEntryDoorPivot) {
        const elapsedSinceEntry = Math.max(0, now - walkStartTime);
        const closeFactor = Math.max(0, 1 - elapsedSinceEntry / 720);
        targetDoorAngle = closeFactor * 1.38 * door.sign;
      } else if (doorStage === "none" && door.id === hoveredDoorId) {
        targetDoorAngle = 0.24 * door.sign;
      }
      door.pivot.rotation.y = THREE.MathUtils.damp(door.pivot.rotation.y, targetDoorAngle, 9.0, delta);
    }

    // 4b. Teacher Avatar Walking, Door-Opening & Station Interaction State Machine
    if (teacherRig) {
      teacherRig.pointer.visible = visibleRoom === "theory" && !isWalking && doorStage === "none";

      if (moving && doorStage === "open-exit-door") {
        // Stage 2: Teacher stands in front of the Exit Door, reaches out & opens the door
        const faceDir = new THREE.Vector3().subVectors(teacherTargetLookAt, teacherRig.body.position).normalize();
        const targetRotY = Math.atan2(faceDir.x, faceDir.z);
        let angleDiff = targetRotY - teacherRig.body.rotation.y;
        while (angleDiff > Math.PI) angleDiff -= Math.PI * 2;
        while (angleDiff < -Math.PI) angleDiff += Math.PI * 2;
        teacherRig.body.rotation.y += angleDiff * Math.min(1, delta * 12);

        teacherRig.leftLeg.rotation.x = THREE.MathUtils.damp(teacherRig.leftLeg.rotation.x, 0, 8.0, delta);
        teacherRig.rightLeg.rotation.x = THREE.MathUtils.damp(teacherRig.rightLeg.rotation.x, 0, 8.0, delta);
        teacherRig.rightArm.rotation.x = THREE.MathUtils.damp(teacherRig.rightArm.rotation.x, -1.25, 10.0, delta);
        teacherRig.leftArm.rotation.x = THREE.MathUtils.damp(teacherRig.leftArm.rotation.x, -0.35, 8.0, delta);

        if (now - doorAnimStartTime >= 460) {
          // Step through the open door into the destination room (Stage 3)
          setRoomVisibilityFn?.(currentStation);
          const destConfig = SPATIAL_STATIONS[currentStation];
          if (currentStation === "classes") {
            const fromDoor = SPATIAL_STATIONS[prevRoomForTransition];
            const entryPos = new THREE.Vector3(...fromDoor.classroomDoorApproach);
            teacherRig.body.position.copy(entryPos);
            activeEntryDoorPivot = classroomDoorPivots[prevRoomForTransition]?.pivot ?? null;
            const returnTarget = new THREE.Vector3(...destConfig.waypoint);
            if (selectedId) {
              const seatIndex = seats.findIndex((s) => s.student?.id === selectedId);
              if (seatIndex >= 0) {
                const { x: seatX, z: seatZ } = classroomWideSeatPosition(seatIndex);
                returnTarget.set(seatX, 0, seatZ + 1.42);
                teacherTargetLookAt.set(seatX, 1.0, seatZ);
              } else {
                teacherTargetLookAt.set(...destConfig.lookAt);
              }
            } else {
              teacherTargetLookAt.set(...destConfig.lookAt);
            }
            targetCamPos.copy(overviewCamPos);
            targetCamLookAt.copy(overviewCamTarget);
            camera.position.set(overviewCamPos.x, overviewCamPos.y + 0.3, overviewCamPos.z + 0.6);
            currentCamLookAt.copy(overviewCamTarget);
            camera.lookAt(currentCamLookAt);
            pathQueue = buildClassroomWalkPath(entryPos, returnTarget, false);
          } else {
            teacherRig.body.position.set(...destConfig.doorEntry);
            activeEntryDoorPivot = returnDoorPivots[currentStation]?.pivot ?? null;
            teacherTargetLookAt.set(...destConfig.lookAt);
            targetCamPos.set(...destConfig.camPos);
            targetCamLookAt.set(...destConfig.camTarget);
            camera.position.set(destConfig.camPos[0] - 0.6, destConfig.camPos[1] + 0.45, destConfig.camPos[2] + 1.05);
            currentCamLookAt.set(destConfig.camTarget[0] - 0.4, destConfig.camTarget[1], destConfig.camTarget[2]);
            camera.lookAt(currentCamLookAt);
            pathQueue = [new THREE.Vector3(...destConfig.waypoint)];
          }
          doorStage = "walk-from-entry-door";
          isWalking = true;
          walkStartTime = now;
        }
      } else if (moving && pathQueue.length > 0) {
        const nextTarget = pathQueue[0];
        const pos = teacherRig.body.position;
        const dist = pos.distanceTo(nextTarget);
        // Walk briskly along orthogonal classroom corridors, and gently inside specialized rooms
        const walkSpeed =
          visibleRoom === "classes"
            ? 6.4
            : doorStage === "walk-from-entry-door"
            ? 3.65
            : 4.85;
        if (dist > 0.07) {
          const moveDir = new THREE.Vector3().subVectors(nextTarget, pos).normalize();
          pos.addScaledVector(moveDir, Math.min(dist, walkSpeed * delta));
          const targetRotY = Math.atan2(moveDir.x, moveDir.z);
          // Shortest angle damping
          let angleDiff = targetRotY - teacherRig.body.rotation.y;
          while (angleDiff > Math.PI) angleDiff -= Math.PI * 2;
          while (angleDiff < -Math.PI) angleDiff += Math.PI * 2;
          teacherRig.body.rotation.y += angleDiff * Math.min(1, delta * 12);
        } else {
          pos.copy(nextTarget);
          pathQueue.shift();
          if (pathQueue.length === 0) {
            if (doorStage === "walk-to-exit-door") {
              // Arrived at the Exit Door -> Transition to Stage 2 (Opening the 3D Door)
              isWalking = false;
              doorStage = "open-exit-door";
              doorAnimStartTime = now;
            } else {
              // Arrived at the final Desk / Student / Podium -> Transition to Stage 4
              isWalking = false;
              doorStage = "none";
              if (currentStation !== "classes") {
                interactionStartTime = now;
                notifyPhase(currentStation, "interacting");
              } else {
                notifyPhase("classes", "ready");
              }
            }
          }
        }
        const stepFreq = doorStage === "walk-from-entry-door" ? 0.0092 : 0.011;
        const stepTime = (now - walkStartTime) * stepFreq;
        teacherRig.leftLeg.rotation.x = Math.sin(stepTime) * 0.48;
        teacherRig.rightLeg.rotation.x = -Math.sin(stepTime) * 0.48;
        teacherRig.leftArm.rotation.x = -Math.sin(stepTime) * 0.38 - 0.15;
        teacherRig.rightArm.rotation.x = Math.sin(stepTime) * 0.38 - 0.15;
        teacherRig.head.rotation.x = THREE.MathUtils.damp(teacherRig.head.rotation.x, -0.05, 6.0, delta);
        teacherRig.body.position.y = Math.abs(Math.sin(stepTime)) * 0.045;
      } else if (moving) {
        // Teacher has arrived at station: face station target & perform station gesture
        const faceDir = new THREE.Vector3().subVectors(teacherTargetLookAt, teacherRig.body.position).normalize();
        const targetRotY = Math.atan2(faceDir.x, faceDir.z);
        let angleDiff = targetRotY - teacherRig.body.rotation.y;
        while (angleDiff > Math.PI) angleDiff -= Math.PI * 2;
        while (angleDiff < -Math.PI) angleDiff += Math.PI * 2;
        teacherRig.body.rotation.y += angleDiff * Math.min(1, delta * 8);

        teacherRig.leftLeg.rotation.x = THREE.MathUtils.damp(teacherRig.leftLeg.rotation.x, 0, 6.0, delta);
        teacherRig.rightLeg.rotation.x = THREE.MathUtils.damp(teacherRig.rightLeg.rotation.x, 0, 6.0, delta);
        teacherRig.body.position.y = THREE.MathUtils.damp(
          teacherRig.body.position.y,
          Math.sin(t * 2.0) * 0.015,
          4.0,
          delta,
        );

        // Station-specific hand & head gestures (opening book, pointing at board, inspecting student)
        if (currentStation === "submissions" || currentStation === "materials") {
          const reachWave = stationPhase === "interacting" ? Math.sin((now - interactionStartTime) * 0.012) * 0.25 : Math.sin(t * 2.2) * 0.06;
          teacherRig.head.rotation.x = THREE.MathUtils.damp(teacherRig.head.rotation.x, 0.24, 5.0, delta);
          teacherRig.rightArm.rotation.x = THREE.MathUtils.damp(teacherRig.rightArm.rotation.x, -1.05 + reachWave, 6.0, delta);
          teacherRig.leftArm.rotation.x = THREE.MathUtils.damp(teacherRig.leftArm.rotation.x, -0.65, 5.0, delta);
        } else if (currentStation === "theory") {
          teacherRig.head.rotation.x = THREE.MathUtils.damp(teacherRig.head.rotation.x, -0.18, 5.0, delta);
          teacherRig.rightArm.rotation.x = THREE.MathUtils.damp(
            teacherRig.rightArm.rotation.x,
            -1.35 + Math.sin(t * 3.0) * 0.14,
            6.0,
            delta,
          );
          teacherRig.leftArm.rotation.x = THREE.MathUtils.damp(teacherRig.leftArm.rotation.x, -0.25, 5.0, delta);
        } else if (currentStation === "analytics") {
          teacherRig.head.rotation.x = THREE.MathUtils.damp(teacherRig.head.rotation.x, 0.1, 5.0, delta);
          teacherRig.rightArm.rotation.x = THREE.MathUtils.damp(
            teacherRig.rightArm.rotation.x,
            -0.85 + Math.sin(t * 3.2) * 0.12,
            6.0,
            delta,
          );
          teacherRig.leftArm.rotation.x = THREE.MathUtils.damp(teacherRig.leftArm.rotation.x, -0.3, 5.0, delta);
        } else if (selectedId) {
          // Leaning slightly to inspect a student's notebook at their desk
          teacherRig.head.rotation.x = THREE.MathUtils.damp(teacherRig.head.rotation.x, 0.22, 5.0, delta);
          teacherRig.rightArm.rotation.x = THREE.MathUtils.damp(teacherRig.rightArm.rotation.x, -0.55, 5.0, delta);
          teacherRig.leftArm.rotation.x = THREE.MathUtils.damp(teacherRig.leftArm.rotation.x, -0.2, 5.0, delta);
        } else {
          teacherRig.head.rotation.x = THREE.MathUtils.damp(teacherRig.head.rotation.x, -0.05, 5.0, delta);
          teacherRig.leftArm.rotation.x = THREE.MathUtils.damp(
            teacherRig.leftArm.rotation.x,
            -0.15 + Math.sin(t * 1.5) * 0.02,
            4.0,
            delta,
          );
          teacherRig.rightArm.rotation.x = THREE.MathUtils.damp(
            teacherRig.rightArm.rotation.x,
            -0.28 + Math.sin(t * 1.5) * 0.02,
            4.0,
            delta,
          );
        }

        // Complete "interacting" phase once book/prop animation finishes (520ms)
        if (stationPhase === "interacting" && now - interactionStartTime >= 520) {
          openProgress[currentStation] = 1;
          notifyPhase(currentStation, "ready");
        }
      }
    }

    // 5. Update 3D Station Props (Book cover, pages, drawer, board mindmap, AI bars)
    updateStationProps(t, delta);

    // 6. Keep 2D projected labels & station pins synchronized when camera moves
    if (cameraMoved) {
      const width = holder.clientWidth;
      const height = renderer.domElement.clientHeight;
      if (width > 0 && height > 0) {
        positionLabels(width, height);
      }
    }

    try {
      renderer.render(scene, camera);
    } catch {
      loseContext();
      return;
    }
    if (moving) schedule();
  }

  function positionLabels(width: number, height: number) {
    // Update floating 3D station doorway/prop pins whenever present
    if (stationPinElements) {
      STATION_PIN_ORDER.forEach((stationKey, idx) => {
        const el = stationPinElements[idx];
        if (!el) return;
        if (currentStation !== "classes" && currentStation !== stationKey) {
          el.style.opacity = "0";
          el.style.pointerEvents = "none";
          return;
        }
        const pin =
          currentStation === "classes"
            ? SPATIAL_STATIONS[stationKey].doorPinPos
            : SPATIAL_STATIONS[stationKey].propPinPos;
        projected.set(pin[0], pin[1], pin[2]).project(camera);
        if (projected.z > 1) {
          el.style.opacity = "0";
          el.style.pointerEvents = "none";
          return;
        }
        const x = (projected.x * 0.5 + 0.5) * width;
        const y = (-projected.y * 0.5 + 0.5) * height;
        el.style.left = `${Math.max(82, Math.min(width - 82, x))}px`;
        el.style.top = `${Math.max(32, Math.min(height - 32, y))}px`;
        el.style.opacity = "1";
        el.style.pointerEvents = "auto";
      });
    }

    if (compact.matches) return;
    for (let column = 0; column < CLASSROOM_COLUMNS; column++) {
      const positions = anchors
        .flatMap((anchor, index) => {
          const label = labels[index];
          if (!label || index % CLASSROOM_COLUMNS !== column) return [];
          projected.copy(anchor).project(camera);
          return [{ label, x: (projected.x * 0.5 + 0.5) * width, y: (-projected.y * 0.5 + 0.5) * height }];
        })
        .sort((left, right) => left.y - right.y);
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
      bubble.style.left = `${(projected.x * 0.5 + 0.5) * width}px`;
      bubble.style.top = `${(-projected.y * 0.5 + 0.5) * height}px`;
    }
  }

  function frameCamera(width: number, height: number) {
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    // Compute the ideal overview camera position for this viewport aspect ratio
    let distance = 1;
    const tempCam = camera.clone();
    for (let attempt = 0; attempt < 8; attempt++) {
      tempCam.position.copy(cameraTarget).addScaledVector(cameraOffset, distance);
      tempCam.lookAt(cameraTarget);
      tempCam.updateMatrixWorld(true);
      let overflow = 1;
      for (const corner of focusCorners) {
        projected.copy(corner).project(tempCam);
        overflow = Math.max(overflow, Math.abs(projected.x) / 0.94, Math.abs(projected.y) / 0.92);
      }
      if (overflow <= 1.002) break;
      distance *= overflow * 1.01;
    }
    overviewCamPos.copy(cameraTarget).addScaledVector(cameraOffset, distance);
    overviewCamTarget.copy(cameraTarget);

    if (currentStation === "classes" && !selectedId) {
      targetCamPos.copy(overviewCamPos);
      targetCamLookAt.copy(overviewCamTarget);
      if (!isWalking) {
        camera.position.copy(overviewCamPos);
        currentCamLookAt.copy(overviewCamTarget);
        camera.lookAt(currentCamLookAt);
        camera.updateMatrixWorld(true);
      }
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

  function activeTargets() {
    return targets.filter((t) => !t.userData.room || t.userData.room === visibleRoom);
  }

  function pointerDown(event: PointerEvent) {
    pointerStart = { x: event.clientX, y: event.clientY };
  }
  function pointerUp(event: PointerEvent) {
    if (!pointerStart || Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 10) {
      pointerStart = null;
      return;
    }
    pointerStart = null;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(activeTargets())[0];
    if (typeof hit?.object.userData.studentId === "string") onSelect(hit.object.userData.studentId);
    if (hit?.object.userData.mascot) onMascot();
    if (typeof hit?.object.userData.station === "string" && onStationSelect) {
      onStationSelect(hit.object.userData.station);
    }
  }
  function pointerMove(event: PointerEvent) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(activeTargets())[0];
    const next = typeof hit?.object.userData.studentId === "string" ? hit.object.userData.studentId : undefined;
    const nextDoor = typeof hit?.object.userData.doorId === "string" ? hit.object.userData.doorId : undefined;
    const isInteractive = Boolean(
      hit?.object.userData.studentId || hit?.object.userData.station || hit?.object.userData.mascot,
    );
    renderer.domElement.style.cursor = isInteractive ? "pointer" : "default";

    if (onHoverChange) {
      if (hit?.object.userData.hoverTitle) {
        const anchorPos = hit.object.userData.hoverAnchor as [number, number, number] | undefined;
        if (anchorPos) {
          projected.set(anchorPos[0], anchorPos[1], anchorPos[2]).project(camera);
          const sx = (projected.x * 0.5 + 0.5) * rect.width;
          const sy = (-projected.y * 0.5 + 0.5) * rect.height;
          onHoverChange({
            kind: hit.object.userData.hoverKind ?? "prop",
            id: hit.object.userData.studentId ?? hit.object.userData.station ?? "mascot",
            title: hit.object.userData.hoverTitle,
            subtitle: hit.object.userData.hoverSubtitle ?? "",
            badge: hit.object.userData.hoverBadge ?? "",
            x: sx,
            y: sy,
          });
        }
      } else {
        onHoverChange(null);
      }
    }

    if (next !== hoveredId || nextDoor !== hoveredDoorId) {
      hoveredId = next;
      hoveredDoorId = nextDoor;
      schedule();
    }
  }
  function pointerCancel() {
    pointerStart = null;
  }
  function visibilityChange() {
    if (!document.hidden) schedule();
  }
  function loseContext(event?: Event) {
    event?.preventDefault();
    if (unavailable || disposed) return;
    unavailable = true;
    cancelAnimationFrame(frame);
    frame = 0;
    onUnavailable();
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    cancelAnimationFrame(frame);
    resizeObserver?.disconnect();
    intersectionObserver?.disconnect();
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
    scene.clear();
    renderer.dispose();
    renderer.forceContextLoss();
    renderer.domElement.remove();
  }

  try {
    const sphere = geometry(new THREE.SphereGeometry(1, 20, 14));
    const cube = geometry(new THREE.BoxGeometry(1, 1, 1));
    const cylinder = geometry(new THREE.CylinderGeometry(1, 1, 1, 16));
    const ringShape = geometry(new THREE.TorusGeometry(1, 0.035, 6, 48));
    const stationRingShape = geometry(new THREE.RingGeometry(0.65, 0.82, 32));
    const circle = geometry(new THREE.CircleGeometry(0.85, 32));
    const hitShape = geometry(new THREE.BoxGeometry(1.8, 2.6, 1.9));
    const hitMaterial = material(new THREE.MeshBasicMaterial({ visible: false }));
    const models = createCozyModels({ geometry, material, color });

    function mesh(
      parent: THREE.Object3D,
      shape: THREE.BufferGeometry,
      tint: number,
      x: number,
      y: number,
      z: number,
      sx: number,
      sy: number,
      sz: number,
    ) {
      const result = new THREE.Mesh(shape, color(tint));
      result.position.set(x, y, z);
      result.scale.set(sx, sy, sz);
      result.castShadow = true;
      result.receiveShadow = true;
      parent.add(result);
      return result;
    }
    function ball(
      parent: THREE.Object3D,
      tint: number,
      x: number,
      y: number,
      z: number,
      sx: number,
      sy = sx,
      sz = sx,
    ) {
      return mesh(parent, sphere, tint, x, y, z, sx, sy, sz);
    }
    function block(
      parent: THREE.Object3D,
      tint: number,
      x: number,
      y: number,
      z: number,
      sx: number,
      sy: number,
      sz: number,
    ) {
      return mesh(parent, cube, tint, x, y, z, sx, sy, sz);
    }
    function roundBlock(
      parent: THREE.Object3D,
      tint: number,
      x: number,
      y: number,
      z: number,
      sx: number,
      sy: number,
      sz: number,
    ) {
      return mesh(parent, models.roundedGeometry, tint, x, y, z, sx, sy, sz);
    }
    function makeStationFloorRing(x: number, z: number, tint: number) {
      const ringMat = material(
        new THREE.MeshBasicMaterial({ color: tint, transparent: true, opacity: 0.2, side: THREE.DoubleSide }),
      );
      const r = new THREE.Mesh(stationRingShape, ringMat);
      r.rotation.x = -Math.PI / 2;
      r.position.set(x, 0.052, z);
      scene.add(r);
      return r;
    }

    scene.add(new THREE.HemisphereLight(0xfff8e9, 0x9caf9f, 2.1));
    const sun = new THREE.DirectionalLight(0xffefd9, 2.7);
    sun.position.set(-5, 12, 8);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    Object.assign(sun.shadow.camera, { left: -12, right: 12, top: 10, bottom: -10 });
    sun.shadow.normalBias = 0.035;
    sun.shadow.radius = 3;
    scene.add(sun);

    // Widescreen Main Classroom Floor & Walls (20.8m wide × 12.6m deep, filling 100% of 16:9 viewport)
    block(staticRoom, 0xdec9aa, 0, -0.28, -0.2, 20.8, 0.48, 12.8);
    block(staticRoom, 0xf0e4cc, 0, -0.01, -0.2, 20.4, 0.08, 12.4);
    for (let x = -9.6; x <= 9.6; x += 0.96) block(staticRoom, 0xdccbaf, x, 0.034, -0.2, 0.02, 0.006, 12.2);
    // Wide horizontal aisle runners & side wall walkways for teacher to walk across without colliding with desks
    block(staticRoom, 0xd3e1cc, 0, 0.044, 3.65, 17.8, 0.012, 1.35);
    block(staticRoom, 0xd3e1cc, 0, 0.044, -0.15, 17.8, 0.012, 1.15);
    block(staticRoom, 0xd3e1cc, -8.15, 0.044, 0.75, 1.35, 0.012, 7.15);
    block(staticRoom, 0xd3e1cc, 8.15, 0.044, 0.75, 1.35, 0.012, 7.15);
    // Back wall (z = -6.3), Left wall (x = -10.2), Right wall (x = +10.2)
    block(staticRoom, 0xe7eddb, 0, 1.65, -6.35, 20.8, 3.4, 0.22);
    block(staticRoom, 0xb6ceae, 0, 0.34, -6.2, 20.6, 0.68, 0.16);
    block(staticRoom, 0xf1ebd8, -10.25, 1.65, -0.2, 0.22, 3.4, 12.6);
    block(staticRoom, 0xc3d2b5, -10.1, 0.34, -0.2, 0.14, 0.68, 12.5);
    block(staticRoom, 0xf1ebd8, 10.25, 1.65, -0.2, 0.22, 3.4, 12.6);
    block(staticRoom, 0xc3d2b5, 10.1, 0.34, -0.2, 0.14, 0.68, 12.5);

    const classRoomExtras = new THREE.Group();
    scene.add(classRoomExtras);

    function makeWallSign(
      parent: THREE.Object3D,
      text: string,
      subText: string,
      x: number,
      y: number,
      z: number,
      width = 4.2,
      height = 0.85,
      bg = "#173f34",
      fg = "#fffdf5",
      rotY = 0,
    ) {
      const signCanvas = document.createElement("canvas");
      signCanvas.width = 1024;
      signCanvas.height = 220;
      const ctx = signCanvas.getContext("2d");
      if (!ctx) return;
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, 1024, 220);
      ctx.strokeStyle = "#d4a843";
      ctx.lineWidth = 12;
      ctx.strokeRect(14, 14, 996, 192);
      ctx.fillStyle = fg;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = "700 44px Segoe UI, Arial";
      ctx.fillText(text, 512, subText ? 84 : 110);
      if (subText) {
        ctx.fillStyle = "#fde68a";
        ctx.font = "600 28px Segoe UI, Arial";
        ctx.fillText(subText, 512, 150);
      }
      const tex = new THREE.CanvasTexture(signCanvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      textures.add(tex);
      const signMesh = new THREE.Mesh(
        geometry(new THREE.PlaneGeometry(width, height)),
        material(new THREE.MeshBasicMaterial({ map: tex, side: THREE.DoubleSide })),
      );
      signMesh.position.set(x, y, z);
      signMesh.rotation.y = rotY;
      parent.add(signMesh);
    }

    // Helper to build a real 3D Hinged Door with frame, doorknob, threshold mat, overhead angled sign & raycast hit
    function buildInteractiveDoor(
      parent: THREE.Object3D,
      opts: {
        id: string;
        room: StationKey;
        targetStation: StationKey;
        side: "left" | "right";
        x: number;
        z: number;
        frameColor: number;
        leafColor: number;
        signBg: string;
        title: string;
        subtitle: string;
        badge: string;
      },
    ) {
      const { id, room, targetStation, side, x, z, frameColor, leafColor, signBg, title, subtitle, badge } = opts;
      const dir = side === "left" ? 1 : -1;
      const doorGroup = new THREE.Group();
      doorGroup.position.set(x, 0, z);
      parent.add(doorGroup);

      // Welcome threshold mat on floor in front of door
      block(doorGroup, 0xd4a843, dir * 0.58, 0.042, 0, 0.92, 0.012, 1.85);
      block(doorGroup, frameColor, dir * 0.58, 0.048, 0, 0.8, 0.014, 1.7);

      // Outer 3D Wooden Door Frame & Jambs
      block(doorGroup, frameColor, 0, 2.38, 0, 0.28, 0.22, 1.96);
      block(doorGroup, frameColor, 0, 1.18, -0.9, 0.26, 2.36, 0.18);
      block(doorGroup, frameColor, 0, 1.18, 0.9, 0.26, 2.36, 0.18);
      // Dark interior recess behind door leaf so when door swings open it reveals a doorway depth
      block(doorGroup, 0x162923, -dir * 0.04, 1.16, 0, 0.08, 2.22, 1.62);

      // Hinged Door Leaf Pivot at (0, 0, -0.78) so rotating pivot.rotation.y swings the door open into the room!
      const pivot = new THREE.Group();
      pivot.position.set(dir * 0.06, 0, -0.78);
      doorGroup.add(pivot);

      // Door Leaf panel (extending from z = 0 to z = +1.56 relative to hinge)
      roundBlock(pivot, leafColor, 0, 1.15, 0.78, 0.12, 2.22, 1.56);
      // Decorative upper glass pane & lower recessed wood panel
      block(pivot, 0xbae6fd, dir * 0.045, 1.62, 0.78, 0.05, 0.62, 0.96);
      block(pivot, frameColor, dir * 0.04, 0.65, 0.78, 0.05, 0.72, 1.02);
      // Brass doorknob & plate near the latch edge (z = 1.34)
      block(pivot, 0xd4a843, dir * 0.07, 1.05, 1.34, 0.04, 0.24, 0.09);
      ball(pivot, 0xfbbf24, dir * 0.12, 1.05, 1.34, 0.065);

      // Overhead 3D Sign Board angled slightly toward the camera so it's crystal-clear from center view
      const signYaw = side === "left" ? Math.PI * 0.36 : -Math.PI * 0.36;
      const signGroup = new THREE.Group();
      signGroup.position.set(dir * 0.42, 2.75, 0);
      signGroup.rotation.y = signYaw;
      doorGroup.add(signGroup);
      roundBlock(signGroup, frameColor, 0, 0, -0.05, 2.85, 0.78, 0.1);
      makeWallSign(signGroup, title, "NHẤN ĐỂ MỞ CỬA", 0, 0, 0.02, 2.7, 0.66, signBg, "#fffdf5", 0);

      // Raycast hit box covering the door and overhead sign
      const doorHit = new THREE.Mesh(geometry(new THREE.BoxGeometry(1.15, 3.1, 2.2)), hitMaterial);
      doorHit.position.set(x + dir * 0.35, 1.5, z);
      doorHit.userData = {
        room,
        station: targetStation,
        doorId: id,
        hoverKind: "prop",
        hoverBadge: badge,
        hoverTitle: title,
        hoverSubtitle: subtitle,
        hoverAnchor: [x + dir * 0.65, 2.35, z],
      };
      scene.add(doorHit);
      targets.push(doorHit);

      const swingSign = side === "left" ? -1 : 1;
      allDoors.push({ id, pivot, sign: swingSign });
      return { pivot, sign: swingSign, id };
    }

    // Rear classroom panoramic blackboard & noticeboard
    block(staticRoom, 0xbaa384, 0, 2.0, -6.18, 7.6, 1.45, 0.14);
    block(staticRoom, 0x1e4638, 0, 2.0, -6.1, 7.3, 1.25, 0.1);
    const boardCanvas = document.createElement("canvas");
    boardCanvas.width = 1024;
    boardCanvas.height = 210;
    const boardContext = boardCanvas.getContext("2d");
    if (boardContext) {
      boardContext.fillStyle = "#1e4638";
      boardContext.fillRect(0, 0, 1024, 210);
      boardContext.strokeStyle = "#d4a843";
      boardContext.lineWidth = 8;
      boardContext.strokeRect(12, 12, 1000, 186);
      boardContext.fillStyle = "#f9f6ea";
      boardContext.textAlign = "center";
      boardContext.textBaseline = "middle";
      boardContext.font = "700 42px Segoe UI, Arial";
      boardContext.fillText("PHÒNG HỌC CHÍNH · LỚP MÌNH CÙNG TIẾN BỘ", 512, 105);
      const boardTexture = new THREE.CanvasTexture(boardCanvas);
      boardTexture.colorSpace = THREE.SRGBColorSpace;
      textures.add(boardTexture);
      const board = new THREE.Mesh(
        geometry(new THREE.PlaneGeometry(7.05, 1.12)),
        material(new THREE.MeshBasicMaterial({ map: boardTexture })),
      );
      board.position.set(0, 2.0, -6.02);
      classRoomExtras.add(board);
    }

    // Rear wall windows flanking the central blackboard
    for (const wx of [-6.4, 6.4]) {
      block(staticRoom, 0xe8f3ec, wx, 1.95, -6.18, 3.2, 1.55, 0.1);
      block(staticRoom, 0xadd1ce, wx, 1.95, -6.12, 2.95, 1.35, 0.06);
      block(staticRoom, 0xf4efe4, wx, 1.95, -6.08, 0.08, 1.4, 0.06);
      block(staticRoom, 0xf4efe4, wx, 1.95, -6.08, 3.0, 0.08, 0.06);
    }

    // 4 INTERACTIVE 3D HINGED DOORS IN MAIN CLASSROOM (2 on Left Wall, 2 on Right Wall)
    classroomDoorPivots.theory = buildInteractiveDoor(classRoomExtras, {
      id: "door-classes-theory",
      room: "classes",
      targetStation: "theory",
      side: "left",
      x: -10.05,
      z: 3.35,
      frameColor: 0x155e75,
      leafColor: 0x0e7490,
      signBg: "#155e75",
      badge: "CỬA PHÒNG 1 · TƯỜNG TRÁI",
      title: "🧠 Studio Lý Thuyết",
      subtitle: "Nhấn để Giáo viên đi tới mở cửa vào Studio Lý Thuyết",
    });

    classroomDoorPivots.analytics = buildInteractiveDoor(classRoomExtras, {
      id: "door-classes-analytics",
      room: "classes",
      targetStation: "analytics",
      side: "left",
      x: -10.05,
      z: -2.1,
      frameColor: 0x0f392d,
      leafColor: 0x1b6b52,
      signBg: "#0f392d",
      badge: "CỬA PHÒNG 2 · TƯỜNG TRÁI",
      title: "🌱 Phòng Lab AI",
      subtitle: "Nhấn để Giáo viên đi tới mở cửa vào Phòng Lab AI",
    });

    classroomDoorPivots.submissions = buildInteractiveDoor(classRoomExtras, {
      id: "door-classes-submissions",
      room: "classes",
      targetStation: "submissions",
      side: "right",
      x: 10.05,
      z: 3.35,
      frameColor: 0x5c3d24,
      leafColor: 0x8c5d38,
      signBg: "#173f34",
      badge: "CỬA PHÒNG 3 · TƯỜNG PHẢI",
      title: "📝 Phòng Chấm Bài",
      subtitle: "Nhấn để Giáo viên đi tới mở cửa vào Phòng Chấm Bài",
    });

    classroomDoorPivots.materials = buildInteractiveDoor(classRoomExtras, {
      id: "door-classes-materials",
      room: "classes",
      targetStation: "materials",
      side: "right",
      x: 10.05,
      z: -2.1,
      frameColor: 0x6e212b,
      leafColor: 0x8c3b32,
      signBg: "#6e212b",
      badge: "CỬA PHÒNG 4 · TƯỜNG PHẢI",
      title: "📚 Thư Viện Học Liệu",
      subtitle: "Nhấn để Giáo viên đi tới mở cửa vào Thư Viện Học Liệu",
    });

    const clock = mesh(staticRoom, cylinder, 0xf8f3e5, 4.35, 2.55, -6.18, 0.42, 0.12, 0.42);
    clock.rotation.x = Math.PI / 2;
    block(staticRoom, 0x526d5f, 4.35, 2.67, -6.08, 0.035, 0.24, 0.035);
    block(staticRoom, 0x526d5f, 4.47, 2.55, -6.08, 0.24, 0.035, 0.035);

    for (const [x, z] of [
      [-8.8, -5.2],
      [8.8, -5.2],
    ]) {
      mesh(staticRoom, cylinder, 0xc59b7e, x, 0.29, z, 0.34, 0.5, 0.34);
      block(staticRoom, 0x74906c, x, 0.9, z, 0.07, 1, 0.07);
      for (let leaf = 0; leaf < 5; leaf++) {
        const angle = leaf * 1.8;
        ball(
          staticRoom,
          0x77a16d,
          x + Math.sin(angle) * 0.24,
          1 + leaf * 0.1,
          z + Math.cos(angle) * 0.24,
          0.18,
          0.4,
          0.13,
        ).rotation.z = Math.sin(angle) * 0.8;
      }
    }

    // Student Desks in Wide Horizontal Widescreen Layout (5 columns across × 2 rows)
    seats.forEach((seat, index) => {
      const { x, z, column } = classroomWideSeatPosition(index);
      const desk = new THREE.Group();
      desk.position.set(x, 0, z + 0.8);
      staticRoom.add(desk);
      roundBlock(desk, 0xceb08a, 0, 0.91, 0, 1.85, 0.13, 1.04);
      roundBlock(desk, 0xe9cda2, 0, 0.99, 0, 1.91, 0.1, 1.1);
      for (const dx of [-0.73, 0.73]) {
        for (const dz of [-0.36, 0.36]) block(desk, 0x819c8e, dx, 0.45, dz, 0.075, 0.9, 0.075);
      }
      const chair = new THREE.Group();
      chair.position.set(x, 0, z - 0.13);
      staticRoom.add(chair);
      roundBlock(chair, 0x9fb8a1, 0, 0.48, 0, 0.73, 0.12, 0.68);
      roundBlock(chair, 0x9fb8a1, 0, 0.87, -0.28, 0.73, 0.65, 0.1);
      for (const dx of [-0.25, 0.25]) {
        for (const dz of [-0.2, 0.2]) block(chair, 0x6f8b79, dx, 0.23, dz, 0.055, 0.46, 0.055);
      }
      anchors.push(new THREE.Vector3(column < 2 ? -6.5 : 6.5, 0.8, z + 0.5));
      const student = seat.student;
      if (!student) return;
      block(desk, 0x7d9f87, 0.12, 1.033, 0, 0.78, 0.026, 0.55);
      block(desk, 0xf9f4df, 0.12, 1.045, 0, 0.7, 0.025, 0.48);
      block(desk, 0xc2d7c1, 0.12, 1.061, 0, 0.015, 0.008, 0.46);
      for (let line = 0; line < 3; line++) block(desk, 0xb9c8b5, 0.18, 1.062, -0.12 + line * 0.1, 0.24, 0.006, 0.012);
      mesh(desk, cylinder, 0xe8b24e, -0.48, 1.07, 0.04, 0.025, 0.45, 0.025).rotation.z = 1.28;
      const activity = classroomActivity(student);
      const rig = models.pupil(scene, student.id, x, z, activity === "offline");
      const accessories = models.accessories(scene, x, z);
      models.applyStyle(rig, accessories, customizations[student.id] ?? defaultDeskStyle(student.id));
      const disk = new THREE.Mesh(
        circle,
        material(new THREE.MeshBasicMaterial({ color: 0x82b894, transparent: true, opacity: 0.07, depthWrite: false })),
      );
      disk.rotation.x = -Math.PI / 2;
      disk.position.set(x, 0.045, z);
      scene.add(disk);
      const ring = new THREE.Mesh(
        ringShape,
        material(new THREE.MeshBasicMaterial({ color: 0x2f805b, transparent: true, opacity: 0.9 })),
      );
      ring.rotation.x = Math.PI / 2;
      ring.position.set(x, 0.06, z);
      ring.scale.setScalar(0.85);
      ring.visible = false;
      scene.add(ring);
      const hit = new THREE.Mesh(hitShape, hitMaterial);
      hit.position.set(x, 1.1, z + 0.35);
      hit.userData = {
        room: "classes",
        studentId: student.id,
        hoverKind: "student",
        hoverBadge: `BÀN ${String(index + 1).padStart(2, "0")}`,
        hoverTitle: student.name,
        hoverSubtitle:
          activity === "help"
            ? "Đang giơ tay cần hỗ trợ · Nhấn để Giáo viên đi tới bàn"
            : activity === "completed"
            ? "Đã hoàn thành bài · Nhấn để Giáo viên đi tới bàn"
            : activity === "offline"
            ? "Ngoại tuyến · Nhấn để xem hồ sơ"
            : "Đang học trên lớp · Nhấn để Giáo viên đi tới bàn",
        hoverAnchor: [x, 1.85, z],
      };
      scene.add(hit);
      targets.push(hit);
      people.push({
        ...rig,
        id: student.id,
        accessories,
        ring,
        disk,
        activity,
        celebratedAt: activity === "completed" ? performance.now() : -1,
        selectedAt: -1,
      });
    });

    // Mầm Xanh Mascot at (0, 0.05, 3.6) - preserved for direct greeting
    mascot = models.mam(scene);
    const mascotHit = new THREE.Mesh(geometry(new THREE.BoxGeometry(0.95, 1.55, 0.9)), hitMaterial);
    mascotHit.position.set(0, 0.8, 3.6);
    mascotHit.userData = {
      room: "classes",
      mascot: true,
      hoverKind: "mascot",
      hoverBadge: "TRỢ LÝ LỚP HỌC",
      hoverTitle: "Mầm Xanh AI",
      hoverSubtitle: "Nhấn để vẫy tay chào Mầm Xanh!",
      hoverAnchor: [0, 1.55, 3.6],
    };
    scene.add(mascotHit);
    targets.push(mascotHit);

    // Merge Room 1 (Main Classroom) static geometry into classRoomBatch Group
    const classRoomGroup = new THREE.Group();
    classRoomGroup.add(classRoomExtras);
    scene.add(classRoomGroup);

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
      const batch = new THREE.Mesh(geometry(merged), surface);
      batch.castShadow = true;
      batch.receiveShadow = true;
      classRoomGroup.add(batch);
    }
    scene.remove(staticRoom);
    staticRoom.clear();

    // =========================================================================
    // TALKING TOM FRONT-FACING DEDICATED 3D ROOMS (MỖI LẦN CHỈ HIỆN 1 PHÒNG CHÍNH DIỆN)
    // =========================================================================
    const roomGroups: Record<StationKey, THREE.Group> = {
      classes: classRoomGroup,
      submissions: new THREE.Group(),
      theory: new THREE.Group(),
      materials: new THREE.Group(),
      analytics: new THREE.Group(),
    };
    scene.add(roomGroups.submissions);
    scene.add(roomGroups.theory);
    scene.add(roomGroups.materials);
    scene.add(roomGroups.analytics);

    function buildFrontFacingRoomShell(
      group: THREE.Group,
      opts: {
        roomKey: StationKey;
        nextStationKey: StationKey;
        nextStationTitle: string;
        floorColor: number;
        trimColor: number;
        wallColor: number;
        wainscotColor: number;
        carpetColor: number;
        carpetBorderColor: number;
        titleText: string;
        subText: string;
        signBg: string;
      },
    ) {
      const {
        roomKey,
        nextStationKey,
        nextStationTitle,
        floorColor,
        trimColor,
        wallColor,
        wainscotColor,
        carpetColor,
        carpetBorderColor,
        titleText,
        subText,
        signBg,
      } = opts;
      // Wide Widescreen Room Floor & Base (14.4m wide × 8.6m deep, centered at x = 0, z = -0.4)
      block(group, trimColor, 0, -0.28, -0.4, 14.6, 0.48, 8.8);
      block(group, floorColor, 0, -0.01, -0.4, 14.4, 0.08, 8.6);
      for (let px = -6.6; px <= 6.6; px += 0.96) {
        block(group, trimColor, px, 0.034, -0.4, 0.02, 0.006, 8.4);
      }
      // Center Luxury Carpet
      block(group, carpetBorderColor, 0, 0.038, -0.35, 7.6, 0.01, 4.8);
      block(group, carpetColor, 0, 0.044, -0.35, 7.2, 0.012, 4.4);

      // Front-facing Backdrop Wall (North at z = -4.2) & Wide Side Walls (x = ±7.0)
      block(group, wallColor, 0, 1.75, -4.2, 14.4, 3.6, 0.22);
      block(group, wainscotColor, 0, 0.38, -4.06, 14.2, 0.78, 0.14);

      block(group, wallColor, -7.0, 1.75, -0.4, 0.22, 3.6, 8.6);
      block(group, wainscotColor, -6.86, 0.38, -0.4, 0.14, 0.78, 8.5);

      block(group, wallColor, 7.0, 1.75, -0.4, 0.22, 3.6, 8.6);
      block(group, wainscotColor, 6.86, 0.38, -0.4, 0.14, 0.78, 8.5);

      // Wall-mounted 3D Sign flat on the front wall
      block(group, wainscotColor, 0, 2.72, -4.05, 5.2, 1.0, 0.1);
      makeWallSign(group, titleText, subText, 0, 2.72, -3.98, 5.0, 0.85, signBg);

      // DOOR #5: THE RETURN DOOR TO MAIN CLASSROOM (Mounted on Left Wall of every specialized room!)
      returnDoorPivots[roomKey] = buildInteractiveDoor(group, {
        id: `door-${roomKey}-return-classes`,
        room: roomKey,
        targetStation: "classes",
        side: "left",
        x: -6.82,
        z: 0.65,
        frameColor: wainscotColor,
        leafColor: 0x286955,
        signBg: "#173f34",
        badge: "CỬA SỐ 5 · QUAY VỀ LỚP",
        title: "🏫 Về Phòng Học Chính",
        subtitle: "Nhấn để Giáo viên đi ra mở cửa quay về Lớp Học Chính",
      });

      // Right Wall Connecting Door to the adjacent specialized room
      buildInteractiveDoor(group, {
        id: `door-${roomKey}-next-${nextStationKey}`,
        room: roomKey,
        targetStation: nextStationKey,
        side: "right",
        x: 6.82,
        z: 0.65,
        frameColor: wainscotColor,
        leafColor: 0x7c5333,
        signBg,
        badge: "CỬA THÔNG PHÒNG",
        title: nextStationTitle,
        subtitle: `Nhấn để Giáo viên mở cửa sang ${nextStationTitle}`,
      });
    }

    // -------------------------------------------------------------------------
    // PHÒNG 2 (CHÍNH DIỆN): PHÒNG CHẤM BÀI GIÁO VIÊN (submissions)
    // -------------------------------------------------------------------------
    buildFrontFacingRoomShell(roomGroups.submissions, {
      roomKey: "submissions",
      nextStationKey: "materials",
      nextStationTitle: "📚 Thư Viện Học Liệu",
      floorColor: 0x8c623e,
      trimColor: 0x694629,
      wallColor: 0xf5ece0,
      wainscotColor: 0x5c3d24,
      carpetColor: 0x184e3d,
      carpetBorderColor: 0xd4a843,
      titleText: "PHÒNG CHẤM BÀI & ĐÁNH GIÁ",
      subText: "NHẤN VÀO SỔ CHẤM BÀI TRÊN BÀN ĐỂ MỞ",
      signBg: "#173f34",
    });

    // Left Wall Rubric Corkboard & Right Credenza inside Room 2
    block(roomGroups.submissions, 0x6e472b, -3.2, 1.65, -4.04, 2.4, 1.15, 0.1);
    block(roomGroups.submissions, 0xe8d8be, -3.2, 1.65, -3.97, 2.2, 0.98, 0.06);
    for (const [rx, ry, rColor] of [
      [-3.7, 1.82, 0xfffdf5],
      [-3.1, 1.78, 0xd1fae5],
      [-2.6, 1.84, 0xfef3c7],
      [-3.4, 1.45, 0xe0f2fe],
      [-2.8, 1.48, 0xffe4e6],
    ] as const) {
      block(roomGroups.submissions, rColor, rx, ry, -3.92, 0.45, 0.28, 0.03);
    }
    roundBlock(roomGroups.submissions, 0x70492c, 3.3, 0.55, -3.4, 1.9, 1.1, 0.85);
    mesh(roomGroups.submissions, cylinder, 0xf2c96d, 3.3, 1.28, -3.4, 0.16, 0.32, 0.16);
    // Warm Standing Floor Lamp
    mesh(roomGroups.submissions, cylinder, 0xd4a843, -3.6, 0.08, -2.8, 0.28, 0.12, 0.28);
    block(roomGroups.submissions, 0xd4a843, -3.6, 1.05, -2.8, 0.06, 1.9, 0.06);
    mesh(roomGroups.submissions, cylinder, 0xffe49e, -3.6, 2.05, -2.8, 0.38, 0.36, 0.38);

    // Executive Teacher Desk at center of Room 2 (x = 0, z = -0.15)
    const teacherDeskGroup = new THREE.Group();
    teacherDeskGroup.position.set(0, 0, -0.15);
    roomGroups.submissions.add(teacherDeskGroup);
    roundBlock(teacherDeskGroup, 0x4a2f1d, 0, 0.52, -1.25, 0.86, 0.14, 0.82);
    roundBlock(teacherDeskGroup, 0x4a2f1d, 0, 1.05, -1.58, 0.86, 0.98, 0.16);
    roundBlock(teacherDeskGroup, 0x6e472b, 0, 0.48, 0, 2.65, 0.92, 1.4);
    roundBlock(teacherDeskGroup, 0x9c6b43, 0, 0.96, 0, 2.85, 0.1, 1.56);
    block(teacherDeskGroup, 0xd4a843, 0, 0.65, 0.71, 2.2, 0.06, 0.04);
    block(teacherDeskGroup, 0xfffef7, -0.92, 1.05, 0.08, 0.46, 0.11, 0.58);
    block(teacherDeskGroup, 0xfdf8e8, -0.88, 1.13, 0.05, 0.44, 0.08, 0.56);
    mesh(teacherDeskGroup, cylinder, 0xd4a843, 0.96, 1.05, -0.25, 0.18, 0.06, 0.18);
    block(teacherDeskGroup, 0xd4a843, 0.96, 1.28, -0.25, 0.045, 0.44, 0.045);
    roundBlock(teacherDeskGroup, 0x1f6b4e, 0.96, 1.5, -0.22, 0.38, 0.16, 0.24);

    // Dynamic Animated Grading Book (Sổ Chấm Bài 3D) in center of Executive Desk
    const ledgerRoot = new THREE.Group();
    ledgerRoot.position.set(0, 1.02, -0.1);
    roomGroups.submissions.add(ledgerRoot);
    block(ledgerRoot, 0x165b45, 0.32, 0.015, 0, 0.62, 0.03, 0.78);
    block(ledgerRoot, 0xfffdf2, 0.3, 0.038, 0, 0.56, 0.032, 0.72);
    for (let line = -2; line <= 2; line++) {
      block(ledgerRoot, 0x8bb5a2, 0.3, 0.058, line * 0.11, 0.42, 0.005, 0.022);
    }
    block(ledgerRoot, 0xd4a843, 0, 0.036, 0, 0.06, 0.065, 0.8);

    ledgerCoverPivot = new THREE.Group();
    ledgerCoverPivot.position.set(0, 0.058, 0);
    ledgerRoot.add(ledgerCoverPivot);
    block(ledgerCoverPivot, 0x1b6b52, 0.32, 0.015, 0, 0.62, 0.03, 0.78);
    block(ledgerCoverPivot, 0xf2c96d, 0.32, 0.032, 0, 0.28, 0.008, 0.36);
    block(ledgerCoverPivot, 0xfffef7, 0.3, -0.002, 0, 0.56, 0.008, 0.72);

    ledgerPage1Pivot = new THREE.Group();
    ledgerPage1Pivot.position.set(0, 0.052, 0);
    ledgerRoot.add(ledgerPage1Pivot);
    block(ledgerPage1Pivot, 0xfffef9, 0.29, 0.005, 0, 0.54, 0.007, 0.7);
    block(ledgerPage1Pivot, 0x3b8f72, 0.29, 0.011, -0.14, 0.4, 0.005, 0.03);
    block(ledgerPage1Pivot, 0xd97757, 0.29, 0.011, 0.08, 0.35, 0.005, 0.03);

    ledgerPage2Pivot = new THREE.Group();
    ledgerPage2Pivot.position.set(0, 0.055, 0);
    ledgerRoot.add(ledgerPage2Pivot);
    block(ledgerPage2Pivot, 0xffffff, 0.29, 0.005, 0, 0.54, 0.007, 0.7);
    block(ledgerPage2Pivot, 0x286955, 0.29, 0.011, -0.1, 0.38, 0.005, 0.03);

    ledgerGlowRing = makeStationFloorRing(0, -1.05, 0x286955);
    roomGroups.submissions.add(ledgerGlowRing);

    const teacherDeskHit = new THREE.Mesh(geometry(new THREE.BoxGeometry(2.8, 2.1, 1.9)), hitMaterial);
    teacherDeskHit.position.set(0, 1.1, -0.15);
    teacherDeskHit.userData = {
      room: "submissions",
      station: "submissions",
      hoverKind: "prop",
      hoverBadge: "PHÒNG CHẤM BÀI",
      hoverTitle: "Sổ Chấm Bài & Bài Nộp Học Sinh",
      hoverSubtitle: "Nhấn vào quyển sổ để mở/đóng bảng chấm bài",
      hoverAnchor: [0, 1.85, -0.15],
    };
    scene.add(teacherDeskHit);
    targets.push(teacherDeskHit);

    // -------------------------------------------------------------------------
    // PHÒNG 4 (CHÍNH DIỆN): STUDIO SƠ ĐỒ LÝ THUYẾT (theory)
    // -------------------------------------------------------------------------
    buildFrontFacingRoomShell(roomGroups.theory, {
      roomKey: "theory",
      nextStationKey: "analytics",
      nextStationTitle: "🌱 Phòng Lab AI",
      floorColor: 0xd8e8e2,
      trimColor: 0x9ab8ad,
      wallColor: 0xf2f7f5,
      wainscotColor: 0x3a6b5c,
      carpetColor: 0x155e75,
      carpetBorderColor: 0x38bdf8,
      titleText: "STUDIO SƠ ĐỒ LÝ THUYẾT",
      subText: "NHẤN VÀO BẢNG SƠ ĐỒ TRÊN TƯỜNG ĐỂ MỞ",
      signBg: "#155e75",
    });

    // Panoramic Interactive Mindmap Board mounted FLAT on the front wall of Room 4
    const boardStation = new THREE.Group();
    boardStation.position.set(0, 0, -3.85);
    roomGroups.theory.add(boardStation);

    roundBlock(boardStation, 0x1e3a34, 0, 1.38, 0, 4.8, 1.85, 0.12);
    roundBlock(boardStation, 0xf7fcf9, 0, 1.38, 0.06, 4.52, 1.62, 0.05);

    boardNodesGroup = new THREE.Group();
    boardNodesGroup.position.set(0, 1.38, 0.11);
    boardStation.add(boardNodesGroup);
    roundBlock(boardNodesGroup, 0x1f634d, 0, 0, 0, 0.82, 0.36, 0.05);
    const branchConfigs: [number, number, number, number][] = [
      [-1.15, 0.45, 0xe07a5f, 0.38],
      [1.15, 0.45, 0x3d85c6, -0.38],
      [-1.25, 0.0, 0x10b981, 0.0],
      [1.25, 0.0, 0xf59e0b, 0.0],
      [-1.15, -0.45, 0xe6a145, -0.38],
      [1.15, -0.45, 0x8e6bbf, 0.38],
    ];
    for (const [bx, by, bColor, rot] of branchConfigs) {
      const link = block(boardNodesGroup, 0x6ea190, bx * 0.52, by * 0.52, -0.01, 0.95, 0.04, 0.02);
      link.rotation.z = rot;
      roundBlock(boardNodesGroup, bColor, bx, by, 0.015, 0.66, 0.28, 0.05);
    }

    roundBlock(roomGroups.theory, 0xe2ece8, -2.8, 0.48, -0.8, 1.6, 0.9, 1.0);
    ball(roomGroups.theory, 0x38bdf8, -3.05, 1.15, -0.8, 0.22);
    mesh(roomGroups.theory, cylinder, 0xf59e0b, -2.5, 1.15, -0.8, 0.18, 0.36, 0.18);

    boardGlowRing = makeStationFloorRing(1.55, -1.25, 0x0284c7);
    roomGroups.theory.add(boardGlowRing);

    const smartBoardHit = new THREE.Mesh(geometry(new THREE.BoxGeometry(4.8, 2.4, 1.5)), hitMaterial);
    smartBoardHit.position.set(0, 1.45, -3.5);
    smartBoardHit.userData = {
      room: "theory",
      station: "theory",
      hoverKind: "prop",
      hoverBadge: "STUDIO LÝ THUYẾT",
      hoverTitle: "Đại Bảng Sơ Đồ Tư Duy 3D",
      hoverSubtitle: "Nhấn vào bảng để mở/đóng Sơ đồ lý thuyết",
      hoverAnchor: [0, 2.25, -3.4],
    };
    scene.add(smartBoardHit);
    targets.push(smartBoardHit);

    // -------------------------------------------------------------------------
    // PHÒNG 3 (CHÍNH DIỆN): THƯ VIỆN HỌC LIỆU & KHO ĐỀ THI (materials)
    // -------------------------------------------------------------------------
    buildFrontFacingRoomShell(roomGroups.materials, {
      roomKey: "materials",
      nextStationKey: "theory",
      nextStationTitle: "🧠 Studio Lý Thuyết",
      floorColor: 0xe6dccb,
      trimColor: 0xc2b299,
      wallColor: 0xf7f2e7,
      wainscotColor: 0x7c5333,
      carpetColor: 0x6e212b,
      carpetBorderColor: 0xd4a843,
      titleText: "THƯ VIỆN HỌC LIỆU & ĐỀ THI",
      subText: "NHẤN VÀO SỔ ĐỀ THI TRÊN BÀN ĐỂ MỞ",
      signBg: "#6e212b",
    });

    for (const bx of [-3.1, 3.1]) {
      const shelfUnit = new THREE.Group();
      shelfUnit.position.set(bx, 0, -3.72);
      roomGroups.materials.add(shelfUnit);
      roundBlock(shelfUnit, 0x8c5d38, 0, 1.25, 0, 2.4, 2.5, 0.65);
      roundBlock(shelfUnit, 0x5e3c22, 0, 1.25, 0.06, 2.18, 2.25, 0.58);
      for (const sy of [0.55, 1.1, 1.65, 2.15]) {
        block(shelfUnit, 0x8c5d38, 0, sy, 0.08, 2.22, 0.06, 0.6);
        for (let bIdx = 0; bIdx < 6; bIdx++) {
          const bookColor = [0x2b6e56, 0xb84a39, 0x3b6ea5, 0xd99b38, 0x7b5294, 0x286955][(bIdx + Math.round(sy * 2)) % 6];
          block(shelfUnit, bookColor, -0.82 + bIdx * 0.32, sy + 0.21, 0.14, 0.22, 0.36, 0.34);
        }
      }
    }

    const archiveRoot = new THREE.Group();
    archiveRoot.position.set(0, 0, -0.15);
    roomGroups.materials.add(archiveRoot);
    roundBlock(archiveRoot, 0x7c5333, 0, 0.48, 0, 2.55, 0.92, 1.4);
    roundBlock(archiveRoot, 0xb8895a, 0, 0.96, 0, 2.75, 0.1, 1.55);

    archiveDrawer = new THREE.Group();
    archiveDrawer.position.set(0, 0.72, 0.42);
    archiveRoot.add(archiveDrawer);
    roundBlock(archiveDrawer, 0x9c6d44, 0, 0, 0, 1.35, 0.26, 0.68);
    block(archiveDrawer, 0xf2c96d, 0, 0.02, 0.35, 0.32, 0.05, 0.04);

    const portfolioBase = new THREE.Group();
    portfolioBase.position.set(0, 1.02, 0.05);
    portfolioBase.rotation.y = Math.PI;
    archiveRoot.add(portfolioBase);
    block(portfolioBase, 0x7c232b, -0.3, 0.015, 0, 0.58, 0.03, 0.74);
    block(portfolioBase, 0xfffdf2, -0.28, 0.036, 0, 0.52, 0.03, 0.68);
    block(portfolioBase, 0xd4a843, 0, 0.034, 0, 0.055, 0.06, 0.76);

    archiveCoverPivot = new THREE.Group();
    archiveCoverPivot.position.set(0, 0.055, 0);
    portfolioBase.add(archiveCoverPivot);
    block(archiveCoverPivot, 0x992b36, -0.3, 0.015, 0, 0.58, 0.03, 0.74);
    block(archiveCoverPivot, 0xf2c96d, -0.3, 0.032, 0, 0.24, 0.008, 0.32);

    archivePagePivot = new THREE.Group();
    archivePagePivot.position.set(0, 0.048, 0);
    portfolioBase.add(archivePagePivot);
    block(archivePagePivot, 0xffffff, -0.27, 0.005, 0, 0.5, 0.007, 0.65);
    block(archivePagePivot, 0x7c232b, -0.27, 0.011, -0.12, 0.36, 0.005, 0.03);

    archiveGlowRing = makeStationFloorRing(0, -1.1, 0xd97757);
    roomGroups.materials.add(archiveGlowRing);

    const bookshelfHit = new THREE.Mesh(geometry(new THREE.BoxGeometry(2.8, 2.2, 2.0)), hitMaterial);
    bookshelfHit.position.set(0, 1.15, -0.15);
    bookshelfHit.userData = {
      room: "materials",
      station: "materials",
      hoverKind: "prop",
      hoverBadge: "THƯ VIỆN HỌC LIỆU",
      hoverTitle: "Tủ Đề Thi & Sổ Học Liệu PDF",
      hoverSubtitle: "Nhấn vào quyển sổ để mở/đóng Kho học liệu & Giao bài",
      hoverAnchor: [0, 1.85, -0.15],
    };
    scene.add(bookshelfHit);
    targets.push(bookshelfHit);

    // -------------------------------------------------------------------------
    // PHÒNG 5 (CHÍNH DIỆN): PHÒNG LAB PHÂN TÍCH MẦM XANH AI (analytics)
    // -------------------------------------------------------------------------
    buildFrontFacingRoomShell(roomGroups.analytics, {
      roomKey: "analytics",
      nextStationKey: "submissions",
      nextStationTitle: "📝 Phòng Chấm Bài",
      floorColor: 0x173a30,
      trimColor: 0x0f2922,
      wallColor: 0xe6f4ef,
      wainscotColor: 0x1b4d3e,
      carpetColor: 0x0d261f,
      carpetBorderColor: 0x34d399,
      titleText: "PHÒNG LAB PHÂN TÍCH AI",
      subText: "NHẤN VÀO BÀN HOLOGRAM ĐỂ XEM BÁO CÁO",
      signBg: "#0f392d",
    });

    for (const [px, pz] of [
      [-3.3, -3.2],
      [3.3, -3.2],
    ]) {
      mesh(roomGroups.analytics, cylinder, 0xc59b7e, px, 0.32, pz, 0.36, 0.55, 0.36);
      block(roomGroups.analytics, 0x34d399, px, 1.05, pz, 0.09, 1.2, 0.09);
      ball(roomGroups.analytics, 0x6ee7b7, px, 1.75, pz, 0.42, 0.48, 0.42);
    }

    const aiHubGroup = new THREE.Group();
    aiHubGroup.position.set(0, 0, -0.15);
    roomGroups.analytics.add(aiHubGroup);
    mesh(aiHubGroup, cylinder, 0x1f4e3f, 0, 0.46, 0, 0.98, 0.92, 0.98);
    mesh(aiHubGroup, cylinder, 0x286955, 0, 0.96, 0, 1.15, 0.08, 1.15);
    mesh(aiHubGroup, cylinder, 0x6ee7b7, 0, 1.02, 0, 0.9, 0.03, 0.9);

    aiBarsGroup = new THREE.Group();
    aiBarsGroup.position.set(0, 1.05, 0);
    aiHubGroup.add(aiBarsGroup);
    const barConfigs: [number, number, number, number][] = [
      [-0.38, -0.16, 0.55, 0x3bb9b0],
      [-0.12, 0.18, 0.82, 0x63c99a],
      [0.14, -0.12, 0.68, 0xf59e0b],
      [0.4, 0.14, 0.98, 0x8b5cf6],
    ];
    for (const [bx, bz, bh, bColor] of barConfigs) {
      block(aiBarsGroup, bColor, bx, bh / 2, bz, 0.18, bh, 0.18);
    }

    aiOrbitRing = new THREE.Mesh(
      ringShape,
      material(new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.88 })),
    );
    aiOrbitRing.position.set(0, 1.48, 0);
    aiOrbitRing.scale.setScalar(0.85);
    aiHubGroup.add(aiOrbitRing);

    aiGlowRing = makeStationFloorRing(0, -1.25, 0x10b981);
    roomGroups.analytics.add(aiGlowRing);

    const aiHubHit = new THREE.Mesh(geometry(new THREE.BoxGeometry(2.5, 2.3, 2.4)), hitMaterial);
    aiHubHit.position.set(0, 1.2, -0.15);
    aiHubHit.userData = {
      room: "analytics",
      station: "analytics",
      hoverKind: "prop",
      hoverBadge: "PHÒNG LAB AI",
      hoverTitle: "Đài Quan Sát Năng Lực Hologram AI",
      hoverSubtitle: "Nhấn vào đài quan sát để mở/đóng Báo cáo năng lực AI",
      hoverAnchor: [0, 2.05, -0.15],
    };
    scene.add(aiHubHit);
    targets.push(aiHubHit);

    function setRoomVisibility(activeKey: StationKey) {
      visibleRoom = activeKey;
      (Object.keys(roomGroups) as StationKey[]).forEach((k) => {
        roomGroups[k].visible = k === activeKey;
      });
      const inClassroom = activeKey === "classes";
      people.forEach((p) => {
        p.body.visible = inClassroom;
        p.disk.visible = inClassroom;
        p.ring.visible = inClassroom && p.id === selectedId;
      });
      if (mascot) {
        mascot.body.visible = inClassroom;
      }
    }
    setRoomVisibilityFn = setRoomVisibility;

    // =========================================================================
    // TEACHER AVATAR IN CLASSROOM
    // =========================================================================
    teacherRig = models.teacher(scene);
    teacherRig.body.position.set(...SPATIAL_STATIONS.classes.waypoint);
    teacherRig.body.rotation.y = Math.PI;
    setRoomVisibility("classes");

    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    renderer.domElement.addEventListener("pointercancel", pointerCancel);
    renderer.domElement.addEventListener("pointermove", pointerMove);
    renderer.domElement.addEventListener("webglcontextlost", loseContext);
    document.addEventListener("visibilitychange", visibilityChange);
    compact.addEventListener("change", resize);
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(holder);
    intersectionObserver = new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
      if (visible) schedule();
    });
    intersectionObserver.observe(holder);
    resize();

    function setStationInternal(stationKey: string) {
      const validKey: StationKey =
        stationKey === "submissions" ||
        stationKey === "theory" ||
        stationKey === "materials" ||
        stationKey === "analytics"
          ? stationKey
          : "classes";

      const prevStation = currentStation;
      currentStation = validKey;
      onHoverChange?.(null);

      const config = SPATIAL_STATIONS[validKey];
      const targetWaypoint = new THREE.Vector3(...config.waypoint);
      const targetLook = new THREE.Vector3(...config.lookAt);

      if (validKey === "classes") {
        if (selectedId) {
          const seatIndex = seats.findIndex((s) => s.student?.id === selectedId);
          if (seatIndex >= 0) {
            const { x: seatX, z: seatZ } = classroomWideSeatPosition(seatIndex);
            targetWaypoint.set(seatX, 0, seatZ + 1.42);
            targetLook.set(seatX, 1.0, seatZ);
            targetCamPos.set(seatX * 0.45, 3.6, seatZ + 4.4);
            targetCamLookAt.set(seatX, 1.05, seatZ + 0.2);
          } else {
            targetCamPos.copy(overviewCamPos);
            targetCamLookAt.copy(overviewCamTarget);
          }
        } else {
          targetCamPos.copy(overviewCamPos);
          targetCamLookAt.copy(overviewCamTarget);
        }
      } else {
        targetCamPos.set(...config.camPos);
        targetCamLookAt.set(...config.camTarget);
      }

      if (!motion) {
        setRoomVisibility(validKey);
        doorStage = "none";
        teacherTargetLookAt.copy(targetLook);
        if (teacherRig) {
          teacherRig.body.position.copy(targetWaypoint);
          const faceDir = new THREE.Vector3().subVectors(teacherTargetLookAt, targetWaypoint).normalize();
          teacherRig.body.rotation.y = Math.atan2(faceDir.x, faceDir.z);
        }
        camera.position.copy(targetCamPos);
        currentCamLookAt.copy(targetCamLookAt);
        camera.lookAt(currentCamLookAt);
        camera.updateMatrixWorld(true);
        pathQueue = [];
        isWalking = false;
        if (validKey !== "classes") {
          openProgress[validKey] = 1;
        }
        notifyPhase(validKey, "ready");
        positionLabels(holder.clientWidth, renderer.domElement.clientHeight);
        schedule();
        return;
      }

      if (teacherRig) {
        const cur = teacherRig.body.position;
        const distToTarget = cur.distanceTo(targetWaypoint);
        if (distToTarget < 0.15 && prevStation === validKey) {
          pathQueue = [];
          isWalking = false;
          doorStage = "none";
          if (validKey !== "classes" && stationPhase !== "ready") {
            interactionStartTime = performance.now();
            notifyPhase(validKey, "interacting");
          } else {
            notifyPhase(validKey, "ready");
          }
          positionLabels(holder.clientWidth, renderer.domElement.clientHeight);
          schedule();
          return;
        }

        // 4-STAGE DOOR SEQUENCE WHEN CHANGING ROOMS (prevStation !== validKey)
        if (prevStation !== validKey) {
          prevRoomForTransition = prevStation;
          setRoomVisibility(prevStation); // Keep current room visible while teacher walks to the Exit Door & opens it!
          doorStage = "walk-to-exit-door";
          const exitQueue: THREE.Vector3[] = [];

          if (prevStation === "classes") {
            // Walking from starting/current position in Main Classroom to one of the 4 Classroom Doors
            const destDoor = SPATIAL_STATIONS[validKey];
            const doorApproach = new THREE.Vector3(...destDoor.classroomDoorApproach);
            exitQueue.push(...buildClassroomWalkPath(cur, doorApproach, true));
            teacherTargetLookAt.set(...destDoor.classroomDoorLookAt);
            activeExitDoorPivot = classroomDoorPivots[validKey]?.pivot ?? null;
            activeExitDoorSign = classroomDoorPivots[validKey]?.sign ?? 1;
            // Gently pan camera toward the door being approached
            targetCamPos.set(destDoor.classroomDoorApproach[0] * 0.32, overviewCamPos.y - 0.5, overviewCamPos.z - 0.6);
            targetCamLookAt.set(destDoor.classroomDoorApproach[0] * 0.55, 1.25, destDoor.classroomDoorApproach[2]);
          } else {
            // Walking from specialized room desk to the Return Door (left wall)
            exitQueue.push(new THREE.Vector3(-5.35, 0, 0.65));
            teacherTargetLookAt.set(-7.1, 1.25, 0.65);
            activeExitDoorPivot = returnDoorPivots[prevStation]?.pivot ?? null;
            activeExitDoorSign = returnDoorPivots[prevStation]?.sign ?? -1;
            targetCamPos.set(-1.5, 3.1, 4.4);
            targetCamLookAt.set(-4.2, 1.2, 0.4);
          }

          pathQueue = exitQueue;
          isWalking = true;
          walkStartTime = performance.now();
          notifyPhase(validKey, "walking");
          positionLabels(holder.clientWidth, renderer.domElement.clientHeight);
          schedule();
          return;
        }

        // Same room (e.g. walking to a student desk in Main Classroom)
        setRoomVisibility(validKey);
        doorStage = "none";
        teacherTargetLookAt.copy(targetLook);
        const queue: THREE.Vector3[] = [];
        if (validKey === "classes") {
          queue.push(...buildClassroomWalkPath(cur, targetWaypoint, false));
        } else {
          queue.push(targetWaypoint.clone());
        }
        pathQueue = queue;
        isWalking = true;
        walkStartTime = performance.now();
        notifyPhase(validKey, "walking");
        positionLabels(holder.clientWidth, renderer.domElement.clientHeight);
      }
      schedule();
    }

    return {
      select(studentId) {
        selectedId = studentId;
        people.forEach((person) => {
          person.ring.visible = person.id === studentId;
          if (person.id === studentId) person.selectedAt = performance.now();
        });
        positionLabels(holder.clientWidth, renderer.domElement.clientHeight);
        if (currentStation === "classes") {
          setStationInternal("classes");
        }
        schedule();
      },
      setStation(stationKey) {
        setStationInternal(stationKey);
      },
      skipStationAnimation() {
        setRoomVisibility(currentStation);
        doorStage = "none";
        for (const d of allDoors) {
          d.pivot.rotation.y = 0;
        }
        const config = SPATIAL_STATIONS[currentStation];
        const targetWaypoint = new THREE.Vector3(...config.waypoint);
        if (currentStation === "classes" && selectedId) {
          const seatIndex = seats.findIndex((s) => s.student?.id === selectedId);
          if (seatIndex >= 0) {
            const { x: seatX, z: seatZ } = classroomWideSeatPosition(seatIndex);
            targetWaypoint.set(seatX, 0, seatZ + 1.42);
            teacherTargetLookAt.set(seatX, 1.0, seatZ);
            targetCamPos.set(seatX * 0.45, 3.6, seatZ + 4.4);
            targetCamLookAt.set(seatX, 1.05, seatZ + 0.2);
          }
        } else {
          teacherTargetLookAt.set(...config.lookAt);
          if (currentStation === "classes") {
            targetCamPos.copy(overviewCamPos);
            targetCamLookAt.copy(overviewCamTarget);
          } else {
            targetCamPos.set(...config.camPos);
            targetCamLookAt.set(...config.camTarget);
          }
        }
        if (teacherRig) {
          teacherRig.body.position.copy(targetWaypoint);
          const faceDir = new THREE.Vector3().subVectors(teacherTargetLookAt, targetWaypoint).normalize();
          teacherRig.body.rotation.y = Math.atan2(faceDir.x, faceDir.z);
        }
        camera.position.copy(targetCamPos);
        currentCamLookAt.copy(targetCamLookAt);
        camera.lookAt(currentCamLookAt);
        camera.updateMatrixWorld(true);
        pathQueue = [];
        isWalking = false;
        if (currentStation !== "classes") {
          openProgress[currentStation] = 1;
        }
        notifyPhase(currentStation, "ready");
        positionLabels(holder.clientWidth, renderer.domElement.clientHeight);
        schedule();
      },
      setMotion(enabled) {
        motion = enabled;
        schedule();
      },
      setCustomizations(styles) {
        customizations = styles;
        people.forEach((person) =>
          models.applyStyle(person, person.accessories, styles[person.id] ?? defaultDeskStyle(person.id)),
        );
        schedule();
      },
      celebrate() {
        const now = performance.now();
        people.forEach((person) => {
          person.celebratedAt = now;
        });
        mascotGreeting = now;
        schedule();
      },
      greetMascot() {
        mascotGreeting = performance.now();
        schedule();
      },
      snapshot() {
        if (disposed || unavailable) return null;
        const rings = people.map((person) => ({ ring: person.ring.visible, disk: person.disk.material.opacity }));
        const size = renderer.getSize(new THREE.Vector2());
        const ratio = renderer.getPixelRatio();
        try {
          renderer.setPixelRatio(1);
          renderer.setSize(1440, 1080, false);
          frameCamera(1440, 1080);
          people.forEach((person) => {
            person.ring.visible = false;
            person.disk.material.opacity = 0;
            person.eyes.forEach((eye) => {
              eye.scale.y = 0.069;
            });
          });
          renderer.render(scene, camera);
          return renderer.domElement.toDataURL("image/png");
        } catch {
          return null;
        } finally {
          renderer.setPixelRatio(ratio);
          renderer.setSize(size.x, size.y, false);
          frameCamera(size.x, size.y);
          people.forEach((person, index) => {
            person.ring.visible = rings[index].ring;
            person.disk.material.opacity = rings[index].disk;
          });
          schedule();
        }
      },
      dispose,
    };
  } catch (error) {
    dispose();
    throw error;
  }
}
