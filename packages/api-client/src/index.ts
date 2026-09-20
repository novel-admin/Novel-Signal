export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type ApiErrorBody = {
  code?: string;
  message?: string;
  details?: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, body: ApiErrorBody = {}) {
    super(body.message ?? `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code ?? "request_failed";
    this.details = body.details;
  }
}

export type CursorPage<T> = {
  items: T[];
  next_cursor?: string | null;
  total?: number;
};

export type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  token?: string;
};

type AccessTokenProvider = () => Promise<string | null>;
let accessTokenProvider: AccessTokenProvider | undefined;

/** Register the browser session token source once at the application boundary. */
export function setAccessTokenProvider(provider: AccessTokenProvider): void {
  accessTokenProvider = provider;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, token: suppliedToken, headers, ...init } = options;
  const token = suppliedToken ?? (await accessTokenProvider?.());
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    let error: ApiErrorBody = {};
    try {
      error = (await response.json()) as ApiErrorBody;
    } catch {
      // Preserve the HTTP status when the server returned no JSON body.
    }
    throw new ApiError(response.status, error);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const token = await accessTokenProvider?.();
  const url = path.startsWith("http://") || path.startsWith("https://")
    ? path
    : `${apiBaseUrl}${path}`;
  const response = await fetch(url, {
    credentials: "include",
    headers: {
      Accept: "text/csv",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!response.ok) {
    let error: ApiErrorBody = {};
    try {
      error = (await response.json()) as ApiErrorBody;
    } catch {
      // Preserve the HTTP status when the server returned no JSON body.
    }
    throw new ApiError(response.status, error);
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(objectUrl);
}

export function withCursor(path: string, cursor?: string | null): string {
  if (!cursor) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}cursor=${encodeURIComponent(cursor)}`;
}

export async function getAllPages<T>(path: string, token?: string): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null | undefined;
  do {
    const page = await request<CursorPage<T>>(withCursor(path, cursor), { token });
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return items;
}

export type ModuleMeta = {
  module: string;
  owner: "Akanksh" | "Palguna";
  status: "scaffolded";
};
