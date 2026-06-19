// Typed fetch wrapper for the iceReach API.
//
// - Always sends credentials so the httpOnly session cookie rides along.
// - For mutating methods (POST/PATCH/PUT/DELETE) it reads the readable `ice_csrf`
//   cookie and echoes it back in the `X-CSRF-Token` header (double-submit CSRF).
// - Throws ApiError carrying the server's {detail} on any non-2xx response.

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const MUTATING = new Set(["POST", "PATCH", "PUT", "DELETE"]);

function readCookie(name: string): string {
  const prefix = name + "=";
  for (const part of document.cookie.split(";")) {
    const c = part.trim();
    if (c.startsWith(prefix)) return decodeURIComponent(c.slice(prefix.length));
  }
  return "";
}

type RequestBody = unknown;

interface RequestOpts {
  method?: string;
  body?: RequestBody;
  // When set, the body is sent as-is (e.g. FormData) without JSON encoding.
  raw?: boolean;
}

async function request<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;

  if (opts.body !== undefined) {
    if (opts.raw) {
      body = opts.body as BodyInit;
    } else {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.body);
    }
  }

  if (MUTATING.has(method)) {
    const csrf = readCookie("ice_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }

  const res = await fetch(path, {
    method,
    headers,
    body,
    credentials: "include",
  });

  if (res.status === 204) {
    return undefined as T;
  }

  let payload: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!res.ok) {
    const detail =
      (payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : null) ||
      (typeof payload === "string" && payload) ||
      res.statusText ||
      "Request failed";
    throw new ApiError(res.status, detail);
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: RequestBody) => request<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: RequestBody) => request<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: RequestBody) => request<T>(path, { method: "PATCH", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form, raw: true }),
};

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

export interface User {
  id: number;
  email: string;
  name: string | null;
}
export interface Workspace {
  id: number;
  name: string;
  slug: string;
}
export interface Me {
  user: User;
  workspace: Workspace;
  role: string;
}

export type ContactStatus = string;
export interface Contact {
  id: number;
  email: string;
  name: string | null;
  attributes: Record<string, unknown>;
  status: ContactStatus;
}
export interface ContactIn {
  email: string;
  name?: string;
  attributes?: Record<string, unknown>;
}

export interface List {
  id: number;
  name: string;
  description: string | null;
}
export interface ListIn {
  name: string;
  description?: string;
}

export interface SegmentRules {
  match?: "all" | "any";
  conditions?: Array<{ field: string; op: string; value: unknown }>;
  [k: string]: unknown;
}
export interface Segment {
  id: number;
  name: string;
  rules: SegmentRules;
}
export interface SegmentIn {
  name: string;
  rules: SegmentRules;
}
export interface SegmentPreview {
  count: number;
  sample: string[];
}

export interface Variant {
  id?: number;
  subject: string;
  html: string;
  text?: string;
  weight?: number;
}
export interface Campaign {
  id: number;
  name: string;
  status: string;
  from_name: string;
  from_email: string;
  sending_domain_id: number | null;
  list_id: number | null;
  segment_id: number | null;
  variants: Variant[];
}
export interface CampaignIn {
  name: string;
  from_name: string;
  from_email?: string;
  sending_domain_id?: number | null;
  list_id?: number | null;
  segment_id?: number | null;
  variants: Variant[];
}

export interface CampaignAnalytics {
  sent: number;
  hard_bounce: number;
  soft_bounce: number;
  unique_opens: number;
  total_opens: number;
  unique_clicks: number;
  total_clicks: number;
  ctr: number;
  ctor: number;
  unsubscribes: number;
  delivered: number | null;
  complaints: number | null;
}

export type JobStatus = "queued" | "running" | "done" | "failed";
export interface Job {
  id: number;
  type: string;
  status: JobStatus;
  progress: number;
  message: string;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface DnsRecord {
  type: string;
  host: string;
  value: string;
  purpose: string;
}
export interface SendingDomain {
  id: number;
  domain: string;
  dkim_selector?: string;
  spf_verified?: boolean;
  dkim_verified?: boolean;
  dmarc_verified?: boolean;
  status?: string;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_username?: string | null;
}
export interface SendingDomainIn {
  domain: string;
  smtp_host?: string;
  smtp_port?: number;
  smtp_username?: string;
  smtp_password?: string;
}
export interface SendingDomainCreated {
  domain: SendingDomain;
  records: DnsRecord[];
}

export interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  scopes: string[];
}
export interface ApiKeyCreated extends ApiKey {
  token: string;
}

// ---------------------------------------------------------------------------
// Email templates (Phase 2 builder)
// ---------------------------------------------------------------------------

export type BlockAlign = "left" | "center" | "right";

export interface HeadingBlock {
  type: "heading";
  text: string;
  level: 1 | 2 | 3;
  align?: BlockAlign;
}
export interface TextBlock {
  type: "text";
  html: string;
  align?: BlockAlign;
}
export interface ButtonBlock {
  type: "button";
  text: string;
  url: string;
  align?: BlockAlign;
  bg?: string;
  color?: string;
}
export interface ImageBlock {
  type: "image";
  src: string;
  alt?: string;
  href?: string;
  width?: number;
}
export interface DividerBlock {
  type: "divider";
}
export interface SpacerBlock {
  type: "spacer";
  height: number;
}
export interface ColumnsBlock {
  type: "columns";
  columns: [Block[], Block[]];
}

export type Block =
  | HeadingBlock
  | TextBlock
  | ButtonBlock
  | ImageBlock
  | DividerBlock
  | SpacerBlock
  | ColumnsBlock;

export type BlockType = Block["type"];

export interface Template {
  id: number;
  name: string;
  subject: string;
  blocks: Block[];
  html: string;
  text: string;
  updated_at?: string;
}
export interface TemplateIn {
  name: string;
  subject: string;
  blocks: Block[];
  preheader?: string;
}

export interface RenderOut {
  html: string;
  text: string;
}
export interface RenderIn {
  blocks: Block[];
  preheader?: string;
}

export interface TestSendIn {
  to_email: string;
  sending_domain_id: number;
  subject?: string;
}
export interface TestSendOut {
  sent: boolean;
}

export interface SavedBlock {
  id: number;
  name: string;
  block: Block;
}
export interface SavedBlockIn {
  name: string;
  block: Block;
}

export function listTemplates() {
  return api.get<Template[]>("/api/templates");
}
export function getTemplate(id: number | string) {
  return api.get<Template>(`/api/templates/${id}`);
}
export function createTemplate(input: TemplateIn) {
  return api.post<Template>("/api/templates", input);
}
export function updateTemplate(id: number | string, input: TemplateIn) {
  return api.put<Template>(`/api/templates/${id}`, input);
}
export function deleteTemplate(id: number | string) {
  return api.del<void>(`/api/templates/${id}`);
}
export function renderBlocks(input: RenderIn) {
  return api.post<RenderOut>("/api/templates/render", input);
}
export function renderTemplate(id: number | string) {
  return api.get<RenderOut>(`/api/templates/${id}/render`);
}
export function testSendTemplate(id: number | string, input: TestSendIn) {
  return api.post<TestSendOut>(`/api/templates/${id}/test-send`, input);
}

export function listSavedBlocks() {
  return api.get<SavedBlock[]>("/api/saved-blocks");
}
export function createSavedBlock(input: SavedBlockIn) {
  return api.post<SavedBlock>("/api/saved-blocks", input);
}
export function deleteSavedBlock(id: number | string) {
  return api.del<void>(`/api/saved-blocks/${id}`);
}

export interface AiSubject {
  subject: string;
  preheader: string;
  rationale: string;
}
export interface AiSubjectsOut {
  variants: AiSubject[];
}
export interface AiBodyOut {
  html: string;
  text: string;
}
export interface AiCritiqueOut {
  spam_risk: string | number;
  issues: string[];
  suggestions: string[];
}

// ---------------------------------------------------------------------------
// Job polling
// ---------------------------------------------------------------------------

export async function pollJob(
  jobId: number,
  onProgress: (job: Job) => void,
  intervalMs = 1200,
): Promise<Job> {
  // Resolves when the job reaches a terminal state (done/failed).
  return new Promise<Job>((resolve, reject) => {
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      try {
        const job = await api.get<Job>(`/api/jobs/${jobId}`);
        onProgress(job);
        if (job.status === "done" || job.status === "failed") {
          resolve(job);
          return;
        }
        window.setTimeout(tick, intervalMs);
      } catch (err) {
        cancelled = true;
        reject(err);
      }
    };
    tick();
  });
}
