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
export type SendingProvider = "smtp" | "resend" | "sendgrid";
export interface SendingDomain {
  id: number;
  domain: string;
  provider?: SendingProvider;
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
  provider?: SendingProvider;
  api_key?: string;
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
// Automations (Phase 3 journeys)
// ---------------------------------------------------------------------------

export type AutomationStatus = "draft" | "active" | "paused";
export type TriggerType = "manual" | "list_subscribe";
export type StepType = "send" | "wait" | "condition";

export interface AutomationStep {
  id?: number;
  position?: number;
  type: StepType;
  config: Record<string, unknown>;
}

export interface Automation {
  id: number;
  name: string;
  status: AutomationStatus;
  trigger_type: TriggerType;
  trigger_list_id?: number | null;
  sending_domain_id?: number | null;
  from_name: string;
  from_email: string;
  steps: AutomationStep[];
}

export interface AutomationIn {
  name: string;
  trigger_type: TriggerType;
  trigger_list_id?: number | null;
  sending_domain_id?: number | null;
  from_name: string;
  from_email: string;
  steps: AutomationStep[];
}

export interface AutomationRun {
  id: number;
  contact_id: number;
  position: number;
  status: string;
  next_run_at: string | null;
  last_error: string | null;
}

export interface EnrollIn {
  contact_ids?: number[];
  segment_id?: number;
}
export interface EnrollOut {
  enrolled: number;
}

export interface AiSequenceEmail {
  subject: string;
  html: string;
  wait_days: number;
}
export interface AiSequenceOut {
  emails: AiSequenceEmail[];
}

export function listAutomations() {
  return api.get<Automation[]>("/api/automations");
}
export function getAutomation(id: number | string) {
  return api.get<Automation>(`/api/automations/${id}`);
}
export function createAutomation(input: AutomationIn) {
  return api.post<Automation>("/api/automations", input);
}
export function updateAutomation(id: number | string, input: AutomationIn) {
  return api.put<Automation>(`/api/automations/${id}`, input);
}
export function deleteAutomation(id: number | string) {
  return api.del<void>(`/api/automations/${id}`);
}
export function activateAutomation(id: number | string) {
  return api.post<Automation>(`/api/automations/${id}/activate`);
}
export function pauseAutomation(id: number | string) {
  return api.post<Automation>(`/api/automations/${id}/pause`);
}
export function enrollAutomation(id: number | string, input: EnrollIn) {
  return api.post<EnrollOut>(`/api/automations/${id}/enroll`, input);
}
export function getAutomationRuns(id: number | string) {
  return api.get<AutomationRun[]>(`/api/automations/${id}/runs`);
}
export function draftSequence(goal: string, steps: number) {
  return api.post<AiSequenceOut>("/api/ai/sequence", { goal, steps });
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

// ---------------------------------------------------------------------------
// Phase 4 — A/B variants & AI narrative
// ---------------------------------------------------------------------------

export interface VariantStats {
  variant_id: number;
  subject: string;
  weight: number;
  sent: number;
  unique_opens: number;
  unique_clicks: number;
  open_rate: number;
  click_rate: number;
}
export interface CampaignVariants {
  variants: VariantStats[];
  winner_variant_id: number | null;
}
export interface AnalyticsNarrative {
  summary: string;
  highlights: string[];
}

export function getCampaignVariants(id: number | string) {
  return api.get<CampaignVariants>(`/api/campaigns/${id}/variants`);
}
export function analyticsNarrative(id: number | string) {
  return api.post<AnalyticsNarrative>(
    `/api/campaigns/${id}/analytics/narrative`,
  );
}

// ---------------------------------------------------------------------------
// Phase 5 — Signup forms & outbound webhooks
// ---------------------------------------------------------------------------

export interface SignupForm {
  id: number;
  name: string;
  list_id?: number | null;
  sending_domain_id?: number | null;
  double_optin: boolean;
  success_message: string;
  redirect_url: string;
}
export interface SignupFormIn {
  name: string;
  list_id?: number | null;
  sending_domain_id?: number | null;
  double_optin?: boolean;
  success_message?: string;
  redirect_url?: string;
}

export function listForms() {
  return api.get<SignupForm[]>("/api/forms");
}
export function createForm(input: SignupFormIn) {
  return api.post<SignupForm>("/api/forms", input);
}
export function deleteForm(id: number | string) {
  return api.del<void>(`/api/forms/${id}`);
}

export interface OutboundWebhook {
  id: number;
  url: string;
  events: string;
  active: boolean;
}
export interface OutboundWebhookIn {
  url: string;
  events: string;
  active?: boolean;
}

export function listOutboundWebhooks() {
  return api.get<OutboundWebhook[]>("/api/outbound-webhooks");
}
export function createOutboundWebhook(input: OutboundWebhookIn) {
  return api.post<OutboundWebhook>("/api/outbound-webhooks", input);
}
export function deleteOutboundWebhook(id: number | string) {
  return api.del<void>(`/api/outbound-webhooks/${id}`);
}

// ---------------------------------------------------------------------------
// Phase 6 — Billing, members & audit logs
// ---------------------------------------------------------------------------

export interface BillingPlan {
  key: string;
  name: string;
  monthly_send_limit: number;
  price_usd: number;
}
export interface Billing {
  plan: string;
  monthly_send_limit: number;
  sent_this_month: number;
}
export interface CheckoutOut {
  checkout_url: string;
  applied: boolean;
  note: string;
}

export function getPlans() {
  return api.get<BillingPlan[]>("/api/billing/plans");
}
export function getBilling() {
  return api.get<Billing>("/api/billing");
}
export function checkout(plan: string) {
  return api.post<CheckoutOut>("/api/billing/checkout", { plan });
}

export interface Member {
  user_id: number;
  email: string;
  name: string | null;
  role: string;
}
export interface MemberIn {
  email: string;
  password: string;
  role: string;
}

export function listMembers() {
  return api.get<Member[]>("/api/members");
}
export function createMember(input: MemberIn) {
  return api.post<Member>("/api/members", input);
}
export function deleteMember(userId: number | string) {
  return api.del<void>(`/api/members/${userId}`);
}

export interface AuditLog {
  id: number;
  action: string;
  target: string;
  user_id: number;
  meta: Record<string, unknown> | null;
  created_at: string;
}

export function listAuditLogs() {
  return api.get<AuditLog[]>("/api/audit-logs");
}
