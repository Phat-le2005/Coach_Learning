import type { GraphSettings, MathExpression } from "./expression";

export interface SamplingInput { model: MathExpression; settings: GraphSettings; slice: boolean; resolution: number }
export interface SamplingRequest extends SamplingInput { id: number }
export interface SamplingData { positions: Float32Array; primitive: "triangles" | "segments"; truncated: boolean }
export type SamplingResponse = { id: number; data: SamplingData } | { id: number; error: string };

/** At most one running job and one replacement. Old frames never replace newer inputs. */
export class GraphSamplingQueue {
  private sequence = 0;
  private active: number | null = null;
  private pending: SamplingRequest | null = null;
  private disposed = false;

  constructor(private send: (request: SamplingRequest) => void, private deliver: (data: SamplingData) => void,
    private reportError: (message: string) => void) {}

  request(input: SamplingInput): void {
    if (this.disposed) return;
    const request = { ...input, id: ++this.sequence };
    if (this.active !== null) this.pending = request;
    else this.start(request);
  }

  accept(response: SamplingResponse): void {
    if (this.disposed || response.id !== this.active) return;
    this.active = null;
    if (this.pending) {
      const latest = this.pending; this.pending = null; this.start(latest);
    } else if (response.id === this.sequence) {
      if ("error" in response) this.reportError(response.error); else this.deliver(response.data);
    }
  }

  dispose(): void { this.disposed = true; this.pending = null; }
  private start(request: SamplingRequest): void { this.active = request.id; this.send(request); }
}
