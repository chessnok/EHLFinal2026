// Typed client for the backend. Requests go to /api/*, which Next.js rewrites to the backend
// (see next.config.ts), so the browser never needs the backend's address.

export type Item = {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type ItemPage = { items: Item[]; total: number };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : response.statusText;
    throw new ApiError(response.status, detail);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; database: string }>("/health"),
  listItems: () => request<ItemPage>("/items"),
  createItem: (data: { name: string; description?: string }) =>
    request<Item>("/items", { method: "POST", body: JSON.stringify(data) }),
  deleteItem: (id: number) => request<void>(`/items/${id}`, { method: "DELETE" }),
};
