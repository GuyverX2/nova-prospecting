/**
 * Nova operator console.
 *
 * Nova issues no credentials and has no login: the platform hands this console
 * a bearer token, which is kept in memory for the session only. Every action
 * here is an operator decision - nothing analyses, proposes or sends by itself.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "./api";
import type { Analysis, Prospect, Summary } from "./types";

type Status = { kind: "idle" | "busy" | "ok" | "error"; message: string };

const IDLE: Status = { kind: "idle", message: "" };

function formatSek(value: number): string {
  return `${value.toLocaleString("sv-SE")} kr`;
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} [${error.code}]` : `${error.message} (${error.code})`;
  }
  return "Unexpected error";
}

export default function App() {
  const [token, setToken] = useState(window.NOVA_PLATFORM_TOKEN ?? "");
  const [authenticated, setAuthenticated] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>(IDLE);

  const selected = useMemo(
    () => prospects.find((prospect) => prospect.id === selectedId) ?? null,
    [prospects, selectedId],
  );

  const refresh = useCallback(
    async (activeToken: string, term: string) => {
      const [nextSummary, nextProspects] = await Promise.all([
        api.summary(activeToken),
        api.listProspects(activeToken, term),
      ]);
      setSummary(nextSummary);
      setProspects(nextProspects);
    },
    [],
  );

  const run = useCallback(
    async (busyMessage: string, action: () => Promise<string>) => {
      setStatus({ kind: "busy", message: busyMessage });
      try {
        const message = await action();
        await refresh(token, search);
        setStatus({ kind: "ok", message });
      } catch (error) {
        setStatus({ kind: "error", message: describeError(error) });
      }
    },
    [refresh, search, token],
  );

  async function connect(event: React.FormEvent) {
    event.preventDefault();
    if (!token.trim()) {
      setStatus({ kind: "error", message: "A platform bearer token is required." });
      return;
    }
    setStatus({ kind: "busy", message: "Connecting…" });
    try {
      await refresh(token, "");
      setAuthenticated(true);
      setStatus({ kind: "ok", message: "Connected to the Nova API." });
    } catch (error) {
      setAuthenticated(false);
      setStatus({ kind: "error", message: describeError(error) });
    }
  }

  useEffect(() => {
    if (!authenticated) return;
    const handle = window.setTimeout(() => {
      void refresh(token, search).catch((error: unknown) =>
        setStatus({ kind: "error", message: describeError(error) }),
      );
    }, 250);
    return () => window.clearTimeout(handle);
  }, [authenticated, refresh, search, token]);

  if (!authenticated) {
    return (
      <main className="gate">
        <p className="eyebrow">NOVA / PROSPECTING</p>
        <h1>Independent operator console.</h1>
        <p className="lede">
          Nova accepts a bearer token issued by the platform. It does not issue credentials and
          provides no login flow. The token is kept in memory for this session only.
        </p>
        <form onSubmit={connect}>
          <label htmlFor="token">Platform bearer token</label>
          <textarea
            id="token"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Supplied by the platform host"
            spellCheck={false}
          />
          <button type="submit">Connect</button>
        </form>
        <StatusLine status={status} />
      </main>
    );
  }

  return (
    <main className="console">
      <header>
        <div>
          <p className="eyebrow">NOVA / PROSPECTING</p>
          <h1>Operator console</h1>
        </div>
        <button
          type="button"
          className="ghost"
          onClick={() => {
            setToken("");
            setAuthenticated(false);
            setSummary(null);
            setProspects([]);
            setStatus({ kind: "ok", message: "Token discarded." });
          }}
        >
          Disconnect
        </button>
      </header>

      {summary ? (
        <section className="cards" aria-label="Tenant summary">
          <Card label="Analysed sites" value={String(summary.analyzed_sites)} />
          <Card label="Open opportunities" value={String(summary.qualified_opportunities)} />
          <Card label="Awaiting review" value={String(summary.awaiting_review)} />
          <Card label="Approved" value={String(summary.approved)} />
          <Card label="Pipeline value" value={formatSek(summary.potential_value_sek)} />
          <Card label="Suppressed contacts" value={String(summary.suppressed_contacts)} />
        </section>
      ) : null}

      <StatusLine status={status} />

      <div className="columns">
        <section aria-label="Prospects">
          <div className="toolbar">
            <input
              type="search"
              value={search}
              placeholder="Search company or domain"
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search prospects"
            />
          </div>
          <NewProspectForm
            onCreate={(payload) =>
              run("Creating prospect…", async () => {
                const created = await api.createProspect(token, payload);
                setSelectedId(created.id);
                return `Created ${created.company_name}.`;
              })
            }
          />
          <ul className="prospects">
            {prospects.map((prospect) => (
              <li key={prospect.id}>
                <button
                  type="button"
                  className={prospect.id === selectedId ? "row selected" : "row"}
                  onClick={() => setSelectedId(prospect.id)}
                >
                  <span className="name">{prospect.company_name}</span>
                  <span className="domain">{prospect.normalized_domain}</span>
                  <span className={`pill ${prospect.status}`}>{prospect.status}</span>
                  {prospect.do_not_contact ? <span className="pill blocked">do not contact</span> : null}
                </button>
              </li>
            ))}
            {prospects.length === 0 ? <li className="empty">No prospects yet.</li> : null}
          </ul>
        </section>

        <section aria-label="Selected prospect">
          {selected ? (
            <ProspectDetail
              prospect={selected}
              onAnalyze={(snapshot, allowFetch) =>
                run("Running analysis…", async () => {
                  const analysis: Analysis = await api.analyze(
                    token,
                    selected.id,
                    snapshot,
                    allowFetch,
                  );
                  return `Analysis complete: improvement score ${analysis.improvement_score}/100.`;
                })
              }
              onVerifyContact={(email, source) =>
                run("Recording contact verification…", async () => {
                  await api.verifyContact(token, selected.id, {
                    ...(email ? { contact_email: email } : {}),
                    contact_verified: true,
                    contact_verification_source: source,
                  });
                  return "Contact recorded as verified.";
                })
              }
              onGenerate={(analysisId) =>
                run("Generating proposal…", async () => {
                  const proposal = await api.generateProposal(token, selected.id, analysisId);
                  return `Created proposal version ${proposal.version}.`;
                })
              }
              onApprove={(proposalId, note) =>
                run("Recording approval…", async () => {
                  await api.approveProposal(token, proposalId, {
                    analysis_verified: true,
                    contact_verified: true,
                    content_approved: true,
                    legal_basis_verified: true,
                    reviewer_note: note,
                  });
                  return "Proposal approved.";
                })
              }
              onShare={(proposalId) =>
                run("Creating share link…", async () => {
                  const share = await api.share(token, proposalId);
                  window.open(share.public_path, "_blank", "noopener,noreferrer");
                  return `Share link valid until ${new Date(share.expires_at).toLocaleDateString("sv-SE")}.`;
                })
              }
              onDeliver={(proposalId, provider, testRecipient) =>
                run("Processing delivery…", async () => {
                  const result = await api.deliver(token, proposalId, provider, testRecipient);
                  return `${result.status} via ${result.provider} (external send: ${result.external_sent ? "yes" : "no"}).`;
                })
              }
              onSuppress={(email) =>
                run("Adding suppression…", async () => {
                  await api.suppress(token, email);
                  return `${email} will not be contacted again.`;
                })
              }
            />
          ) : (
            <p className="empty">Select a prospect to see its analysis, proposal and delivery state.</p>
          )}
        </section>
      </div>
    </main>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <article className="card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function StatusLine({ status }: { status: Status }) {
  if (status.kind === "idle") return null;
  return (
    <p className={`status ${status.kind}`} role="status" aria-live="polite">
      {status.message}
    </p>
  );
}

function NewProspectForm({
  onCreate,
}: {
  onCreate: (payload: {
    company_name: string;
    website_url: string;
    contact_name?: string;
    contact_email?: string;
    estimated_value_sek?: number;
  }) => void;
}) {
  const [companyName, setCompanyName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [contactEmail, setContactEmail] = useState("");

  return (
    <form
      className="new-prospect"
      onSubmit={(event) => {
        event.preventDefault();
        onCreate({
          company_name: companyName.trim(),
          website_url: websiteUrl.trim(),
          ...(contactEmail.trim() ? { contact_email: contactEmail.trim() } : {}),
        });
        setCompanyName("");
        setWebsiteUrl("");
        setContactEmail("");
      }}
    >
      <h2>Add prospect</h2>
      <input
        value={companyName}
        onChange={(event) => setCompanyName(event.target.value)}
        placeholder="Company name"
        aria-label="Company name"
        required
        minLength={2}
      />
      <input
        value={websiteUrl}
        onChange={(event) => setWebsiteUrl(event.target.value)}
        placeholder="https://example.se"
        aria-label="Website URL"
        type="url"
        required
      />
      <input
        value={contactEmail}
        onChange={(event) => setContactEmail(event.target.value)}
        placeholder="Contact email (optional)"
        aria-label="Contact email"
        type="email"
      />
      <button type="submit">Create</button>
    </form>
  );
}

function ProspectDetail({
  prospect,
  onAnalyze,
  onVerifyContact,
  onGenerate,
  onApprove,
  onShare,
  onDeliver,
  onSuppress,
}: {
  prospect: Prospect;
  onAnalyze: (snapshot: string, allowFetch: boolean) => void;
  onVerifyContact: (email: string, source: string) => void;
  onGenerate: (analysisId: string) => void;
  onApprove: (proposalId: string, note: string) => void;
  onShare: (proposalId: string) => void;
  onDeliver: (proposalId: string, provider: string, testRecipient?: string) => void;
  onSuppress: (email: string) => void;
}) {
  const [snapshot, setSnapshot] = useState("");
  const [contactEmail, setContactEmail] = useState(prospect.contact_email ?? "");
  const [verificationSource, setVerificationSource] = useState("");
  const [allowFetch, setAllowFetch] = useState(false);
  const [note, setNote] = useState("");
  const [provider, setProvider] = useState("queue");
  const [testRecipient, setTestRecipient] = useState("");
  const analysis = prospect.latest_analysis;
  const proposal = prospect.latest_proposal;

  return (
    <div className="detail">
      <h2>{prospect.company_name}</h2>
      <p className="meta">
        <a href={prospect.website_url} target="_blank" rel="noopener noreferrer">
          {prospect.normalized_domain}
        </a>{" "}
        · score {prospect.qualification_score}/100 · {formatSek(prospect.estimated_value_sek)}
      </p>
      <p className="meta">
        {prospect.contact_email ?? "no contact email"}{" "}
        {prospect.contact_verified ? "· verified" : "· unverified"}
      </p>

      <fieldset>
        <legend>1 · Evidence</legend>
        <p className="hint">
          Paste a saved HTML snapshot, or confirm a live fetch of the operator-selected public URL.
          Network fetching also requires the server-side kill switch to be on.
        </p>
        <textarea
          value={snapshot}
          onChange={(event) => setSnapshot(event.target.value)}
          placeholder="<!doctype html> …"
          aria-label="HTML snapshot"
        />
        <label className="check">
          <input
            type="checkbox"
            checked={allowFetch}
            onChange={(event) => setAllowFetch(event.target.checked)}
          />
          I confirm fetching {prospect.normalized_domain} over the network
        </label>
        <button type="button" onClick={() => onAnalyze(snapshot, allowFetch)}>
          Run analysis
        </button>
        {analysis ? (
          <div className="analysis">
            <p>
              <strong>{analysis.status}</strong> · improvement {analysis.improvement_score}/100 ·
              performance {analysis.performance_score} · SEO {analysis.seo_score} · a11y{" "}
              {analysis.accessibility_score} · mobile {analysis.mobile_score}
            </p>
            {analysis.error_detail ? <p className="error">{analysis.error_detail}</p> : null}
            <ul>
              {analysis.findings.slice(0, 5).map((finding) => (
                <li key={finding.title}>
                  {finding.title}
                  {finding.confidence === undefined
                    ? null
                    : ` (${Math.round(finding.confidence * 100)}%)`}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </fieldset>

      <fieldset>
        <legend>2 · Contact verification</legend>
        <p className="hint">
          Delivery and approval both require a contact that a human has verified, with a note of how
          it was verified. Nova never imports an email address as verified.
        </p>
        {analysis && analysis.contact_candidates.length > 0 ? (
          <div className="candidates">
            <p className="hint">
              Found on the analysed page — check each one before you use it:
            </p>
            <ul>
              {analysis.contact_candidates.map((candidate) => (
                <li key={`${candidate.field}:${candidate.value}`}>
                  <code>{candidate.field}</code> {candidate.value}{" "}
                  <span className="hint">
                    {candidate.source} · {Math.round(candidate.confidence * 100)}% · {candidate.evidence}
                  </span>
                  {candidate.field === "email" ? (
                    <button
                      type="button"
                      className="link"
                      onClick={() => {
                        setContactEmail(candidate.value);
                        setVerificationSource(
                          `Read from ${analysis.final_url ?? analysis.analyzed_url} (${candidate.evidence}) on ${new Date().toISOString().slice(0, 10)} — confirmed by `,
                        );
                      }}
                    >
                      use
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {prospect.contact_verified && prospect.contact_verification_source ? (
          <p className="hint">Verified: {prospect.contact_verification_source}</p>
        ) : null}
        <div className="row-inputs">
          <input
            value={contactEmail}
            onChange={(event) => setContactEmail(event.target.value)}
            placeholder="Contact email"
            aria-label="Contact email"
            type="email"
          />
          <input
            value={verificationSource}
            onChange={(event) => setVerificationSource(event.target.value)}
            placeholder="How was it verified?"
            aria-label="Verification source"
          />
        </div>
        <button
          type="button"
          disabled={prospect.contact_verified || !verificationSource.trim()}
          onClick={() => onVerifyContact(contactEmail.trim(), verificationSource.trim())}
        >
          {prospect.contact_verified ? "Contact verified" : "Mark contact verified"}
        </button>
      </fieldset>

      <fieldset>
        <legend>3 · Proposal</legend>
        <button
          type="button"
          disabled={!analysis || analysis.status !== "complete"}
          onClick={() => analysis && onGenerate(analysis.id)}
        >
          Generate proposal from analysis
        </button>
        {proposal ? (
          <div className="proposal">
            <p>
              v{proposal.version} · <strong>{proposal.status}</strong> · delivery{" "}
              {proposal.delivery_status}
            </p>
            <p className="headline">{proposal.headline}</p>
            <ul>
              {proposal.packages.map((pack) => (
                <li key={pack.name}>
                  {pack.name} — {formatSek(pack.price_sek)}
                  {pack.recommended ? " (recommended)" : ""}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </fieldset>

      <fieldset>
        <legend>4 · Human approval</legend>
        <p className="hint">
          Approving records that you verified the analysis, the contact, the content and the legal
          basis. Approved proposals are immutable.
        </p>
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Reviewer note"
          aria-label="Reviewer note"
        />
        <button
          type="button"
          disabled={!proposal || proposal.status === "approved"}
          onClick={() => proposal && onApprove(proposal.id, note)}
        >
          Approve proposal
        </button>
      </fieldset>

      <fieldset>
        <legend>5 · Share and deliver</legend>
        <button
          type="button"
          disabled={!proposal || proposal.status !== "approved"}
          onClick={() => proposal && onShare(proposal.id)}
        >
          Create share link
        </button>
        <div className="row-inputs">
          <select
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
            aria-label="Delivery provider"
          >
            <option value="queue">queue (no external send)</option>
            <option value="mock">mock (no external send)</option>
            <option value="resend">resend (real email)</option>
            <option value="smtp_generic">smtp_generic (real email)</option>
          </select>
          <input
            value={testRecipient}
            onChange={(event) => setTestRecipient(event.target.value)}
            placeholder="Test recipient (yourself)"
            aria-label="Test recipient"
            type="email"
          />
        </div>
        <button
          type="button"
          disabled={!proposal || proposal.status !== "approved"}
          onClick={() =>
            proposal && onDeliver(proposal.id, provider, testRecipient.trim() || undefined)
          }
        >
          Process delivery
        </button>
        {prospect.contact_email ? (
          <button
            type="button"
            className="ghost"
            onClick={() => prospect.contact_email && onSuppress(prospect.contact_email)}
          >
            Suppress {prospect.contact_email}
          </button>
        ) : null}
      </fieldset>
    </div>
  );
}
