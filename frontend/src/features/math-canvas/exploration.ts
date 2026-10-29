import type { CanvasSnapshot } from "./api";
import type { GraphCamera, GraphSettings } from "./expression";

/** Start a new exploration without mutating saved settings or claiming new source ink. */
export function createExplorationDraft(snapshot: Pick<CanvasSnapshot, "expression" | "note">, settings: GraphSettings, camera: GraphCamera) {
  return {
    source: snapshot.expression,
    note: snapshot.note,
    settings: { ...settings, parameters: { ...settings.parameters } },
    camera: { position: [...camera.position] as GraphCamera["position"], target: [...camera.target] as GraphCamera["target"], zoom: camera.zoom ?? 1 },
  };
}
