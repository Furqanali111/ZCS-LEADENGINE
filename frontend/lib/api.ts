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

export type Source = { key: string; name: string; status: string; notes: string | null };

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
};

export type Contact = {
  first_name: string | null;
  last_name: string | null;
  title: string | null;
  phone: string | null;
  role: string | null;
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
  updated_at: string;
  contact: Contact | null;
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
  search_job_id?: string;
};

export type ListLeadsParams = LeadFilters & {
  page?: number;
  page_size?: number;
  sort?: "score" | "name" | "updated";
  order?: "asc" | "desc";
};

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
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

export const patchLeadStatus = (id: string, crm_status: string) =>
  json<Lead>(`/api/leads/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ crm_status }),
  });

export async function exportLeads(body: { filters?: LeadFilters; ids?: string[] }): Promise<Blob> {
  return (await request("/api/exports/excel", post(body))).blob();
}
