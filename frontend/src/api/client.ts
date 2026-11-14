/**
 * The only module that talks to the server. Every call goes through `send`,
 * so the error envelope is parsed in one place and no caller sees a raw
 * Response. Text from the API is data, never markup: nothing here sets HTML.
 */
import type { paths } from "./schema";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(
    code: string,
    message: string,
    status: number,
    details: Record<string, unknown> = {},
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Plain-language message for the error state. Never the raw payload. */
export function errorMessage(error: unknown): string {
  if (isApiError(error)) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

type Method = "get" | "post" | "put" | "patch" | "delete";

type Op<P extends keyof paths, M extends Method> = M extends keyof paths[P]
  ? paths[P][M]
  : never;
type JsonBody<T> = T extends { content: { "application/json": infer B } }
  ? B
  : never;
type AtStatus<O, C extends number> = O extends { responses: infer R }
  ? C extends keyof R
    ? JsonBody<R[C]>
    : never
  : never;

export type ResponseOf<
  P extends keyof paths,
  M extends Method,
  C extends number = 200,
> = AtStatus<Op<P, M>, C>;

export type BodyOf<P extends keyof paths, M extends Method> =
  Op<P, M> extends { requestBody: { content: { "application/json": infer B } } }
    ? B
    : never;

export type PathParamsOf<P extends keyof paths, M extends Method> =
  Op<P, M> extends { parameters: { path: infer X } } ? X : never;

export type QueryOf<P extends keyof paths, M extends Method> =
  Op<P, M> extends { parameters: { query?: infer Q } } ? Q : never;

/** Required bodies must stay required; GET and DELETE carry no body at all. */
type BodyField<P extends keyof paths, M extends Method> =
  Op<P, M> extends { requestBody: { content: { "application/json": unknown } } }
    ? { body: BodyOf<P, M> }
    : { body?: undefined };

type Call<P extends keyof paths, M extends Method> = {
  params?: PathParamsOf<P, M>;
  query?: QueryOf<P, M>;
  signal?: AbortSignal;
} & BodyField<P, M>;

function fillPath(
  path: string,
  params: Record<string, string> | undefined,
): string {
  if (!params) return path;
  return path.replace(/\{(\w+)\}/g, (_match, key: string) => {
    const value = params[key];
    if (value === undefined)
      throw new ApiError("CLIENT_BUG", `Missing path value: ${key}`, 0);
    return encodeURIComponent(value);
  });
}

function fillQuery(query: Record<string, unknown> | undefined): string {
  if (!query) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function toApiError(payload: unknown, response: Response): ApiError {
  const envelope = (payload ?? {}) as Record<string, unknown>;
  // Every error this API raises carries a `code`. A body without one did not
  // come from the API (a dead dev proxy answers 500 with an empty body), so
  // report the thing the user can act on instead of echoing "500".
  if (typeof envelope.code !== "string") {
    return new ApiError(
      "UNREACHABLE",
      "Cannot reach the local server.",
      response.status,
    );
  }
  const code = envelope.code;
  const message =
    typeof envelope.message === "string" && envelope.message
      ? envelope.message
      : `${response.status} ${response.statusText}`.trim();
  const details =
    envelope.details && typeof envelope.details === "object"
      ? (envelope.details as Record<string, unknown>)
      : {};
  const requestId =
    typeof envelope.request_id === "string" ? envelope.request_id : null;
  return new ApiError(code, message, response.status, details, requestId);
}

async function send(
  path: string,
  method: string,
  options: {
    json?: unknown;
    form?: FormData;
    signal?: AbortSignal;
    accept?: string;
  } = {},
): Promise<Response> {
  const headers: Record<string, string> = {
    accept: options.accept ?? "application/json",
  };
  let body: BodyInit | undefined;
  if (options.form) {
    // The browser owns the multipart boundary; setting the header would break it.
    body = options.form;
  } else if (options.json !== undefined) {
    headers["content-type"] = "application/json";
    body = JSON.stringify(options.json);
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body,
      signal: options.signal ?? null,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError")
      throw cause;
    throw new ApiError("NETWORK_ERROR", "Cannot reach the local server.", 0);
  }

  if (!response.ok) throw toApiError(await parseJson(response), response);
  return response;
}

async function readJson<T>(
  path: string,
  method: string,
  options: Parameters<typeof send>[2],
) {
  const response = await send(path, method, options);
  return (await parseJson(response)) as T;
}

function callOptions<P extends keyof paths, M extends Method>(
  call: Call<P, M>,
) {
  return {
    json: call.body,
    signal: call.signal,
  };
}

/** The one cast in this file: an omitted call carries no body by definition. */
function noCall<P extends keyof paths, M extends Method>(): Call<P, M> {
  return {} as Call<P, M>;
}

export const api = {
  get<P extends keyof paths>(
    path: P,
    call?: Call<P, "get">,
  ): Promise<ResponseOf<P, "get">> {
    const options = call ?? noCall<P, "get">();
    const url = fillPath(
      path,
      options.params as Record<string, string> | undefined,
    );
    return readJson<ResponseOf<P, "get">>(
      url + fillQuery(options.query as Record<string, unknown> | undefined),
      "GET",
      { signal: options.signal },
    );
  },

  post<P extends keyof paths, C extends number = 200>(
    path: P,
    call?: Call<P, "post">,
  ): Promise<ResponseOf<P, "post", C>> {
    const options = call ?? noCall<P, "post">();
    const url = fillPath(
      path,
      options.params as Record<string, string> | undefined,
    );
    return readJson<ResponseOf<P, "post", C>>(
      url,
      "POST",
      callOptions(options),
    );
  },

  put<P extends keyof paths, C extends number = 200>(
    path: P,
    call?: Call<P, "put">,
  ): Promise<ResponseOf<P, "put", C>> {
    const options = call ?? noCall<P, "put">();
    const url = fillPath(
      path,
      options.params as Record<string, string> | undefined,
    );
    return readJson<ResponseOf<P, "put", C>>(url, "PUT", callOptions(options));
  },

  patch<P extends keyof paths, C extends number = 200>(
    path: P,
    call?: Call<P, "patch">,
  ): Promise<ResponseOf<P, "patch", C>> {
    const options = call ?? noCall<P, "patch">();
    const url = fillPath(
      path,
      options.params as Record<string, string> | undefined,
    );
    return readJson<ResponseOf<P, "patch", C>>(
      url,
      "PATCH",
      callOptions(options),
    );
  },

  /** Multipart upload: a CV file plus an optional note. */
  postForm<P extends keyof paths, C extends number = 201>(
    path: P,
    form: FormData,
    call: { params?: PathParamsOf<P, "post">; signal?: AbortSignal } = {},
  ): Promise<ResponseOf<P, "post", C>> {
    const url = fillPath(
      path,
      call.params as Record<string, string> | undefined,
    );
    return readJson<ResponseOf<P, "post", C>>(url, "POST", {
      form,
      signal: call.signal,
    });
  },

  /** Markdown export and anything else served as text. */
  async text(path: string, signal?: AbortSignal): Promise<string> {
    const response = await send(path, "GET", {
      accept: "text/markdown",
      signal,
    });
    return response.text();
  },
};
