export class ApiContractError extends Error {
  constructor(message: string, public readonly path = "response") {
    super(`${message} (${path})`);
    this.name = "ApiContractError";
  }
}

export function record(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ApiContractError("Expected an object", path);
  }
  return value as Record<string, unknown>;
}

export function string(value: unknown, path: string): string {
  if (typeof value !== "string") throw new ApiContractError("Expected a string", path);
  return value;
}

export function nonEmptyString(value: unknown, path: string): string {
  const result = string(value, path);
  if (!result.trim()) throw new ApiContractError("Expected a non-empty string", path);
  return result;
}

export function number(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ApiContractError("Expected a finite number", path);
  }
  return value;
}

export function integer(value: unknown, path: string): number {
  const result = number(value, path);
  if (!Number.isInteger(result)) throw new ApiContractError("Expected an integer", path);
  return result;
}

export function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new ApiContractError("Expected a boolean", path);
  return value;
}

export function array<T>(value: unknown, path: string, parse: (item: unknown, path: string) => T): T[] {
  if (!Array.isArray(value)) throw new ApiContractError("Expected an array", path);
  return value.map((item, index) => parse(item, `${path}[${index}]`));
}

export function nullable<T>(value: unknown, path: string, parse: (item: unknown, path: string) => T): T | null {
  return value === null ? null : parse(value, path);
}

export function optional<T>(value: unknown, path: string, parse: (item: unknown, path: string) => T): T | undefined {
  return value === undefined ? undefined : parse(value, path);
}

export function oneOf<T extends string>(value: unknown, path: string, values: readonly T[]): T {
  const parsed = string(value, path);
  if (!values.includes(parsed as T)) throw new ApiContractError(`Expected one of: ${values.join(", ")}`, path);
  return parsed as T;
}
