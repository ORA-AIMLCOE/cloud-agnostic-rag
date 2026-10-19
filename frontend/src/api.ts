export type Change = {
  path: string;
  reason?: string;
  reason_source?: "astra";
  kind: string;
  added: number;
  removed: number;
  diff: string;
};
export type Job = {
  id: string;
  repository_url: string;
  source_branch: string;
  status: string;
  phase: string;
  source_sha?: string;
  created_at: number;
  publish_allowed?: boolean;
  branch_url?: string;
  compare_url?: string;
  target_branch?: string;
  target_commit?: string;
  files: Change[];
  events: { time: number; message: string }[];
  checks: { name: string; status: string }[];
  analysis?: { components: string[]; protected_files: number; application?: string; prepared_knowledge?: boolean; integration_api?: boolean };
  metrics?: { modified: number; added: number; core_unchanged: number };
  validation_log?: string;
  cancel_requested?: boolean;
};
export type Status = {
  astra_configured: boolean;
  astra_model: string;
  retention_hours: number;
};
export async function api<T>(
  path: string,
  body?: unknown,
  method?: "DELETE",
): Promise<T> {
  const response = await fetch("/api" + path, {
    method: method ?? (body === undefined ? "GET" : "POST"),
    headers: { "Content-Type": "application/json", "X-Converter-Request": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.error || data.detail || "The request could not be completed.",
    );
  return data as T;
}
export async function download(id: string, kind: "configuration" | "source") {
  const response = await fetch(`/api/jobs/${id}/${kind}`, {
    headers: { "X-Converter-Request": "1" },
  });
  if (!response.ok) {
    const body = await response.json();
    throw new Error(body.error || body.detail || "Download failed.");
  }
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download =
    kind === "source" ? "oci-project.zip" : "oci-private-configuration.zip";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
