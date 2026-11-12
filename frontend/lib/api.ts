import { getName } from "@/lib/me";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  code: string;
  status: number;
  fields: Record<string, string>;
  constructor(code: string, message: string, status = 0, fields: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.fields = fields;
  }
}

export type Source = { key: string; name: string; status: string; notes: string | null; key_missing: boolean };

export type Counters = {
  candidates_seen?: number;
  accepted_new?: number;
  accepted_existing?: number;
  skipped_excluded?: number;
  skipped_inactive?: number;
  skipped_not_sole_proprietor?: number;
  skipped_works_at_known_org?: number;
  pages_fetched?: number;
  source_failures?: number;
  websites_found?: number;
  no_website_found?: number;
  emails_found?: number;
  people_found?: number;
  enrich_attempted?: number;
  enrich_failures?: number;
  skipped?: number;
};

export type Job = {
  id: string;
  specialty: string;
  state: string;
  city: string | null;
  target_count: number;
  include_practices: boolean;
  include_solo: boolean;
  include_subparts: boolean;
  include_hospitals: boolean;
  sources: string[];
  enrich: boolean;
  status: string;
  counters: Counters;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type SearchInput = {
  specialty: string;
  state: string;
  city?: string | null;
  target_count: number;
  include_practices: boolean;
  include_solo: boolean;
  include_subparts: boolean;
  include_hospitals: boolean;
  sources: string[];
  enrich?: boolean;
};

export type Contact = {
  first_name: string | null;
  last_name: string | null;
  title: string | null;
  phone: string | null;
  role: string | null;
  email: string | null;
  email_status: string | null;
  source_url: string | null;
  collected_at: string | null;
};

export type LeadLocation = {
  purpose: string | null;
  address_1: string | null;
  address_2: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  phone: string | null;
  is_primary: boolean;
};

export type Lead = {
  id: string;
  npi: string;
  name: string;
  dba_name: string | null;
  organization_type: string;
  parent_organization_name: string | null;
  primary_taxonomy_desc: string | null;
  phone: string | null;
  fax: string | null;
  city: string | null;
  state: string | null;
  fit_score: number | null;
  priority: string | null;
  crm_status: string;
  owner: string | null;
  last_contacted_at: string | null;
  next_follow_up_at: string | null;
  suppressed: boolean;
  updated_at: string;
  website: string | null;
  enrichment_status: string;
  website_evidence: { page_url?: string; check?: string; checked_at?: string } | null;
  primary_email: string | null;
  contact: Contact | null;
  contacts: Contact[];
  locations: LeadLocation[];
  score: { components: Record<string, unknown>; config_version: string; calculated_at: string } | null;
  source: { source_key: string; collected_at: string } | null;
};

export type LeadPage = { items: Lead[]; total: number; page: number; page_size: number };

export type LeadFilters = {
  q?: string;
  state?: string;
  specialty?: string;
  organization_type?: string;
  priority?: string;
  min_score?: number;
  crm_status?: string;
  owner?: string;
  search_job_id?: string;
  follow_up?: "due" | "overdue" | "none";
  has_website?: "true";
  has_email?: "true";
};

export type ListLeadsParams = LeadFilters & {
  page?: number;
  page_size?: number;
  sort?: "score" | "name" | "updated" | "follow_up" | "email" | "website";
  order?: "asc" | "desc";
};

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  const who = getName();
  try {
    res = await fetch(`${BASE}${path}`, who ? { ...init, headers: { ...init?.headers, "X-Salesperson": encodeURIComponent(who) } } : init);
  } catch {
    throw new ApiError("network_error", "Cannot reach the backend. Is it running on " + BASE + "?");
  }
  if (!res.ok) {
    let code = "http_error";
    let message = `Request failed (${res.status})`;
    let fields: Record<string, string> = {};
    try {
      const body = await res.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        // optional per-field messages, {field: text}, if the backend sends them
        if (body.error.fields && typeof body.error.fields === "object") fields = body.error.fields;
      } else if (Array.isArray(body?.detail)) {
        // FastAPI default validation shape, in case a 422 bypasses the handler
        code = "validation_error";
        message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
        for (const d of body.detail as { loc: (string | number)[]; msg: string }[]) {
          const f = d.loc?.[d.loc.length - 1];
          if (typeof f === "string") fields[f] = d.msg;
        }
      }
    } catch {
      // body was not JSON; keep the generic message
    }
    throw new ApiError(code, message, res.status, fields);
  }
  return res;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request(path, init)).json() as Promise<T>;
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const getSources = () => json<Source[]>("/api/sources");
export const createSearch = (input: SearchInput) => json<Job>("/api/search", post(input));
export type SearchProgress = { leads_fetched: number; exhausted: boolean };
export type ProgressKey = { specialty: string; state: string; city: string; subparts: boolean; hospitals: boolean };
const progressQuery = (k: ProgressKey) =>
  new URLSearchParams({
    specialty: k.specialty,
    state: k.state,
    ...(k.city && { city: k.city }),
    include_subparts: String(k.subparts),
    include_hospitals: String(k.hospitals),
  }).toString();
export const getSearchProgress = (k: ProgressKey) => json<SearchProgress>(`/api/search/progress?${progressQuery(k)}`);
export const resetSearchProgress = async (k: ProgressKey) => {
  await request(`/api/search/progress?${progressQuery(k)}`, { method: "DELETE" });
};
export const listJobs = () => json<Job[]>("/api/search");
export const cancelJob = (id: string) => json<Job>(`/api/search/${id}/cancel`, post());
export const resumeJob = (id: string) => json<Job>(`/api/search/${id}/resume`, post());

export function listLeads(params: ListLeadsParams = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  }
  return json<LeadPage>(`/api/leads?${qs}`);
}

export type LeadPatch = { crm_status?: string; next_follow_up_at?: string | null; reject_website?: true };

export const patchLead = (id: string, body: LeadPatch) =>
  json<Lead>(`/api/leads/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const claimLead = (id: string) => json<Lead>(`/api/leads/${id}/claim`, post());
export const releaseLead = (id: string) => json<Lead>(`/api/leads/${id}/release`, post());
export const listOwners = () => json<string[]>("/api/owners");

export const patchLeadStatus = (id: string, crm_status: string) => patchLead(id, { crm_status });

export const getLead = (id: string) => json<Lead>(`/api/leads/${id}`);

export type Activity = {
  id: string;
  type: string;
  occurred_at: string;
  summary: string | null;
  outcome: string | null;
  from_status: string | null;
  to_status: string | null;
  actor?: string | null;
  created_at: string;
};

export type ActivityInput = {
  type: string;
  occurred_at?: string;
  summary?: string;
  outcome?: string | null;
  next_follow_up_at?: string | null;
};

export type ActivityPage = { items: Activity[]; total: number; page: number; page_size: number };

export const listActivities = (id: string, page = 1) =>
  json<ActivityPage>(`/api/leads/${id}/activities?page=${page}`);

export const addActivity = (id: string, body: ActivityInput) =>
  json<Activity>(`/api/leads/${id}/activities`, post(body));

export type PipelineCard = {
  id: string;
  name: string;
  city: string | null;
  state: string | null;
  organization_type: string;
  fit_score: number | null;
  priority: string | null;
  owner?: string | null;
  next_follow_up_at: string | null;
  last_contacted_at: string | null;
};

export type PipelineColumn = { status: string; count: number; leads: PipelineCard[] };

export const getPipeline = (limit = 20) =>
  json<{ columns: PipelineColumn[] }>(`/api/pipeline?limit=${limit}`);

export const getPipelineColumn = (status: string, offset: number, limit = 20) =>
  json<PipelineColumn>(`/api/pipeline/${status}?offset=${offset}&limit=${limit}`);

export type CountItem = { key: string; count: number };

export type DashboardStats = {
  range: { from: string; to: string };
  total: number;
  new_leads: number;
  critical_high: number;
  follow_ups_due: number;
  meetings_scheduled: number;
  converted: number;
  by_state: CountItem[];
  by_specialty: CountItem[];
  by_status: CountItem[];
  recent_jobs: Job[];
  conversion: { converted: number; contacted: number; rate: number | null };
};

export function getDashboard(range: { from?: string; to?: string } = {}) {
  const qs = new URLSearchParams();
  if (range.from) qs.set("from", range.from);
  if (range.to) qs.set("to", range.to);
  return json<DashboardStats>(`/api/dashboard/stats?${qs}`);
}

export type SuppressionEntry = {
  id: string;
  kind: string;
  value: string;
  reason: string | null;
  created_at: string;
};

export const listSuppression = () => json<SuppressionEntry[]>("/api/suppression");

export const addSuppression = (body: { kind: string; value: string; reason?: string }) =>
  json<SuppressionEntry>("/api/suppression", post(body));

export const removeSuppression = async (id: string) => {
  await request(`/api/suppression/${id}`, { method: "DELETE" });
};

export type OutreachTemplate = {
  id: string;
  name: string;
  kind: "email" | "call";
  subject: string | null;
  body: string;
  created_at: string;
  updated_at: string;
};
export type TemplateInput = { name: string; kind: "email" | "call"; subject?: string | null; body: string };

const send = (method: string, body: unknown): RequestInit => ({ ...post(body), method });

export const listTemplates = () => json<OutreachTemplate[]>("/api/templates");
export const createTemplate = (body: TemplateInput) => json<OutreachTemplate>("/api/templates", post(body));
export const updateTemplate = (id: string, body: Partial<TemplateInput>) =>
  json<OutreachTemplate>(`/api/templates/${id}`, send("PATCH", body));
export const deleteTemplate = async (id: string) => {
  await request(`/api/templates/${id}`, { method: "DELETE" });
};

// Returns the blob and the filename from Content-Disposition.
export async function exportLeadsFile(body: { filters?: LeadFilters; ids?: string[] }) {
  const res = await request("/api/exports/excel", post(body));
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(res.headers.get("Content-Disposition") ?? "");
  return { blob: await res.blob(), filename: m ? decodeURIComponent(m[1]) : "zcs-leads.xlsx" };
}

// related leads
export type RelatedLead = {
  id: string;
  name: string;
  city: string | null;
  state: string | null;
  crm_status: string;
  owner: string | null;
  fit_score: number | null;
  priority: string | null;
  reasons: string[];
};
export const getRelatedLeads = (id: string) => json<RelatedLead[]>(`/api/leads/${id}/related`);
