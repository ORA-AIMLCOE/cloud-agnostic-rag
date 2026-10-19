import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { api, download, type Job, type Status } from "./api";
import { Icon } from "./Icon";
import { CodeChanges } from "./CodeChanges";
import { Environment } from "./Environment";
import { activityLabel } from "./activity";

const initialTarget = {
  region: "ap-hyderabad-1",
  compartment_id:
    "ocid1.compartment.oc1..aaaaaaaa3qvv265xribdtfsiykr3haigqnyrokay6civ2e6rijweihtagdna",
  namespace: "axq9kf4jgjxz",
  bucket: "cloudshift-rag-documents",
  object_prefix: "documents/",
  llm_model_id:
    "ocid1.generativeaimodel.oc1.ap-hyderabad-1.amaaaaaask7dceya5vgh63kn7duemcsc7hhitvnduml4ivx5k3hjqdevrpfa",
  llm_endpoint:
    "https://inference.generativeai.ap-hyderabad-1.oci.oraclecloud.com",
  llm_format: "generic",
  llm_serving_mode: "on_demand",
  embedding_model_id:
    "cohere.embed-v4.0",
  embedding_endpoint:
    "https://inference.generativeai.ap-hyderabad-1.oci.oraclecloud.com",
  embedding_serving_mode: "on_demand",
  embedding_dimensions: 1536,
  embedding_set_dimensions: false,
  chunk_chars: 1800,
  chunk_overlap: 200,
  db_user: "AWSOCI_RAG",
  db_password: "",
  db_dsn: "cloudshiftrag_low",
  db_wallet_dir: "/home/ubuntu/oci_wallets/Wallet_CLOUDSHIFTRAG",
  db_wallet_password: "",
  oci_profile: "DEFAULT",
  tenancy_id: "",
  user_id: "",
  fingerprint: "",
  private_key: "",
};
const names: Record<string, string> = {
  queued_inspection: "Queued",
  running: "In progress",
  ready: "Ready to configure",
  queued: "Queued",
  completed: "Complete",
  failed: "Needs attention",
  cancelled: "Cancelled",
  expired: "Expired",
};
const deletable = (status: string) =>
  ["completed", "failed", "cancelled", "expired"].includes(status);
const shortDate = (time: number) =>
  new Date(time * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const errors = (e: unknown) =>
  e instanceof Error ? e.message : "Something went wrong.";
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
function Section({
  number,
  title,
  description,
  children,
}: {
  number: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="form-section">
      <div className="section-heading">
        <span className="section-number">{number}</span>
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

export default function App() {
  const defaults = useRef(initialTarget);
  const repositoryDefault = useRef("");
  const [githubTokenConfigured, setGithubTokenConfigured] = useState(false);
  const [status, setStatus] = useState<Status | null>(null),
    [jobs, setJobs] = useState<Job[]>([]),
    [job, setJob] = useState<Job | null>(null);
  const [repo, setRepo] = useState(""),
    [branch, setBranch] = useState("aws_rag"),
    [token, setToken] = useState(""),
    [env, setEnv] = useState(""),
    [envName, setEnvName] = useState("");
  const [target, setTarget] = useState(initialTarget),
    [publish, setPublish] = useState(true),
    [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [tab, setTab] = useState<"overview" | "changes" | "checks" | "environment">(
      "overview",
    ),
    [mobile, setMobile] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("cloudshift-sidebar") === "collapsed";
    } catch {
      return false;
    }
  });
  function toggleSidebar() {
    setCollapsed((value) => {
      try {
        localStorage.setItem(
          "cloudshift-sidebar",
          value ? "expanded" : "collapsed",
        );
      } catch {
        /* Preferences are optional. */
      }
      return !value;
    });
  }
  const [deleteTarget, setDeleteTarget] = useState<Job | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const deleteDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (deleteTarget) deleteDialog.current?.showModal();
    else deleteDialog.current?.close();
  }, [deleteTarget]);
  async function removeJob() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await api(`/jobs/${deleteTarget.id}`, undefined, "DELETE");
      setJobs((current) =>
        current.filter((item) => item.id !== deleteTarget.id),
      );
      if (job?.id === deleteTarget.id) select(null);
      setDeleteTarget(null);
    } catch (e) {
      setDeleteError(errors(e));
    } finally {
      setDeleting(false);
    }
  }
  useEffect(() => {
    Promise.all([
      api<Status>("/status"),
      api<Job[]>("/jobs"),
      api<Pick<typeof initialTarget, "db_password" | "db_wallet_password"> & { repository_url?: string; github_token_configured?: boolean }>("/target-defaults"),
    ])
      .then(([s, j, privateDefaults]) => {
        defaults.current = {
          ...initialTarget,
          db_password: privateDefaults.db_password ?? "",
          db_wallet_password: privateDefaults.db_wallet_password ?? "",
        };
        repositoryDefault.current = privateDefaults.repository_url ?? "";
        setGithubTokenConfigured(privateDefaults.github_token_configured ?? false);
        setRepo(current => current || repositoryDefault.current);
        setTarget({ ...defaults.current });
        setStatus(s);
        setJobs(j);
        const id = window.location.hash.slice(1);
        setJob(j.find((x) => x.id === id) || null);
      })
      .catch((e) => setError(errors(e)));
  }, []);
  useEffect(() => {
    if (
      !job ||
      !["queued_inspection", "running", "queued"].includes(job.status)
    )
      return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Job>("/jobs/" + job.id);
        if (!cancelled) {
          setJob(next);
          setJobs((current) =>
            current.map((j) => (j.id === next.id ? next : j)),
          );
        }
      } catch (e) {
        if (!cancelled) setError(errors(e));
      } finally {
        if (!cancelled) timer = setTimeout(poll, 2000);
      }
    };
    timer = setTimeout(poll, 1500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [job?.id, job?.status]);
  const normalizeRepository = (value: string) =>
    value.trim().replace(/\/$/, "").replace(/\.git$/, "").toLowerCase();
  const hasSavedGithubToken = githubTokenConfigured &&
    normalizeRepository(repo) === normalizeRepository(repositoryDefault.current);
  function select(next: Job | null) {
    if (!next) {
      setRepo(repositoryDefault.current);
      setToken("");
    }
    setJob(next);
    window.location.hash = next?.id || "";
    setTarget({ ...defaults.current });
    setAck(false);
    setPublish(next?.publish_allowed ?? true);
    setError("");
    setMobile(false);
    setTab("overview");
  }
  function update(
    key: keyof typeof initialTarget,
    value: string | number | boolean,
  ) {
    setTarget((t) => ({ ...t, [key]: value }));
  }
  const field = (
    key: keyof typeof initialTarget,
    label: string,
    placeholder = "",
    type = "text",
    hint?: string,
  ) => (
    <Field label={label} hint={hint}>
      <input
        value={String(target[key])}
        type={type}
        placeholder={placeholder}
        required={
          ![
            "db_wallet_dir",
            "db_wallet_password",
            "tenancy_id",
            "user_id",
            "fingerprint",
          ].includes(key)
        }
        autoComplete="off"
        onChange={(e) =>
          update(
            key,
            type === "number" ? Number(e.target.value) : e.target.value,
          )
        }
      />
    </Field>
  );
  async function inspect(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await api<Job>("/jobs", {
        repository_url: repo,
        source_branch: branch,
        github_token: token,
        aws_env: env,
      });
      setJobs((j) => [next, ...j]);
      select(next);
      setToken("");
      setEnv("");
      setEnvName("");
    } catch (e) {
      setError(errors(e));
    } finally {
      setBusy(false);
    }
  }
  async function convert(e: FormEvent) {
    e.preventDefault();
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<Job>(`/jobs/${job.id}/convert`, {
        target: {
          ...target,
        },
        publish: publish && !!job.publish_allowed,
        acknowledge_source_transfer: ack,
      });
      setJob(next);
      setTarget({ ...defaults.current });
      setTab("overview");
    } catch (e) {
      setError(errors(e));
    } finally {
      setBusy(false);
    }
  }
  async function getDownload(kind: "configuration" | "source") {
    if (!job) return;
    try {
      await download(job.id, kind);
    } catch (e) {
      setError(errors(e));
    }
  }
  const active =
    job && ["running", "queued", "queued_inspection"].includes(job.status);

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <dialog
        ref={deleteDialog}
        className="delete-dialog"
        aria-labelledby="delete-title"
        aria-describedby="delete-description"
        onCancel={(e) => {
          e.preventDefault();
          if (!deleting) setDeleteTarget(null);
        }}
      >
        <h2 id="delete-title">Delete this conversion?</h2>
        <p className="delete-name">
          {deleteTarget?.repository_url.split("/").pop()} {"\u00b7"}{" "}
          {deleteTarget && shortDate(deleteTarget.created_at)}
        </p>
        <p id="delete-description">
          This removes its local history, downloads, and saved credentials.
          Published GitHub branches and cloud resources are kept. This cannot be
          undone.
        </p>
        {deleteError && (
          <p className="error" role="alert">
            {deleteError}
          </p>
        )}
        <div className="dialog-actions">
          <button
            className="secondary"
            autoFocus
            disabled={deleting}
            onClick={() => setDeleteTarget(null)}
          >
            Keep conversion
          </button>
          <button className="primary" disabled={deleting} onClick={removeJob}>
            {deleting ? "Deleting..." : "Delete conversion"}
          </button>
        </div>
      </dialog>
      {mobile && (
        <button
          className="scrim"
          aria-label="Close menu"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        id="workspace-sidebar"
        className={`sidebar ${mobile ? "open" : ""}`}
      >
        <button
          className="sidebar-toggle"
          onClick={toggleSidebar}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          aria-controls="workspace-sidebar"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <Icon name="panel" />
        </button>
        <a
          href="#"
          className="brand"
          aria-label="Cloudshift home"
          title="Cloudshift home"
          onClick={(e) => {
            e.preventDefault();
            select(null);
          }}
        >
          <span className="brand-symbol">
            <Icon name="code" />
          </span>
          <span>
            Cloudshift<small>AWS TO OCI</small>
          </span>
        </a>
        <button
          className="new-conversion"
          aria-label="New conversion"
          title="New conversion"
          onClick={() => select(null)}
        >
          <Icon name="plus" />
          <span>New conversion</span>
        </button>
        <div className="sidebar-label">RECENT CONVERSIONS</div>
        <nav aria-label="Recent conversions">
          {jobs.length ? (
            jobs.map((j) => (
              <div
                key={j.id}
                className={`job-row ${job?.id === j.id ? "selected" : ""}`}
              >
                <button
                  className="job-link"
                  onClick={() => select(j)}
                  title={`${j.repository_url.split("/").pop()} - ${names[j.status] || j.status} - ${shortDate(j.created_at)}`}
                  aria-label={`${j.repository_url.split("/").pop()} - ${names[j.status] || j.status} - ${shortDate(j.created_at)}`}
                  aria-current={job?.id === j.id ? "page" : undefined}
                >
                  <span className={`rail-job-icon ${j.status}`}>
                    <Icon name="file" />
                  </span>
                  <span className="job-info">
                    <strong title={j.repository_url}>
                      {j.repository_url.split("/").pop()}
                    </strong>
                    <small className="job-state">
                      <i className={`dot ${j.status}`} />
                      {names[j.status] || j.status}
                    </small>
                    <small className="job-date">
                      {j.source_branch || "History"} {"\u00b7"}{" "}
                      {shortDate(j.created_at)}
                    </small>
                  </span>
                </button>
                {deletable(j.status) && (
                  <button
                    className="delete-job"
                    title="Delete conversion"
                    aria-label={`Delete conversion ${j.repository_url.split("/").pop()} from ${shortDate(j.created_at)}`}
                    onClick={() => {
                      setDeleteError("");
                      setDeleteTarget(j);
                    }}
                  >
                    <Icon name="trash" />
                  </button>
                )}
              </div>
            ))
          ) : (
            <p className="empty-list">Your conversions will appear here.</p>
          )}
        </nav>
      </aside>
      <main>
        <header className="topbar">
          <button
            className="mobile-menu"
            aria-label="Open menu"
            onClick={() => setMobile(true)}
          >
            <Icon name="code" />
          </button>
        </header>
        <div className="page">
          {error && (
            <div role="alert" className="error">
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <Icon name="close" />
              </button>
            </div>
          )}
          {!job ? (
            <>
              <div className="page-heading">
                <div className="eyebrow">SAME APPLICATION. A NEW CLOUD.</div>
                <h1>Make the move to OCI.</h1>
                <p>
                  Bring your repository. Keep your core logic.
                  <br />
                  Get an OCI branch with every change explained.
                </p>
              </div>
              <div className="migration-strip">
                <span className="cloud-badge aws">aws</span>
                <span className="migration-line" />
                <span className="migration-caption">
                  Your code, carried forward
                </span>
                <Icon name="arrow" />
                <span className="cloud-badge oci">OCI</span>
              </div>
              <form onSubmit={inspect} className="source-form">
                <Section
                  number="01"
                  title="Start with your repository"
                  description="We'll inspect a snapshot of your selected branch."
                >
                  <Field label="GitHub repository">
                    <input
                      type="url"
                      required
                      placeholder="https://github.com/your-team/aws_rag"
                      value={repo}
                      onChange={(e) => setRepo(e.target.value)}
                    />
                  </Field>
                  <div className="field-grid">
                    <Field label="Source branch">
                      <input
                        required
                        value={branch}
                        onChange={(e) => setBranch(e.target.value)}
                      />
                    </Field>
                    <Field
                      label="GitHub access token"
                      hint={hasSavedGithubToken ? "A saved token is available for this repository. Leave blank to use it, or enter another token." : "Fine-grained token: this repository, Contents read and write."}
                    >
                      <input
                        type="password"
                        required={!hasSavedGithubToken}
                        autoComplete="off"
                        value={token}
                        placeholder={hasSavedGithubToken ? "Saved token on server" : "Your repository access token"}
                        onChange={(e) => setToken(e.target.value)}
                      />
                    </Field>
                  </div>
                  <label className="file-drop">
                    <span className="upload-symbol">
                      <Icon name="file" />
                    </span>
                    <span>
                      <strong>{envName || "Add your AWS .env file"}</strong>
                      <small>
                        Optional. AWS secrets are discarded; resource settings
                        are read.
                      </small>
                    </span>
                    <span className="browse">Browse</span>
                    <input
                      type="file"
                      aria-label="AWS environment file"
                      onChange={async (e) => {
                        const f = e.target.files?.[0];
                        if (f) {
                          if (f.size > 65536) {
                            setError(
                              "Use an environment file smaller than 64 KB.",
                            );
                            return;
                          }
                          setEnv(await f.text());
                          setEnvName(f.name);
                        }
                      }}
                    />
                  </label>
                </Section>
                <div className="form-footer">
                  <button className="primary" disabled={busy}>
                    {busy ? "Starting inspection..." : "Inspect repository"}
                    <Icon name="arrow" />
                  </button>
                </div>
              </form>
              <div className="principles">
                <span>
                  <Icon name="check" />
                  Core logic preserved
                </span>
                <span>
                  <Icon name="check" />
                  New branch in your repository
                </span>
                <span>
                  <Icon name="check" />
                  Changes you can review
                </span>
              </div>
            </>
          ) : (
            <>
              <div className="job-heading">
                <div>
                  <div className="eyebrow">
                    {job.source_branch}{" "}
                    {job.source_sha && ` / ${job.source_sha.slice(0, 8)}`}
                  </div>
                  <h1>{job.repository_url.split("/").pop()}</h1>
                  <p>{job.phase}</p>
                </div>
                <span className={`status-pill ${job.status}`}>
                  {names[job.status] || job.status}
                </span>
              </div>
              {job.status === "ready" ? (
                <form onSubmit={convert}>
                  <div className="inline-note">
                    <Icon name="check" />
                    <span>
                      {job.analysis?.prepared_knowledge
                        ? "Distributor Aggregator detected. Its prepared document workflow, comparisons, UI and integration API stay intact. Persistence moves to Autonomous Database."
                        : "Source inspected. Your RAG workflow, UI, prompts, and question-answering flow stay intact. Persistence moves to Autonomous Database."}
                    </span>
                  </div>
                  <Section
                    number="02"
                    title="Connect your OCI components"
                    description="Use existing resources. The converter won't create or deploy cloud infrastructure."
                  >
                    <div className="field-grid">
                      {field("region", "OCI region", "ap-hyderabad-1")}
                      {field(
                        "compartment_id",
                        "Compartment OCID",
                        "ocid1.compartment...",
                      )}
                      {field(
                        "namespace",
                        "Object Storage namespace",
                        "your-namespace",
                      )}
                      {field(
                        "bucket",
                        "Object Storage bucket",
                        "rag-documents",
                      )}
                      {field("object_prefix", "Object prefix", "documents/")}
                    </div>
                  </Section>
                  <Section
                    number="03"
                    title="Choose the answer model"
                    description="This model answers document questions in your converted RAG application."
                  >
                    <div className="field-grid">
                      {field(
                        "llm_model_id",
                        "LLM model or endpoint ID",
                        "Model ID or dedicated endpoint OCID",
                      )}
                      <Field label="LLM API format">
                        <select
                          value={target.llm_format}
                          onChange={(e) => update("llm_format", e.target.value)}
                        >
                          <option value="generic">OCI native - Generic</option>
                          <option value="generic_astra">
                            OCI native - Generic (Astra)
                          </option>
                          <option value="cohere">OCI native - Cohere</option>
                          <option value="responses">OCI - Responses API</option>
                          <option value="chat_completions">
                            OCI - Chat Completions
                          </option>
                        </select>
                      </Field>
                      {field(
                        "llm_endpoint",
                        "LLM service endpoint",
                        "https://inference.generativeai...oci.oraclecloud.com",
                        "url",
                        "For Responses / Chat Completions, include the API base path.",
                      )}
                      <Field label="LLM serving mode">
                        <select
                          value={target.llm_serving_mode}
                          onChange={(e) =>
                            update("llm_serving_mode", e.target.value)
                          }
                        >
                          <option value="on_demand">On demand</option>
                          <option value="dedicated">Dedicated endpoint</option>
                        </select>
                      </Field>
                    </div>
                  </Section>
                  <Section
                    number="04"
                    title="Choose the embedding model"
                    description="Independent of the answer model. Embeddings are stored in Autonomous Database with AI Vector Search."
                  >
                    <div className="field-grid">
                      {field(
                        "embedding_model_id",
                        "Embedding model or endpoint ID",
                        "Your OCI embedding model",
                      )}
                      {field(
                        "embedding_endpoint",
                        "Embedding service endpoint",
                        "https://inference.generativeai...oci.oraclecloud.com",
                        "url",
                        "Native OCI EmbedText endpoint; supports retrieval input types.",
                      )}
                      {field(
                        "embedding_dimensions",
                        "Vector dimensions",
                        "1024",
                        "number",
                      )}
                      <Field label="Embedding serving mode">
                        <select
                          value={target.embedding_serving_mode}
                          onChange={(e) =>
                            update("embedding_serving_mode", e.target.value)
                          }
                        >
                          <option value="on_demand">On demand</option>
                          <option value="dedicated">Dedicated endpoint</option>
                        </select>
                      </Field>
                    </div>
                    <details className="advanced">
                      <summary>Chunking and model options</summary>
                      <div className="field-grid">
                        {field(
                          "chunk_chars",
                          "Characters per chunk",
                          "1800",
                          "number",
                        )}
                        {field(
                          "chunk_overlap",
                          "Overlap in characters",
                          "200",
                          "number",
                        )}
                      </div>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={target.embedding_set_dimensions}
                          onChange={(e) =>
                            update("embedding_set_dimensions", e.target.checked)
                          }
                        />
                        Request output dimensions from the model (only if
                        supported)
                      </label>
                      <p>
                        Different chunks and wording from AWS are expected.
                        Sources and factual grounding matter.
                      </p>
                    </details>
                  </Section>
                  <Section
                    number="05"
                    title="Database and runtime credentials"
                    description="These values go into a private download, never the generated Git branch."
                  >
                    <p>
                      Autonomous AI Database Serverless stores document
                      metadata, chat history, and vectors.
                    </p>
                    {field(
                      "db_dsn",
                      "Database connection string (DSN)",
                      "tcps://your-host:1521/your-service",
                      "text",
                      "Copy the TLS connection string from OCI Database connection. For mTLS, use your wallet's TNS alias.",
                    )}
                    <div className="field-grid">
                      {field("db_user", "Database username", "RAG_APP")}
                      {field(
                        "db_password",
                        "Database password",
                        "",
                        "password",
                      )}
                    </div>
                    <details className="advanced">
                      <summary>Database wallet (optional)</summary>
                      {field(
                        "db_wallet_dir",
                        "Wallet directory on runtime machine",
                        "config/wallet",
                        "text",
                        "For mTLS, extract your wallet here on the machine running the converted app. Wallet files are not uploaded or committed.",
                      )}
                      {field(
                        "db_wallet_password",
                        "Wallet password (optional)",
                        "",
                        "password",
                      )}
                    </details>
                    <details className="advanced">
                      <summary>OCI signing credentials</summary>
                      {field("oci_profile", "OCI profile", "DEFAULT")}
                      <p>
                        Use an existing OCI profile on the machine running the
                        generated project, or include signing credentials below.
                      </p>
                      <div className="field-grid">
                        {field("tenancy_id", "Tenancy OCID")}
                        {field("user_id", "User OCID")}
                        {field("fingerprint", "Public key fingerprint")}
                      </div>
                      <Field label="Private signing key (optional)">
                        <textarea
                          value={target.private_key}
                          onChange={(e) =>
                            update("private_key", e.target.value)
                          }
                          placeholder="PEM private key - included only in your Private ENV Configuration download"
                          rows={3}
                        />
                      </Field>
                    </details>
                  </Section>
                  <div className="conversion-options">
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={publish && !!job.publish_allowed}
                        disabled={!job.publish_allowed}
                        onChange={(e) => setPublish(e.target.checked)}
                      />
                      Push the validated result to a new branch in this
                      repository
                    </label>
                    {!job.publish_allowed && (
                      <p>
                        Automatic branch workflows were detected. Download-only
                        conversion is available.
                      </p>
                    )}
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        required
                        checked={ack}
                        onChange={(e) => setAck(e.target.checked)}
                      />
                      Send the relevant source code to my configured OCI Astra
                      model for conversion.
                    </label>
                  </div>
                  {!status?.astra_configured && (
                    <div className="setup-note">
                      OCI Astra is not connected yet. Add its endpoint and
                      credentials to the converter configuration, then restart
                      the backend.
                    </div>
                  )}
                  <div className="form-footer">
                    <span>
                      Astra converts code. Your selected models power the RAG
                      app.
                    </span>
                    <button
                      className="primary"
                      disabled={busy || !status?.astra_configured || !ack}
                    >
                      CONVERT TO OCI
                      <Icon name="arrow" />
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <div
                    className="tabs"
                    role="tablist"
                    aria-label="Conversion results"
                  >
                    {(
                      ["overview", "changes", "checks", "environment"] as const
                    ).map((t) => (
                      <button
                        key={t}
                        role="tab"
                        aria-selected={tab === t}
                        className={tab === t ? "active" : ""}
                        onClick={() => setTab(t)}
                      >
                        {t === "overview"
                          ? "Overview"
                          : t === "changes"
                            ? `Code changes${job.files.length ? " / " + job.files.length : ""}`
                            : t === "checks"
                              ? "Validation"
                              : "Environment"}
                      </button>
                    ))}
                  </div>
                  {tab === "overview" && (
                    <div className="overview-grid">
                      <div className="overview-summary">
                        <div className="result-card">
                          {active ? (
                            <>
                              <div className="working-mark">
                                <Icon name="code" />
                              </div>
                              <h2>
                                {job.cancel_requested
                                  ? "Cancelling at the next safe point..."
                                  : "Working in the background"}
                              </h2>
                              <p>
                                You can return to this job after refreshing the
                                page.
                              </p>
                            </>
                          ) : job.status === "completed" ? (
                            <>
                              <span className="success-mark">
                                <Icon name="check" />
                              </span>
                              <h2>Your OCI project is ready to review.</h2>
                              <p>
                                Offline validation passed. Live OCI access and
                                answer quality are still unverified.
                              </p>
                              {job.analysis?.prepared_knowledge && (
                                <p>
                                  Follow docs/oci-generated.md to initialize Oracle and ingest the distributor
                                  document before starting the app. The new integration API key is included
                                  only in Private ENV Configuration.
                                </p>
                              )}
                              <div className="result-actions">
                                {job.branch_url && (
                                  <a
                                    className="primary"
                                    href={job.branch_url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    Open OCI branch
                                    <Icon name="arrow" />
                                  </a>
                                )}
                                <button
                                  className="secondary"
                                  onClick={() => getDownload("source")}
                                >
                                  Download code
                                </button>
                                <button
                                  className="secondary"
                                  onClick={() => getDownload("configuration")}
                                >
                                  Private ENV Configuration
                                </button>
                              </div>
                              {job.compare_url && (
                                <a
                                  className="text-link"
                                  href={job.compare_url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Compare with the source commit
                                </a>
                              )}
                            </>
                          ) : (
                            <>
                              <h2>
                                {job.status === "failed"
                                  ? "Conversion needs attention."
                                  : names[job.status]}
                              </h2>
                              <p>{job.phase}</p>
                              <button
                                className="secondary"
                                onClick={() => select(null)}
                              >
                                Start a new conversion
                              </button>
                            </>
                          )}
                        </div>
                        {job.status === "completed" && (
                          <div className="component-map">
                            <h2>What moved</h2>
                            <div>
                              <span>
                                <Icon name="storage" />
                                S3
                              </span>
                              <Icon name="arrow" />
                              <strong>
                                <Icon name="storage" />
                                OCI Object Storage
                              </strong>
                            </div>
                            <div>
                              <span>
                                <Icon name="model" />
                                Bedrock answer model
                              </span>
                              <Icon name="arrow" />
                              <strong>
                                <Icon name="model" />
                                Your OCI LLM
                              </strong>
                            </div>
                            <div>
                              <span>
                                <Icon name="search" />
                                Bedrock Knowledge Base
                              </span>
                              <Icon name="arrow" />
                              <strong>
                                <Icon name="search" />
                                Oracle AI Vector Search
                              </strong>
                            </div>
                            <div>
                              <span>
                                <Icon name="database" />
                                PostgreSQL history
                              </span>
                              <Icon name="arrow" />
                              <strong>
                                <Icon name="database" />
                                Autonomous Database history
                              </strong>
                            </div>
                          </div>
                        )}
                        {job.metrics && (
                          <div className="metrics">
                            <div>
                              <strong>{job.metrics.modified}</strong>
                              <span>Existing files changed</span>
                            </div>
                            <div>
                              <strong>{job.metrics.added}</strong>
                              <span>Files added</span>
                            </div>
                            <div>
                              <strong>{job.metrics.core_unchanged}</strong>
                              <span>Core files preserved</span>
                            </div>
                          </div>
                        )}
                      </div>
                      <section
                        className="activity"
                        aria-label="Conversion activity"
                      >
                        <div className="activity-heading">
                          <h2>Conversion activity</h2>
                          <span
                            className={`activity-label ${active ? "live" : ""}`}
                          >
                            {active ? "Live" : `${job.events.length} events`}
                          </span>
                        </div>
                        <p className="activity-caption">
                          {active
                            ? "Following your conversion"
                            : "From AWS source to OCI code"}
                        </p>
                        <ol
                          className="event-list"
                          aria-live="polite"
                          aria-relevant="additions text"
                        >
                          {job.events.map((event, i) => {
                            const label = activityLabel(event.message);
                            return (
                              <li
                                className={`event ${i === job.events.length - 1 ? `latest ${job.status}` : ""}`}
                                key={i}
                              >
                                <span className="event-marker">
                                  {i === job.events.length - 1 &&
                                  job.status === "completed" ? (
                                    <Icon name="check" />
                                  ) : i === job.events.length - 1 &&
                                    job.status === "failed" ? (
                                    "!"
                                  ) : (
                                    <span />
                                  )}
                                </span>
                                <div className="event-content">
                                  <span className="event-title">
                                    {label.title}
                                  </span>
                                  {label.description && (
                                    <p className="event-description">
                                      {label.description}
                                    </p>
                                  )}
                                  <time
                                    dateTime={new Date(
                                      event.time * 1000,
                                    ).toISOString()}
                                  >
                                    {shortDate(event.time)}
                                  </time>
                                </div>
                              </li>
                            );
                          })}
                        </ol>
                        {!job.events.length && (
                          <p className="activity-caption">
                            Events will appear when processing starts.
                          </p>
                        )}
                        {active && (
                          <button
                            className="text-link cancel"
                            disabled={job.cancel_requested}
                            onClick={() =>
                              api<Job>(`/jobs/${job.id}/cancel`, {})
                                .then(setJob)
                                .catch((e) => setError(errors(e)))
                            }
                          >
                            Cancel conversion
                          </button>
                        )}
                      </section>
                    </div>
                  )}
                  {tab === "changes" && (
                    <CodeChanges
                      key={job.id}
                      files={job.files}
                      compareUrl={job.compare_url}
                    />
                  )}
                  {tab === "environment" && (
                    <Environment
                      key={job.id}
                      jobId={job.id}
                      status={job.status}
                    />
                  )}
                  {tab === "checks" && (
                    <div className="checks-panel">
                      {job.checks.map((c) => (
                        <div className="check-row" key={c.name}>
                          <span>{c.name}</span>
                          <span className={`check-status ${c.status}`}>
                            {c.status.replace("_", " ")}
                          </span>
                        </div>
                      ))}
                      {job.validation_log && (
                        <details className="test-log">
                          <summary>Build and test output</summary>
                          <pre>{job.validation_log}</pre>
                        </details>
                      )}
                      <p>
                        Live OCI testing is separate. Matching AWS answers word
                        for word is not required.
                      </p>
                    </div>
                  )}
                </>
              )}
            </>
          )}
          <footer>
            Cloudshift <span>Configuration first. Core logic intact.</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
