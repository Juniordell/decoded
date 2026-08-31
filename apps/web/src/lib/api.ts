import type { components } from "@/types/api";

export type PaperCard = components["schemas"]["PaperCard"];
export type PaperDetail = components["schemas"]["PaperDetail"];
export type FeedResponse = components["schemas"]["FeedResponse"];
export type SearchResponse = components["schemas"]["SearchResponse"];
export type SearchHit = components["schemas"]["SearchHit"];
export type TopicCard = components["schemas"]["TopicCard"];
export type TopicDetail = components["schemas"]["TopicDetail"];
export type TopicsListResponse = components["schemas"]["TopicsListResponse"];
export type PulseResponse = components["schemas"]["PulseResponse"];
export type AuthorCard = components["schemas"]["AuthorCard"];
export type AuthorDetail = components["schemas"]["AuthorDetail"];
export type InstitutionCard = components["schemas"]["InstitutionCard"];
export type InstitutionDetail = components["schemas"]["InstitutionDetail"];
export type PeopleListResponse = components["schemas"]["PeopleListResponse"];
export type TopicPoint = components["schemas"]["TopicPoint"];
export type InstitutionsListResponse =
  components["schemas"]["InstitutionsListResponse"];

const API_BASE = (() => {
  const configured = process.env.NEXT_PUBLIC_API_URL ?? "/api";

  // No browser, caminho relativo funciona (mesma origem, passa pelo rewrite)
  if (typeof window !== "undefined") {
    return configured.replace(/\/+$/, "");
  }

  // No servidor, precisa ser absoluta. Fala direto com a API, sem passar pelo rewrite.
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(
    /\/+$/,
    "",
  );
})();

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!res.ok) {
    throw new ApiError(`${res.status} ${res.statusText}`, res.status);
  }

  return res.json() as Promise<T>;
}

export const api = {
  async getFeed(
    params: {
      limit?: number;
      offset?: number;
      category?: string;
      decodedOnly?: boolean;
    } = {},
  ): Promise<FeedResponse> {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.offset) qs.set("offset", String(params.offset));
    if (params.category) qs.set("category", params.category);
    if (params.decodedOnly) qs.set("decoded_only", "true");

    return fetchJson<FeedResponse>(`/v1/papers?${qs}`);
  },

  async getPaper(arxivId: string): Promise<PaperDetail> {
    return fetchJson<PaperDetail>(`/v1/papers/${arxivId}`);
  },

  async search(params: {
    q: string;
    limit?: number;
    category?: string;
  }): Promise<SearchResponse> {
    const qs = new URLSearchParams({ q: params.q });
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.category) qs.set("category", params.category);

    return fetchJson<SearchResponse>(`/v1/search?${qs}`);
  },

  async getPulse(): Promise<PulseResponse> {
    return fetchJson<PulseResponse>("/v1/topics/pulse");
  },

  async getTopics(
    params: { sort?: string; limit?: number } = {},
  ): Promise<TopicsListResponse> {
    const qs = new URLSearchParams();
    if (params.sort) qs.set("sort", params.sort);
    if (params.limit) qs.set("limit", String(params.limit));
    return fetchJson<TopicsListResponse>(`/v1/topics?${qs}`);
  },

  async getTopic(slug: string, weeks = 12): Promise<TopicDetail> {
    return fetchJson<TopicDetail>(`/v1/topics/${slug}?weeks=${weeks}`);
  },

  async getAuthors(limit = 50): Promise<PeopleListResponse> {
    return fetchJson<PeopleListResponse>(`/v1/authors?limit=${limit}`);
  },

  async getAuthor(slug: string): Promise<AuthorDetail> {
    return fetchJson<AuthorDetail>(`/v1/authors/${slug}`);
  },

  async getInstitutions(limit = 50): Promise<InstitutionsListResponse> {
    return fetchJson<InstitutionsListResponse>(
      `/v1/institutions?limit=${limit}`,
    );
  },

  async getInstitution(slug: string): Promise<InstitutionDetail> {
    return fetchJson<InstitutionDetail>(`/v1/institutions/${slug}`);
  },
};

export { ApiError };
