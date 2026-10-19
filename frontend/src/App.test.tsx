// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "./App";
import { api } from "./api";
vi.mock("./api", () => ({ api: vi.fn(), download: vi.fn() }));
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  window.location.hash = "";
  window.localStorage.clear();
});
const job = {
  id: "abc",
  repository_url: "https://github.com/team/aws_rag",
  source_branch: "main",
  status: "ready",
  phase: "Repository inspected",
  created_at: 1,
  publish_allowed: true,
  files: [],
  events: [],
  checks: [],
};
test("inspects repository and keeps conversion blocked until Astra is configured", async () => {
  vi.mocked(api).mockImplementation(async (path, body) =>
    path === "/status"
      ? {
          astra_configured: false,
          astra_model: "gpt-6-astra",
          retention_hours: 24,
        }
      : body
        ? job
        : ([] as any),
  );
  render(<App />);
  await waitFor(() => expect(api).toHaveBeenCalledWith("/target-defaults"));
  expect(screen.queryByText("Waiting for endpoint details")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("GitHub repository"), {
    target: { value: "https://github.com/team/aws_rag" },
  });
  fireEvent.change(screen.getByLabelText(/GitHub access token/), {
    target: { value: "test-token" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Inspect repository/ }));
  await screen.findByText("Connect your OCI components");
  expect(screen.getByRole("button", { name: /CONVERT TO OCI/ })).toBeDisabled();
  expect(screen.getByLabelText("LLM model or endpoint ID")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("LLM API format"), {
    target: { value: "generic_astra" },
  });
  expect(screen.getByLabelText("LLM API format")).toHaveValue("generic_astra");
  expect(
    screen.getByLabelText("Embedding model or endpoint ID"),
  ).toBeInTheDocument();
  expect(screen.getByLabelText(/Database connection string/)).toBeRequired();
  expect(screen.getByLabelText("Database username")).toBeRequired();
  expect(screen.getByLabelText("Database password")).toHaveAttribute(
    "type",
    "password",
  );
  expect(
    screen.getByLabelText(/Wallet directory on runtime machine/),
  ).not.toBeRequired();
  expect(
    screen.queryByLabelText(/PostgreSQL connection URL/),
  ).not.toBeInTheDocument();
  expect(window.localStorage.getItem("test-token")).toBeNull();
});
test("renders failures without claiming successful conversion", async () => {
  window.location.hash = "abc";
  vi.mocked(api).mockImplementation(async (path) =>
    path === "/status"
      ? { astra_configured: true, astra_model: "model", retention_hours: 24 }
      : ([
          { ...job, status: "failed", phase: "Offline validation failed." },
        ] as any),
  );
  render(<App />);
  await screen.findByText("Conversion needs attention.");
  expect(
    screen.queryByText("Your OCI project is ready to review."),
  ).not.toBeInTheDocument();
});
test("shows actual file diffs and separates live verification", async () => {
  window.location.hash = "abc";
  const completed = {
    ...job,
    status: "completed",
    phase: "Code validated",
    analysis: { components: [], protected_files: 50, prepared_knowledge: true, integration_api: true },
    files: [
      {
        path: "backend/app/providers/oci/llm.py",
        kind: "modified",
        added: 1,
        removed: 1,
        diff: "-old\n+new",
      },
    ],
    checks: [{ name: "Live OCI access and RAG", status: "not_run" }],
  };
  vi.mocked(api).mockImplementation(async (path) =>
    path === "/status"
      ? { astra_configured: true, astra_model: "model", retention_hours: 24 }
      : ([completed] as any),
  );
  render(<App />);
  await screen.findByText("Your OCI project is ready to review.");
  expect(screen.getByText(/initialize Oracle and ingest the distributor/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: /Code changes/ }));
  expect(screen.getByText("new")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Validation" }));
  expect(screen.getByText("not run")).toBeInTheDocument();
});

function history(status = "failed", rejectDelete = false) {
  window.location.hash = "abc";
  vi.mocked(api).mockImplementation(async (path, _body, method) => {
    if (method === "DELETE") {
      if (rejectDelete) throw new Error("Local files are in use.");
      return { deleted: "abc" } as any;
    }
    return (
      path === "/status"
        ? { astra_configured: true, astra_model: "model", retention_hours: 24 }
        : [
            {
              ...job,
              status,
              events: [
                { time: 1, message: "Reading source" },
                { time: 2, message: "Validation stopped" },
              ],
            },
          ]
    ) as any;
  });
}

test("deletion requires confirmation and clears the selected conversion", async () => {
  history();
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: /Delete conversion aws_rag/ }),
  );
  expect(screen.getByRole("dialog")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Keep conversion" }));
  expect(api).not.toHaveBeenCalledWith("/jobs/abc", undefined, "DELETE");
  fireEvent.click(
    screen.getByRole("button", { name: /Delete conversion aws_rag/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Delete conversion" }));
  await screen.findByText("Your conversions will appear here.");
  expect(api).toHaveBeenCalledWith("/jobs/abc", undefined, "DELETE");
  expect(window.location.hash).toBe("");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("failed deletion keeps history and explains the retry", async () => {
  history("failed", true);
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: /Delete conversion aws_rag/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Delete conversion" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Local files are in use.",
  );
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(window.location.hash).toBe("#abc");
});

test("running conversions have a timeline and no delete control", async () => {
  history("running");
  render(<App />);
  await screen.findByText("Working in the background");
  expect(
    screen.queryByRole("button", { name: /Delete conversion/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("region", { name: "Conversion activity" }),
  ).toHaveTextContent("Live");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});

test("sidebar collapses, keeps conversion navigation, and remembers its preference", async () => {
  history("completed");
  render(<App />);
  await screen.findByText("Your OCI project is ready to review.");
  fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
  expect(
    screen.getByRole("button", { name: "Expand sidebar" }),
  ).toHaveAttribute("aria-expanded", "false");
  expect(
    screen.getByRole("button", { name: /aws_rag - Complete/ }),
  ).toBeInTheDocument();
  expect(localStorage.getItem("cloudshift-sidebar")).toBe("collapsed");
  cleanup();
  render(<App />);
  expect(
    screen.getByRole("button", { name: "Expand sidebar" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));
  expect(localStorage.getItem("cloudshift-sidebar")).toBe("expanded");
});

test("environment tab loads the saved redacted preview", async () => {
  window.location.hash = "abc";
  vi.mocked(api).mockImplementation(
    async (path) =>
      (path === "/status"
        ? { astra_configured: true, astra_model: "model", retention_hours: 24 }
        : path.endsWith("/environment")
          ? {
              aws: { AWS_REGION: "ap-southeast-2" },
              aws_ignored: 2,
              oci: {
                OCI_REGION: "us-chicago-1",
                OCI_DB_PASSWORD: "[REDACTED]",
              },
              masked: ["OCI_DB_PASSWORD"],
              status: "completed",
            }
          : [{ ...job, status: "completed" }]) as any,
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("tab", { name: "Environment" }));
  await screen.findByText("OCI_DB_PASSWORD");
  expect(screen.getByText('"[REDACTED]"')).toBeInTheDocument();
  expect(screen.getByText('"ap-southeast-2"')).toBeInTheDocument();
  expect(screen.getByText(/2 other entries discarded/)).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith("/jobs/abc/environment");
  expect(screen.getByText("Initial upload")).toBeInTheDocument();
  expect(
    screen.queryByLabelText("Load AWS .env for comparison"),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("Use saved settings")).not.toBeInTheDocument();
});


test("loads private defaults into masked fields and restores them for a new selection", async () => {
  window.location.hash = "abc";
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/status")
      return { astra_configured: true, astra_model: "model", retention_hours: 24 } as any;
    if (path === "/target-defaults")
      return { db_password: "test-db-secret", db_wallet_password: "test-wallet-secret" } as any;
    return [job] as any;
  });
  render(<App />);
  await screen.findByText("Connect your OCI components");
  expect(screen.getByLabelText("Database password")).toHaveValue("test-db-secret");
  expect(screen.getByLabelText("Database password")).toHaveAttribute("type", "password");
  expect(screen.getByLabelText("Wallet password (optional)")).toHaveValue("test-wallet-secret");
  expect(screen.getByLabelText("Wallet password (optional)")).toHaveAttribute("type", "password");
  expect(screen.getByLabelText("LLM API format")).toHaveValue("generic");
  fireEvent.change(screen.getByLabelText("Database password"), {
    target: { value: "edited-password" },
  });
  expect(screen.getByLabelText("Database password")).toHaveValue("edited-password");
  fireEvent.click(screen.getByRole("button", { name: /New conversion/i }));
  fireEvent.click(screen.getByRole("button", { name: /aws_rag - Ready to configure/i }));
  expect(screen.getByLabelText("Database password")).toHaveValue("test-db-secret");
  expect(JSON.stringify(window.localStorage)).not.toContain("test-db-secret");
});

test("autofills the configured repository and restores it for a new conversion", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/status") return { astra_configured: true } as any;
    if (path === "/target-defaults") return { repository_url: "https://github.com/team/repo" } as any;
    return [] as any;
  });
  render(<App />);
  const repository = screen.getByLabelText("GitHub repository");
  await waitFor(() => expect(repository).toHaveValue("https://github.com/team/repo"));
  fireEvent.change(repository, { target: { value: "https://github.com/team/other" } });
  expect(repository).toHaveValue("https://github.com/team/other");
  fireEvent.click(screen.getByRole("button", { name: /New conversion/i }));
  expect(repository).toHaveValue("https://github.com/team/repo");
});

test("uses the saved server token only for its configured GitHub repository", async () => {
  vi.mocked(api).mockImplementation(async (path, body) => {
    if (path === "/status") return { astra_configured: true } as any;
    if (path === "/target-defaults") return {
      repository_url: "https://github.com/team/repo", github_token_configured: true,
    } as any;
    return body ? job : [] as any;
  });
  render(<App />);
  const repository = screen.getByLabelText("GitHub repository");
  const token = screen.getByLabelText(/GitHub access token/);
  await waitFor(() => expect(repository).toHaveValue("https://github.com/team/repo"));
  expect(token).toHaveValue("");
  expect(token).toHaveAttribute("placeholder", "Saved token on server");
  expect(token).not.toBeRequired();
  fireEvent.change(repository, { target: { value: "https://github.com/team/other" } });
  expect(token).toBeRequired();
  fireEvent.click(screen.getByRole("button", { name: /New conversion/i }));
  expect(repository).toHaveValue("https://github.com/team/repo");
  expect(token).not.toBeRequired();
  fireEvent.click(screen.getByRole("button", { name: /Inspect repository/ }));
  await screen.findByText("Connect your OCI components");
  expect(api).toHaveBeenCalledWith("/jobs", expect.objectContaining({
    repository_url: "https://github.com/team/repo", github_token: "",
  }));
  fireEvent.click(screen.getByRole("button", { name: /New conversion/i }));
  expect(screen.getByLabelText(/GitHub access token/)).not.toBeRequired();
});
