import { sampleImplicitGeometry } from "./geometry";
import type { SamplingRequest, SamplingResponse } from "./sampling-protocol";

// Keep the worker entry independent of the DOM and Three.js.
const scope = self as unknown as {
  onmessage: (event: MessageEvent<SamplingRequest>) => void;
  postMessage: (response: SamplingResponse, transfer?: Transferable[]) => void;
};
scope.onmessage = ({ data: request }) => {
  try {
    const sampled = sampleImplicitGeometry(request.model, request.settings, request.slice, request.resolution);
    const positions = new Float32Array(sampled.positions);
    scope.postMessage({ id: request.id, data: { ...sampled, positions } }, [positions.buffer]);
  } catch {
    scope.postMessage({ id: request.id, error: "Không thể lấy mẫu hình này. Thử thu hẹp miền hoặc sửa công thức." });
  }
};
