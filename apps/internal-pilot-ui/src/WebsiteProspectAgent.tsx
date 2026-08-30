import { useEffect, useMemo, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { loadStoredApiBase, resolveApiUrl } from "./apiBase";
import {
  analyzeProspect,
  approveProposal,
  createCampaign,
  createManualProspect,
  createProspectsFromCsv,
  createProposalShare,
  discoverCampaign,
  generateProposal,
  loadProposalPresentation,
  loadProspectingWorkspace,
  ProspectingApiError,
  queueProposalDelivery,
  suppressProspect,
  updateProposal,
  updateProspect,
  updateProspectingPolicy,
  type ApiAnalysis,
  type ApiProspectingPolicy,
  type ApiProposal,
  type ApiProspect,
  type ApiProspectingSummary
} from "./websiteProspectingApi";
import "./websiteProspectAgent.css";

type IconName =
  | "activity"
  | "arrow"
  | "bolt"
  | "building"
  | "calendar"
  | "check"
  | "chevron"
  | "clipboard"
  | "close"
  | "external"
  | "eye"
  | "file"
  | "filter"
  | "globe"
  | "inbox"
  | "layout"
  | "mail"
  | "menu"
  | "more"
  | "notification"
  | "people"
  | "plus"
  | "refresh"
  | "search"
  | "settings"
  | "shield"
  | "sparkles"
  | "target"
  | "trend"
  | "user"
  | "wand";

type LeadStatus = "analysis_ready" | "analyzing" | "qualified" | "proposal_ready" | "approved";
type DetailTab = "analysis" | "proposal" | "email";
type FilterKey = "all" | "review" | "qualified" | "approved";

type Finding = {
  title: string;
  detail: string;
  severity: "high" | "medium" | "positive";
  icon: IconName;
};

type Lead = {
  id: number;
  apiId?: string;
  analysisId?: string;
  proposalId?: string;
  sourceUrl?: string | null;
  evidence?: ApiAnalysis["evidence"];
  screenshot?: string;
  legalBasis?: string;
  doNotContact?: boolean;
  emailSubject?: string;
  emailDraft?: string;
  proposalHeadline?: string;
  proposalSitemap?: string[];
  proposalBenefits?: Array<{ title: string; detail: string }>;
  proposalPackages?: Array<{ name: string; price_sek: number; recommended?: boolean; features: string[] }>;
  proposalTimeline?: Array<{ week: string; title: string }>;
  company: string;
  initials: string;
  orgNumber: string;
  industry: string;
  city: string;
  domain: string;
  employees: string;
  turnover: string;
  score: number;
  opportunity: number;
  status: LeadStatus;
  updated: string;
  contact: {
    name: string;
    role: string;
    email: string;
    verified: boolean;
  };
  metrics: {
    performance: number;
    seo: number;
    accessibility: number;
    mobile: number;
  };
  findings: Finding[];
  pitch: string;
  accent: string;
};


const STATUS_LABELS: Record<LeadStatus, string> = {
  analysis_ready: "Klar för granskning",
  analyzing: "Analyseras",
  qualified: "Kvalificerad",
  proposal_ready: "Förslag klart",
  approved: "Godkänd för utskick"
};

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    activity: <><path d="M3 12h4l2.2-7 4.1 14 2.1-7H21" /></>,
    arrow: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
    bolt: <><path d="m13 2-9 12h7l-1 8 9-12h-7z" /></>,
    building: <><path d="M4 21V5l8-3 8 3v16" /><path d="M9 21v-4h6v4M8 8h.01M12 8h.01M16 8h.01M8 12h.01M12 12h.01M16 12h.01" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
    chevron: <><path d="m9 18 6-6-6-6" /></>,
    clipboard: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4.5V3h6v1.5M9 9h6M9 13h6M9 17h4" /></>,
    close: <><path d="M6 6l12 12M18 6 6 18" /></>,
    external: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6" /></>,
    eye: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z" /><circle cx="12" cy="12" r="2.5" /></>,
    file: <><path d="M6 2h8l4 4v16H6z" /><path d="M14 2v5h5M9 12h6M9 16h6" /></>,
    filter: <><path d="M4 5h16M7 12h10M10 19h4" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.6 3.5 5.6 3.5 9s-1 6.4-3.5 9c-2.5-2.6-3.5-5.6-3.5-9S9.5 5.6 12 3z" /></>,
    inbox: <><path d="M4 4h16v16H4z" /><path d="M4 14h4l2 3h4l2-3h4" /></>,
    layout: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 9v12" /></>,
    mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m4 7 8 6 8-6" /></>,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    more: <><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none" /></>,
    notification: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
    people: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M19 8v6M22 11h-6" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 8a7 7 0 0 1 11.4-2.2L20 8M4 16l2.5 2.2A7 7 0 0 0 17.9 16" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1z" /></>,
    shield: <><path d="M12 3 4.5 6v5.5c0 4.7 3.2 7.9 7.5 9.5 4.3-1.6 7.5-4.8 7.5-9.5V6z" /><path d="m9 12 2 2 4-5" /></>,
    sparkles: <><path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2zM19 14l.7 2.3L22 17l-2.3.7L19 20l-.7-2.3L16 17l2.3-.7zM5 13l.7 2.3L8 16l-2.3.7L5 19l-.7-2.3L2 16l2.3-.7z" /></>,
    target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" fill="currentColor" /></>,
    trend: <><path d="m3 17 6-6 4 4 8-9" /><path d="M15 6h6v6" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
    wand: <><path d="m15 4 5 5L8 21l-5-5zM12 7l5 5M5 3v4M3 5h4M19 15v4M17 17h4" /></>
  };

  return (
    <svg aria-hidden="true" className="wpa-icon" fill="none" height={size} viewBox="0 0 24 24" width={size}>
      <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8">{paths[name]}</g>
    </svg>
  );
}

function formatSek(value: number): string {
  return new Intl.NumberFormat("sv-SE", { style: "currency", currency: "SEK", maximumFractionDigits: 0 }).format(value);
}

function operatorErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ProspectingApiError) {
    if (error.code === "WEBSITE_FETCH_DISABLED") {
      return "Webbhämtning är avstängd på servern. Operatör sätter PROSPECTING_FETCH_ENABLED efter egress-kontroll.";
    }
    if (error.code === "DISCOVERY_PROVIDER_DISABLED" || error.code === "DISCOVERY_PROVIDER_NOT_CONFIGURED") {
      return "Sökning via Places är avstängd. Använd Analysera URL för ett skarpt case.";
    }
    if (error.code === "REAL_EMAIL_DISABLED") {
      return "Verklig e-post är avstängd. Utskicket köas tills H8c är applicerad på host.";
    }
    return error.message;
  }
  return error instanceof Error ? error.message : fallback;
}

function statusClass(status: LeadStatus): string {
  if (status === "approved") return "success";
  if (status === "analysis_ready" || status === "proposal_ready") return "review";
  if (status === "analyzing") return "running";
  return "neutral";
}

function stableLeadId(value: string): number {
  return Math.abs(Array.from(value).reduce((hash, character) => ((hash << 5) - hash + character.charCodeAt(0)) | 0, 0)) + 10_000;
}

function apiProspectToLead(prospect: ApiProspect): Lead {
  const analysis = prospect.latest_analysis;
  const proposal = prospect.latest_proposal;
  const mappedStatus: LeadStatus = prospect.do_not_contact
    ? "qualified"
    : proposal?.status === "approved" || prospect.status === "approved"
      ? "approved"
      : proposal
        ? "proposal_ready"
        : analysis?.status === "complete"
          ? "analysis_ready"
          : "qualified";
  const companyWords = prospect.company_name.split(/\s+/).filter(Boolean);
  const initials = companyWords.slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "PR";
  const pageSpeed = analysis?.technical?.pagespeed as { final_screenshot?: unknown } | undefined;
  const screenshot = typeof pageSpeed?.final_screenshot === "string" ? pageSpeed.final_screenshot : undefined;
  const findings: Finding[] = (analysis?.findings || []).map((finding) => ({
    title: finding.title,
    detail: finding.detail,
    severity: finding.severity,
    icon: finding.key.includes("mobile") || finding.key.includes("viewport") ? "globe" : finding.key.includes("cta") || finding.key.includes("form") ? "target" : finding.key.includes("local") || finding.key.includes("seo") ? "search" : finding.severity === "positive" ? "sparkles" : "activity"
  }));
  return {
    id: stableLeadId(prospect.id),
    apiId: prospect.id,
    analysisId: analysis?.id,
    proposalId: proposal?.id,
    sourceUrl: prospect.source_url,
    evidence: analysis?.evidence || [],
    screenshot,
    legalBasis: prospect.legal_basis,
    doNotContact: prospect.do_not_contact,
    emailSubject: proposal?.email_subject,
    emailDraft: proposal?.email_body,
    proposalHeadline: proposal?.headline,
    proposalSitemap: proposal?.sitemap,
    proposalBenefits: proposal?.benefits,
    proposalPackages: proposal?.packages,
    proposalTimeline: proposal?.timeline,
    company: prospect.company_name,
    initials,
    orgNumber: prospect.organization_number || "Ej angivet",
    industry: prospect.industry || "Ej klassificerad",
    city: prospect.city || "Sverige",
    domain: prospect.normalized_domain,
    employees: prospect.employee_band || "Ej angivet",
    turnover: prospect.turnover_label || "Ej angivet",
    score: analysis?.improvement_score || prospect.qualification_score,
    opportunity: prospect.estimated_value_sek,
    status: mappedStatus,
    updated: "Sparad i SalesOS",
    contact: {
      name: prospect.contact_name || "Kontakt saknas",
      role: prospect.contact_role || "Ej verifierad",
      email: prospect.contact_email || "",
      verified: prospect.contact_verified
    },
    metrics: analysis?.metrics || { performance: 0, seo: 0, accessibility: 0, mobile: 0 },
    findings: findings.length ? findings : [{ title: "Analys väntar", detail: "Starta en säker webbplatsanalys för att skapa ett evidenspaket.", severity: "medium", icon: "activity" }],
    pitch: proposal?.summary || `Ett mätbart webbupplägg för ${prospect.company_name} med tydligare kundresor och bättre uppföljning.`,
    accent: "#2867d8"
  };
}

function MetricBar({ label, value }: { label: string; value: number }) {
  const level = value < 45 ? "low" : value < 65 ? "mid" : "good";
  return (
    <div className="wpa-metric">
      <div className="wpa-metric__head"><span>{label}</span><strong className={level}>{value}</strong></div>
      <div className="wpa-metric__track"><span className={level} style={{ width: `${value}%` }} /></div>
    </div>
  );
}

function WebsiteMockup({ lead }: { lead: Lead }) {
  return (
    <div className="wpa-site-mock" style={{ "--mock-accent": lead.accent } as CSSProperties}>
      <div className="wpa-browser-bar"><i /><i /><i /><span>{lead.domain}</span></div>
      <div className="wpa-site-nav">
        <strong>{lead.initials}</strong>
        <div><span>Tjänster</span><span>Projekt</span><span>Om oss</span><b>Få offert</b></div>
      </div>
      <div className="wpa-site-hero">
        <small>LOKAL EXPERTIS · TRYGG LEVERANS</small>
        <h4>{lead.company.split(" AB")[0]}</h4>
        <p>{lead.pitch}</p>
        <button type="button">Kostnadsfri offert <Icon name="arrow" size={12} /></button>
      </div>
      <div className="wpa-site-proof"><span>✓ Certifierade</span><span>✓ Tydlig process</span><span>★ 4,8 av 5</span></div>
      <div className="wpa-site-cards"><i /><i /><i /></div>
    </div>
  );
}

function CampaignModal({ onClose, onStart }: { onClose: () => void; onStart: (criteria: string) => void }) {
  const [industry, setIndustry] = useState("Bygg & hantverk");
  const [region, setRegion] = useState("Mälardalen");
  const [minScore, setMinScore] = useState("65");

  function submit(event: FormEvent) {
    event.preventDefault();
    onStart(`${industry} · ${region} · minst ${minScore} poäng`);
  }

  return (
    <div className="wpa-modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="campaign-title" aria-modal="true" className="wpa-modal wpa-campaign-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header className="wpa-modal__header">
          <div className="wpa-modal__icon"><Icon name="target" size={21} /></div>
          <div><span>Ny prospektering</span><h2 id="campaign-title">Välj vilka företag agenten ska hitta</h2></div>
          <button aria-label="Stäng" className="wpa-icon-button" onClick={onClose} type="button"><Icon name="close" /></button>
        </header>
        <form onSubmit={submit}>
          <div className="wpa-form-grid">
            <label>Bransch<select onChange={(event) => setIndustry(event.target.value)} value={industry}><option>Bygg & hantverk</option><option>Ekonomi & juridik</option><option>Hälsa & skönhet</option><option>Lokala tjänsteföretag</option></select></label>
            <label>Region<select onChange={(event) => setRegion(event.target.value)} value={region}><option>Mälardalen</option><option>Stockholm</option><option>Västra Götaland</option><option>Hela Sverige</option></select></label>
            <label>Minsta förbättringspoäng<select onChange={(event) => setMinScore(event.target.value)} value={minScore}><option value="55">55 — bred sökning</option><option value="65">65 — rekommenderad</option><option value="75">75 — hög potential</option></select></label>
            <label>Företagsstorlek<select defaultValue="3–25"><option>1–10</option><option>3–25</option><option>11–50</option></select></label>
          </div>
          <div className="wpa-source-box">
            <Icon name="shield" size={19} />
            <div><strong>Säkra källor och varsam frekvens</strong><p>Agenten använder publika företags- och webbuppgifter, respekterar robots.txt och sparar källan till varje observation.</p></div>
          </div>
          <footer className="wpa-modal__footer"><button className="wpa-button secondary" onClick={onClose} type="button">Avbryt</button><button className="wpa-button primary" type="submit"><Icon name="sparkles" /> Starta agenten</button></footer>
        </form>
      </section>
    </div>
  );
}

function ManualProspectModal({
  busy,
  fetchEnabled,
  onClose,
  onCreate
}: {
  busy: boolean;
  fetchEnabled: boolean;
  onClose: () => void;
  onCreate: (payload: { company_name: string; website_url: string; contact_name: string; contact_email: string; city: string; legitimate_interest_note: string }) => void;
}) {
  const [company, setCompany] = useState("");
  const [website, setWebsite] = useState("https://");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [city, setCity] = useState("");
  const [basis, setBasis] = useState("");
  const valid = company.trim().length > 1 && /^https?:\/\//i.test(website) && basis.trim().length > 10;

  return (
    <div className="wpa-modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="manual-title" aria-modal="true" className="wpa-modal wpa-manual-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header className="wpa-modal__header">
          <div className="wpa-modal__icon"><Icon name="globe" size={21} /></div>
          <div><span>Evidensbaserad analys</span><h2 id="manual-title">Lägg till och analysera en webbplats</h2></div>
          <button aria-label="Stäng" className="wpa-icon-button" onClick={onClose} type="button"><Icon name="close" /></button>
        </header>
        <div className="wpa-form-grid">
          <label>Företagsnamn<input onChange={(event) => setCompany(event.target.value)} placeholder="Exempel Bygg AB" value={company} /></label>
          <label>Publik webbplats<input onChange={(event) => setWebsite(event.target.value)} placeholder="https://example.se" value={website} /></label>
          <label>Ort<input onChange={(event) => setCity(event.target.value)} placeholder="Göteborg" value={city} /></label>
          <label>Kontaktperson<input onChange={(event) => setContactName(event.target.value)} placeholder="Namn (valfritt)" value={contactName} /></label>
          <label>Kontaktens e-post<input onChange={(event) => setContactEmail(event.target.value)} placeholder="Verifieras före utskick" type="email" value={contactEmail} /></label>
          <label className="wpa-form-wide">Berättigat intresse / relevans<textarea onChange={(event) => setBasis(event.target.value)} placeholder="Varför är erbjudandet relevant för detta B2B-företag?" rows={3} value={basis} /></label>
        </div>
        <div className="wpa-source-box"><Icon name="shield" size={19} /><div><strong>Avgränsad och säker kontroll</strong><p>Endast den angivna publika sidan hämtas. Robots.txt respekteras, privata nätverk blockeras och varje observation får ett källbevis.</p></div></div>
        <footer className="wpa-modal__footer"><button className="wpa-button secondary" onClick={onClose} type="button">Avbryt</button><button className="wpa-button primary" disabled={!valid || busy} onClick={() => onCreate({ company_name: company.trim(), website_url: website.trim(), contact_name: contactName.trim(), contact_email: contactEmail.trim(), city: city.trim(), legitimate_interest_note: basis.trim() })} type="button"><Icon name="activity" /> {busy ? "Analyserar …" : "Spara & analysera"}</button></footer>
      </section>
    </div>
  );
}

function CsvBulkModal({
  busy,
  onClose,
  onImport
}: {
  busy: boolean;
  onClose: () => void;
  onImport: (csvText: string) => void;
}) {
  const [csvText, setCsvText] = useState(
    "company_name,website_url,city\nExempel Bygg AB,https://example.se,Göteborg\n"
  );
  const valid = csvText.toLowerCase().includes("company_name") && csvText.toLowerCase().includes("website_url") && csvText.trim().split("\n").length > 1;

  return (
    <div className="wpa-modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="csv-title" aria-modal="true" className="wpa-modal wpa-manual-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header className="wpa-modal__header">
          <div className="wpa-modal__icon"><Icon name="activity" size={21} /></div>
          <div><span>CSV-intag</span><h2 id="csv-title">Klistra in en lista (max 50 rader)</h2></div>
          <button aria-label="Stäng" className="wpa-icon-button" onClick={onClose} type="button"><Icon name="close" /></button>
        </header>
        <label className="wpa-form-wide">
          CSV med kolumnerna company_name, website_url och valfri city
          <textarea onChange={(event) => setCsvText(event.target.value)} rows={10} value={csvText} />
        </label>
        <div className="wpa-source-box">
          <Icon name="shield" size={19} />
          <div>
            <strong>Ingen e-post från CSV</strong>
            <p>Kontaktadresser i filen ignoreras. Dubbletter hoppas över. Ingen analys eller utskick startas automatiskt.</p>
          </div>
        </div>
        <footer className="wpa-modal__footer">
          <button className="wpa-button secondary" onClick={onClose} type="button">Avbryt</button>
          <button className="wpa-button primary" disabled={!valid || busy} onClick={() => onImport(csvText)} type="button">
            <Icon name="plus" /> {busy ? "Importerar …" : "Importera lista"}
          </button>
        </footer>
      </section>
    </div>
  );
}

function ContactVerificationModal({ lead, busy, onClose, onVerify }: { lead: Lead; busy: boolean; onClose: () => void; onVerify: (source: string) => void }) {
  const [source, setSource] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  return (
    <div className="wpa-modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="contact-verify-title" aria-modal="true" className="wpa-modal wpa-contact-verify-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header className="wpa-modal__header"><div className="wpa-modal__icon review"><Icon name="user" size={21} /></div><div><span>Kontaktkontroll</span><h2 id="contact-verify-title">Verifiera {lead.contact.name}</h2></div><button aria-label="Stäng" className="wpa-icon-button" onClick={onClose} type="button"><Icon name="close" /></button></header>
        <div className="wpa-contact-verify-body"><div><span>E-post</span><strong>{lead.contact.email || "Saknas"}</strong></div><label>Verifieringskälla<input onChange={(event) => setSource(event.target.value)} placeholder="Företagets webbplats, telefonsamtal eller annan dokumenterad källa" value={source} /></label><label className="wpa-verify-confirm"><input checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" /><span>Jag har kontrollerat att personen, rollen och e-postadressen är aktuella.</span></label></div>
        <footer className="wpa-modal__footer"><button className="wpa-button secondary" onClick={onClose} type="button">Avbryt</button><button className="wpa-button primary approve" disabled={!confirmed || source.trim().length < 5 || !lead.contact.email || busy} onClick={() => onVerify(source.trim())} type="button"><Icon name="check" /> {busy ? "Sparar …" : "Spara verifiering"}</button></footer>
      </section>
    </div>
  );
}

function ProposalEditorModal({ lead, busy, onClose, onSave }: { lead: Lead; busy: boolean; onClose: () => void; onSave: (payload: Pick<ApiProposal, "headline" | "summary" | "sitemap" | "benefits" | "packages" | "timeline">) => void }) {
  const [headline, setHeadline] = useState(lead.proposalHeadline || `Ett tydligare digitalt säljflöde för ${lead.company}`);
  const [summary, setSummary] = useState(lead.pitch);
  const [sitemap, setSitemap] = useState((lead.proposalSitemap || ["Start", "Tjänster", "Projekt", "Om oss", "Kontakt", "Offert"]).join("\n"));
  const [benefits, setBenefits] = useState((lead.proposalBenefits || [
    { title: "Fler relevanta leads", detail: "Tydliga erbjudanden och CTA per kundbehov." },
    { title: "Mindre manuellt arbete", detail: "Kvalificerande formulär och automatisk mötesbokning." },
    { title: "Starkare lokal SEO", detail: "Ortssidor och teknisk struktur som går att mäta." }
  ]).map((item) => `${item.title} | ${item.detail}`).join("\n"));
  const [packages, setPackages] = useState((lead.proposalPackages || [
    { name: "Start", price_sek: Math.round(lead.opportunity * 0.7), features: ["Design", "Mobilanpassning"] },
    { name: "Tillväxt", price_sek: lead.opportunity, recommended: true, features: ["Design", "SEO", "Konverteringsflöde"] },
    { name: "Partner", price_sek: Math.round(lead.opportunity * 1.4), features: ["Allt i Tillväxt", "Löpande optimering"] }
  ]).map((item) => `${item.name} | ${item.price_sek}`).join("\n"));
  const [timeline, setTimeline] = useState((lead.proposalTimeline || [
    { week: "Vecka 1", title: "Strategi och innehåll" },
    { week: "Vecka 2–4", title: "Design och utveckling" },
    { week: "Vecka 5", title: "Kvalitetssäkring och lansering" }
  ]).map((item) => `${item.week} | ${item.title}`).join("\n"));
  const sitemapRows = sitemap.split("\n").map((item) => item.trim()).filter(Boolean);
  const valid = headline.trim().length >= 5 && summary.trim().length >= 10 && sitemapRows.length > 0;

  function pipeRows(value: string): string[][] {
    return value.split("\n").map((line) => line.split("|").map((part) => part.trim())).filter((parts) => parts[0]);
  }

  function submit(): void {
    const benefitRows = pipeRows(benefits);
    const packageRows = pipeRows(packages);
    const timelineRows = pipeRows(timeline);
    onSave({
      headline: headline.trim(),
      summary: summary.trim(),
      sitemap: sitemapRows,
      benefits: benefitRows.map(([title, detail]) => ({ title, detail: detail || title })),
      packages: packageRows.map(([name, price], index) => ({
        name,
        price_sek: Math.max(0, Number.parseInt(price || "0", 10) || 0),
        recommended: index === 1,
        features: lead.proposalPackages?.[index]?.features || ["Kundanpassad design", "Mätbar leverans"]
      })),
      timeline: timelineRows.map(([week, title]) => ({ week, title: title || week }))
    });
  }

  return (
    <div className="wpa-modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="proposal-editor-title" aria-modal="true" className="wpa-modal wpa-proposal-editor-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header className="wpa-modal__header"><div className="wpa-modal__icon"><Icon name="file" size={21} /></div><div><span>Versionshanterat utkast</span><h2 id="proposal-editor-title">Redigera hela kundupplägget</h2></div><button aria-label="Stäng" className="wpa-icon-button" onClick={onClose} type="button"><Icon name="close" /></button></header>
        <div className="wpa-proposal-editor-body">
          <label>Rubrik<input onChange={(event) => setHeadline(event.target.value)} value={headline} /></label>
          <label>Sammanfattning<textarea onChange={(event) => setSummary(event.target.value)} rows={3} value={summary} /></label>
          <div className="wpa-proposal-editor-grid"><label>Sidstruktur<small>En sida per rad</small><textarea onChange={(event) => setSitemap(event.target.value)} rows={6} value={sitemap} /></label><label>Effekter<small>Rubrik | beskrivning</small><textarea onChange={(event) => setBenefits(event.target.value)} rows={6} value={benefits} /></label><label>Paket<small>Namn | pris i SEK</small><textarea onChange={(event) => setPackages(event.target.value)} rows={5} value={packages} /></label><label>Tidslinje<small>Period | aktivitet</small><textarea onChange={(event) => setTimeline(event.target.value)} rows={5} value={timeline} /></label></div>
        </div>
        <div className="wpa-warning"><Icon name="shield" /><span>Ett godkänt förslag är låst. Skapa en ny version innan du ändrar ett redan godkänt upplägg.</span></div>
        <footer className="wpa-modal__footer"><button className="wpa-button secondary" onClick={onClose} type="button">Avbryt</button><button className="wpa-button primary" disabled={!valid || busy} onClick={submit} type="button"><Icon name="check" /> {busy ? "Sparar …" : "Spara utkast"}</button></footer>
      </section>
    </div>
  );
}

function ReviewModal({ lead, onClose, onApprove }: { lead: Lead; onClose: () => void; onApprove: () => void }) {
  const [checks, setChecks] = useState([false, false, false, false]);
  const allChecked = checks.every(Boolean);
  const rows = [
    ["Analysen är saklig", "Observationerna stämmer mot källbevisen för kundens nuvarande webbplats."],
    ["Kontaktuppgiften är verifierad", `${lead.contact.name} · ${lead.contact.email || "e-post saknas"}`],
    ["Rättslig grund är dokumenterad", lead.legalBasis || "Verifiera berättigat intresse eller samtycke."],
    ["Förslag och e-post är godkända", "Ton, omfattning, delningslänk och nästa steg är redo att delas."]
  ];

  return (
    <div className="wpa-modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="review-title" aria-modal="true" className="wpa-modal wpa-review-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header className="wpa-modal__header">
          <div className="wpa-modal__icon review"><Icon name="shield" size={21} /></div>
          <div><span>Mänsklig verifiering</span><h2 id="review-title">Godkänn leverans till {lead.company}</h2></div>
          <button aria-label="Stäng" className="wpa-icon-button" onClick={onClose} type="button"><Icon name="close" /></button>
        </header>
        <p className="wpa-review-intro">Inget skickas innan alla kontroller är bekräftade. Du kan gå tillbaka och redigera innehållet när som helst.</p>
        <div className="wpa-review-list">
          {rows.map(([title, description], index) => (
            <label className={checks[index] ? "checked" : ""} key={title}>
              <input checked={checks[index]} onChange={() => setChecks((current) => current.map((value, itemIndex) => itemIndex === index ? !value : value))} type="checkbox" />
              <span className="wpa-custom-check"><Icon name="check" size={14} /></span>
              <span><strong>{title}</strong><small>{description}</small></span>
            </label>
          ))}
        </div>
        <div className="wpa-delivery-summary"><Icon name="mail" /><div><span>Leverans</span><strong>{lead.contact.email}</strong><small>Personligt e-postutkast + länk till kundförslag</small></div></div>
        <footer className="wpa-modal__footer"><button className="wpa-button secondary" onClick={onClose} type="button">Fortsätt redigera</button><button className="wpa-button primary approve" disabled={!allChecked} onClick={onApprove} type="button"><Icon name="check" /> Godkänn för leverans</button></footer>
      </section>
    </div>
  );
}

function AutomationModal({ onClose, onSave }: { onClose: () => void; onSave: (enabled: boolean) => void }) {
  const [enabled, setEnabled] = useState(false);
  return (
    <div className="wpa-modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="automation-title" aria-modal="true" className="wpa-modal wpa-automation-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header className="wpa-modal__header">
          <div className="wpa-modal__icon"><Icon name="settings" size={21} /></div>
          <div><span>Leveranskontroll</span><h2 id="automation-title">Från verifiering till automation</h2></div>
          <button aria-label="Stäng" className="wpa-icon-button" onClick={onClose} type="button"><Icon name="close" /></button>
        </header>
        <div className="wpa-automation-step active"><b>1</b><div><strong>Manuell verifiering</strong><p>Varje analys, kontakt och e-post godkänns av en person före leverans.</p></div><span>Aktiv nu</span></div>
        <div className="wpa-automation-step"><b>2</b><div><strong>Regelstyrd automation</strong><p>Leverera automatiskt först när kvalitet, kontaktverifiering och opt-out-policy är godkända.</p></div><label className="wpa-switch"><input checked={enabled} onChange={(event) => setEnabled(event.target.checked)} type="checkbox" /><i /></label></div>
        {enabled ? <div className="wpa-warning"><Icon name="shield" /><span>Regelstyrd automation sparas i tenant-policyn. Verklig e-postleverans kräver godkänd provider på host.</span></div> : null}
        <footer className="wpa-modal__footer"><button className="wpa-button secondary" onClick={onClose} type="button">Avbryt</button><button className="wpa-button primary" onClick={() => onSave(enabled)} type="button">Spara inställning</button></footer>
      </section>
    </div>
  );
}

function ProviderSettingsModal({
  onClose,
  onOpenAutomation,
  policy,
  summary
}: {
  onClose: () => void;
  onOpenAutomation: () => void;
  policy: ApiProspectingPolicy | null;
  summary: ApiProspectingSummary | null;
}) {
  const discovery = summary?.providers.discovery;
  const websiteFetch = summary?.providers.website_fetch;
  const email = summary?.providers.email;
  return (
    <div className="wpa-modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="provider-settings-title" aria-modal="true" className="wpa-modal wpa-automation-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header className="wpa-modal__header">
          <div className="wpa-modal__icon"><Icon name="settings" size={21} /></div>
          <div><span>Operatörsstatus</span><h2 id="provider-settings-title">Nova-leverantörer och policy</h2></div>
          <button aria-label="Stäng" className="wpa-icon-button" onClick={onClose} type="button"><Icon name="close" /></button>
        </header>
        <div className="wpa-provider-settings">
          <article><span>Webbanalys</span><strong>{websiteFetch?.enabled ? "Aktiverad" : "Låst"}</strong><small>Robots.txt respekteras · privata nätverk blockeras</small></article>
          <article><span>Discovery</span><strong>{discovery?.provider && discovery.provider !== "disabled" ? discovery.provider : "Avstängd"}</strong><small>{discovery?.configured ? "API konfigurerat" : "Manuell URL eller CSV"}</small></article>
          <article><span>E-post</span><strong>{email?.real_send_enabled && email?.configured ? "Verklig sändning" : "Kö/mock"}</strong><small>{email?.provider || "disabled"}{email?.from_addresses?.length ? ` · ${email.from_addresses.join(", ")}` : ""}</small></article>
          <article><span>Policy</span><strong>{policy?.mode === "rules_assisted" ? "Regelstyrd" : "Manuell granskning"}</strong><small>Daglig gräns {policy?.daily_delivery_limit ?? 20} · minsta poäng {policy?.minimum_score ?? 80}</small></article>
          <article><span>Schemaläggare</span><strong>{policy?.scheduler_enabled ? "Aktiv" : "Låst"}</strong><small>Bakgrundskörning kräver operatörsgodkännande på host</small></article>
        </div>
        <footer className="wpa-modal__footer"><button className="wpa-button secondary" onClick={onClose} type="button">Stäng</button><button className="wpa-button primary" onClick={onOpenAutomation} type="button">Hantera automation</button></footer>
      </section>
    </div>
  );
}

function InternalBusinessCaseModal({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const recommended = lead.proposalPackages?.find((item) => item.recommended)?.price_sek || lead.opportunity || 0;
  const [investment, setInvestment] = useState(recommended ? String(recommended) : "");
  const [contribution, setContribution] = useState("");
  const [closeRate, setCloseRate] = useState("");
  const investmentValue = Number(investment) || 0;
  const contributionValue = Number(contribution) || 0;
  const closeRateValue = Number(closeRate) || 0;
  const dealsToBreakEven = investmentValue > 0 && contributionValue > 0
    ? Math.ceil(investmentValue / contributionValue)
    : null;
  const qualifiedLeadsNeeded = dealsToBreakEven && closeRateValue > 0
    ? Math.ceil(dealsToBreakEven / (closeRateValue / 100))
    : null;

  return (
    <div className="wpa-modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="internal-case-title" aria-modal="true" className="wpa-modal wpa-internal-case-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header className="wpa-modal__header"><div className="wpa-modal__icon review"><Icon name="shield" size={21} /></div><div><span>ENDAST INTERN ARBETSYTA</span><h2 id="internal-case-title">Privat affärskalkyl för {lead.company}</h2></div><button aria-label="Stäng" className="wpa-icon-button" onClick={onClose} type="button"><Icon name="close" /></button></header>
        <div className="wpa-internal-case-privacy"><Icon name="shield" size={17} /><div><strong>Marginaldata lämnar aldrig den här dialogen</strong><p>Värdena finns bara i minnet i denna webbläsarflik. De sparas inte, skickas inte till API:t och följer aldrig med kundförslaget, mötesfilmen eller delningslänken.</p></div></div>
        <div className="wpa-internal-case-grid">
          <label>Föreslagen investering, SEK<input min="0" onChange={(event) => setInvestment(event.target.value)} step="1000" type="number" value={investment} /></label>
          <label>Internt täckningsbidrag per ny affär<input min="0" onChange={(event) => setContribution(event.target.value)} step="1000" type="number" value={contribution} /></label>
          <label>Intern stängningsgrad från kvalificerat lead, %<input max="100" min="0" onChange={(event) => setCloseRate(event.target.value)} step="1" type="number" value={closeRate} /></label>
        </div>
        <div className="wpa-internal-case-results">
          <article><span>Affärer till intern break-even</span><strong>{dealsToBreakEven ?? "—"}</strong><small>Investering ÷ täckningsbidrag, avrundat uppåt</small></article>
          <article><span>Kvalificerade leads som behövs</span><strong>{qualifiedLeadsNeeded ?? "—"}</strong><small>Break-even-affärer ÷ intern stängningsgrad</small></article>
        </div>
        <footer className="wpa-modal__footer"><button className="wpa-button primary" onClick={onClose} type="button"><Icon name="check" /> Stäng och rensa värden</button></footer>
      </section>
    </div>
  );
}

function NovaLoginGate({
  apiBase,
  onLogin
}: {
  apiBase: string;
  onLogin: (token: string) => void;
}) {
  const [email, setEmail] = useState("tenant-wide@example.invalid");
  const [password, setPassword] = useState("salesos");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = new URLSearchParams();
      body.set("username", email.trim());
      body.set("password", password);
      const response = await fetch(resolveApiUrl(apiBase, "/api/v1/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body
      });
      const data = await response.json() as { access_token?: string; detail?: string };
      if (!response.ok || !data.access_token) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Inloggningen misslyckades.");
      }
      window.localStorage.setItem("salesos.salesDeskToken", data.access_token);
      onLogin(data.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inloggningen misslyckades.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wpa-login-gate">
      <section className="wpa-login-gate__card">
        <div className="wpa-brand"><span className="wpa-brand__mark"><Icon name="sparkles" size={19} /></span><div><strong>Nova</strong><small>Webbprospektering</small></div></div>
        <h1>Logga in för att fortsätta</h1>
        <p>Tenant-isolerad lagring, revisionslogg och mänskligt mandat före varje utskick.</p>
        <form onSubmit={(event) => void submit(event)}>
          <label>E-post<input autoComplete="username" onChange={(event) => setEmail(event.target.value)} type="email" value={email} /></label>
          <label>Lösenord<input autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} type="password" value={password} /></label>
          {error ? <p className="wpa-login-gate__error">{error}</p> : null}
          <button className="wpa-button primary" disabled={busy || !email.trim() || !password} type="submit">{busy ? "Loggar in …" : "Logga in"}</button>
        </form>
        <div className="wpa-login-gate__links">
          <a href="/">Till SalesOS start</a>
          <a href="/nova-video">Se Nova-filmen</a>
        </div>
      </section>
    </main>
  );
}

export function WebsiteProspectAgent() {
  const apiBase = loadStoredApiBase();
  const [sessionToken, setSessionToken] = useState(() => window.localStorage.getItem("salesos.salesDeskToken") || "");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [detailTab, setDetailTab] = useState<DetailTab>("analysis");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [search, setSearch] = useState("");
  const [campaignOpen, setCampaignOpen] = useState(false);
  const [manualProspectOpen, setManualProspectOpen] = useState(false);
  const [manualProspectBusy, setManualProspectBusy] = useState(false);
  const [csvBulkOpen, setCsvBulkOpen] = useState(false);
  const [csvBulkBusy, setCsvBulkBusy] = useState(false);
  const [contactVerifyOpen, setContactVerifyOpen] = useState(false);
  const [contactVerifyBusy, setContactVerifyBusy] = useState(false);
  const [proposalEditorOpen, setProposalEditorOpen] = useState(false);
  const [proposalEditorBusy, setProposalEditorBusy] = useState(false);
  const [internalBusinessCaseOpen, setInternalBusinessCaseOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [automationOpen, setAutomationOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [automationEnabled, setAutomationEnabled] = useState(false);
  const [agentRunning, setAgentRunning] = useState(false);
  const [testDeliveryBusy, setTestDeliveryBusy] = useState(false);
  const [operatorEmail, setOperatorEmail] = useState("");
  const [campaignCriteria, setCampaignCriteria] = useState("Bygg & hantverk · Mälardalen");
  const [toast, setToast] = useState<string | null>(null);
  const [emailBody, setEmailBody] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
  const [fromAddress, setFromAddress] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [apiState, setApiState] = useState<"loading" | "live" | "live_empty" | "error">("loading");
  const [apiSummary, setApiSummary] = useState<ApiProspectingSummary | null>(null);
  const [apiPolicy, setApiPolicy] = useState<ApiProspectingPolicy | null>(null);
  const token = sessionToken;
  const homePath = "/nova";

  const selected = leads.find((lead) => lead.id === selectedId) ?? leads[0];
  const liveSession = Boolean(token) && (apiState === "live" || apiState === "live_empty");
  const fetchEnabled = Boolean(apiSummary?.providers.website_fetch?.enabled);
  const discoveryConfigured = Boolean(apiSummary?.providers.discovery?.configured);

  async function refreshWorkspace(showMessage = false): Promise<void> {
    if (!token) {
      setApiState("loading");
      setLeads([]);
      setSelectedId(0);
      return;
    }
    setApiState("loading");
    try {
      const workspace = await loadProspectingWorkspace(apiBase, token);
      setApiSummary(workspace.summary);
      setApiPolicy(workspace.policy);
      setAutomationEnabled(workspace.policy.mode === "rules_assisted");
      if (workspace.prospects.length > 0) {
        const liveLeads = workspace.prospects.map(apiProspectToLead);
        setLeads(liveLeads);
        setSelectedId((current) => liveLeads.some((lead) => lead.id === current) ? current : liveLeads[0].id);
        setApiState("live");
      } else {
        setLeads([]);
        setSelectedId(0);
        setApiState("live_empty");
      }
      if (showMessage) setToast("Arbetsytan har synkroniserats med SalesOS API.");
    } catch {
      setApiState("error");
      setLeads([]);
      setSelectedId(0);
    }
  }

  function handleLogin(nextToken: string) {
    setSessionToken(nextToken);
  }

  function handleLogout() {
    window.localStorage.removeItem("salesos.salesDeskToken");
    setSessionToken("");
    setLeads([]);
    setSelectedId(0);
    setApiSummary(null);
    setApiPolicy(null);
    setApiState("loading");
  }

  useEffect(() => {
    void refreshWorkspace();
  }, [sessionToken]);

  useEffect(() => {
    if (!token) {
      setOperatorEmail("");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch(resolveApiUrl(apiBase, "/api/v1/auth/me"), {
          headers: { Accept: "application/json", Authorization: `Bearer ${token}` }
        });
        if (!response.ok || cancelled) return;
        const profile = await response.json() as { email?: string };
        if (!cancelled && profile.email) setOperatorEmail(profile.email);
      } catch {
        // Operator email is optional; test delivery shows a helpful toast when missing.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBase, token]);

  useEffect(() => {
    if (!selected) return;
    setEmailSubject(selected.emailSubject || `3 konkreta förbättringar för ${selected.domain}`);
    setEmailBody(
      selected.emailDraft || `Hej ${selected.contact.name.split(" ")[0]},\n\nJag tittade på ${selected.domain} och såg flera konkreta möjligheter att göra webbplatsen snabbare, tydligare och bättre på att skapa relevanta offertförfrågningar.\n\nVi har tagit fram en kort analys och ett nytt upplägg specifikt för ${selected.company}. De största möjligheterna är bättre mobilprestanda, en tydligare väg till kontakt och starkare lokal synlighet.\n\nJag delar gärna genomgången i ett kort 20-minutersmöte. Passar tisdag eller torsdag nästa vecka?\n\nVänliga hälsningar,\nErik på SalesOS Webbstudio`
    );
  }, [selected?.id, selected?.company, selected?.contact.name, selected?.domain, selected?.emailDraft]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const filteredLeads = useMemo(() => {
    const term = search.trim().toLowerCase();
    return leads.filter((lead) => {
      const matchesSearch = !term || `${lead.company} ${lead.industry} ${lead.city} ${lead.domain}`.toLowerCase().includes(term);
      const matchesFilter = filter === "all"
        || (filter === "review" && ["analysis_ready", "proposal_ready"].includes(lead.status))
        || (filter === "qualified" && ["qualified", "analyzing"].includes(lead.status))
        || (filter === "approved" && lead.status === "approved");
      return matchesSearch && matchesFilter;
    });
  }, [filter, leads, search]);

  const totalPipeline = leads.reduce((sum, lead) => sum + lead.opportunity, 0);
  const reviewCount = leads.filter((lead) => ["analysis_ready", "proposal_ready"].includes(lead.status)).length;

  async function startCampaign(criteria: string) {
    if (!discoveryConfigured) {
      setCampaignOpen(false);
      setToast("Sökning via Places är avstängd. Använd Analysera URL för ett skarpt case.");
      return;
    }
    setCampaignOpen(false);
    setCampaignCriteria(criteria);
    setAgentRunning(true);
    setToast("Agenten söker nu efter relevanta företag …");
    if (token) {
      try {
        const [industry, region] = criteria.split(" · ");
        const campaign = await createCampaign(apiBase, token, {
          name: `${industry || "Prospektering"} — ${region || "Sverige"}`,
          industry,
          region,
          min_score: 65,
          daily_limit: 20,
          mode: "manual_review",
          source_provider: "google_places",
          criteria: { operator_verified: true }
        });
        const result = await discoverCampaign(apiBase, token, campaign.id, industry || criteria, region);
        await refreshWorkspace();
        setToast(`${result.created.length} nya företag sparades från ${result.provider}.`);
      } catch (error) {
        setToast(operatorErrorMessage(error, "Sökningen kunde inte genomföras."));
      } finally {
        setAgentRunning(false);
      }
      return;
    }
    setAgentRunning(false);
    setToast("Logga in för att starta en sparad kampanj.");
  }

  async function analyzeSelected() {
    if (!selected) return;
    if (!fetchEnabled) {
      setToast("Webbhämtning är avstängd på servern. Operatör sätter PROSPECTING_FETCH_ENABLED efter egress-kontroll.");
      return;
    }
    setLeads((current) => current.map((lead) => lead.id === selected.id ? { ...lead, status: "analyzing", updated: "Analyseras nu" } : lead));
    setToast(`Agenten analyserar ${selected.domain} …`);
    if (token && selected.apiId) {
      try {
        const analysis = await analyzeProspect(apiBase, token, selected.apiId, true);
        const pageSpeed = analysis.technical.pagespeed as { final_screenshot?: unknown } | undefined;
        const screenshot = typeof pageSpeed?.final_screenshot === "string" ? pageSpeed.final_screenshot : undefined;
        setLeads((current) => current.map((lead) => lead.id === selected.id ? {
          ...lead,
          analysisId: analysis.id,
          score: analysis.improvement_score,
          metrics: analysis.metrics,
          findings: analysis.findings.map((finding) => ({ title: finding.title, detail: finding.detail, severity: finding.severity, icon: finding.key.includes("cta") ? "target" : "activity" })),
          evidence: analysis.evidence,
          screenshot,
          status: "analysis_ready",
          updated: "Nyss analyserad"
        } : lead));
        setDetailTab("analysis");
        setToast(`Analysen är klar med ${analysis.evidence.length} källbevis.`);
      } catch (error) {
        setLeads((current) => current.map((lead) => lead.id === selected.id ? { ...lead, status: "qualified", updated: "Analys stoppad" } : lead));
        setToast(operatorErrorMessage(error, "Analysen kunde inte genomföras."));
      }
      return;
    }
    setToast("Logga in och välj ett sparat prospekt för att analysera.");
  }

  async function openMeetingPresentation(): Promise<void> {
    if (!token || !selected?.proposalId) {
      setToast("Skapa och spara ett kundupplägg innan du startar mötesfilmen.");
      return;
    }
    const preview = window.open("", "_blank");
    if (!preview) {
      setToast("Tillåt popup-fönster för att starta mötesfilmen.");
      return;
    }
    preview.document.title = `Nova förbereder ${selected.company} …`;
    preview.document.body.innerHTML = "<p style=\"font:16px system-ui;padding:40px\">Nova bygger mötesfilmen från det verifierade kundupplägget …</p>";
    try {
      const html = await loadProposalPresentation(apiBase, token, selected.proposalId);
      preview.document.open();
      preview.document.write(html);
      preview.document.close();
      setToast("Den kundanpassade mötesfilmen är redo i ett nytt fönster.");
    } catch (error) {
      preview.close();
      setToast(error instanceof Error ? error.message : "Mötesfilmen kunde inte skapas.");
    }
  }

  async function createProposal() {
    if (!selected) return;
    if (token && selected.apiId) {
      try {
        const proposal = await generateProposal(apiBase, token, selected.apiId, selected.analysisId);
        setLeads((current) => current.map((lead) => lead.id === selected.id ? { ...lead, proposalId: proposal.id, emailSubject: proposal.email_subject, emailDraft: proposal.email_body, proposalHeadline: proposal.headline, proposalSitemap: proposal.sitemap, proposalBenefits: proposal.benefits, proposalPackages: proposal.packages, proposalTimeline: proposal.timeline, pitch: proposal.summary, status: "proposal_ready", updated: `Förslag v${proposal.version} skapat` } : lead));
        setEmailBody(proposal.email_body);
        setEmailSubject(proposal.email_subject);
        setDetailTab("proposal");
        setToast("Ett versionshanterat kundupplägg har sparats i SalesOS.");
      } catch (error) {
        setToast(error instanceof Error ? error.message : "Kundupplägget kunde inte skapas.");
      }
      return;
    }
    setToast("Logga in och välj ett sparat prospekt.");
  }

  async function saveProposalContent(payload: Pick<ApiProposal, "headline" | "summary" | "sitemap" | "benefits" | "packages" | "timeline">): Promise<void> {
    if (selected.status === "approved") {
      setToast("Godkända förslag är låsta. Skapa en ny version innan du redigerar.");
      return;
    }
    setProposalEditorBusy(true);
    try {
      if (!token || !selected.proposalId) {
        setToast("Ett sparat kundupplägg krävs.");
        return;
      }
      const proposal = await updateProposal(apiBase, token, selected.proposalId, payload);
      setLeads((current) => current.map((lead) => lead.id === selected.id ? {
        ...lead,
        proposalHeadline: proposal.headline,
        proposalSitemap: proposal.sitemap,
        proposalBenefits: proposal.benefits,
        proposalPackages: proposal.packages,
        proposalTimeline: proposal.timeline,
        pitch: proposal.summary,
        updated: `Förslag v${proposal.version} redigerat`
      } : lead));
      setProposalEditorOpen(false);
      setToast("Kundupplägget är sparat som ett redigerbart utkast.");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Kundupplägget kunde inte sparas.");
    } finally {
      setProposalEditorBusy(false);
    }
  }

  async function approveDelivery() {
    if (token && selected.proposalId) {
      try {
        await updateProposal(apiBase, token, selected.proposalId, { email_body: emailBody, email_subject: emailSubject });
        await approveProposal(apiBase, token, selected.proposalId, "Verifierad av operatör i webbprospekteringsagenten.");
        const share = await createProposalShare(apiBase, token, selected.proposalId);
        const emailCfg = apiSummary?.providers.email;
        const canSendSmtp = Boolean(
          emailCfg?.real_send_enabled && emailCfg?.provider === "smtp_generic" && emailCfg.configured
        );
        const delivery = await queueProposalDelivery(
          apiBase,
          token,
          selected.proposalId,
          canSendSmtp ? "smtp_generic" : "queue",
          share.token,
          fromAddress || emailCfg?.from_addresses?.[0]
        );
        setLeads((current) => current.map((lead) => lead.id === selected.id ? { ...lead, status: "approved", updated: "Godkänd och köad nyss" } : lead));
        setReviewOpen(false);
        setDetailTab("email");
        try {
          await navigator.clipboard?.writeText(`${window.location.origin}${share.public_path}`);
        } catch {
          // Clipboard is optional; the share remains persisted and audited.
        }
        setToast(`Godkänd, delningslänk skapad och leverans ${delivery.status}.`);
      } catch (error) {
        setToast(error instanceof Error ? `Godkännandet stoppades: ${error.message}` : "Godkännandet kunde inte slutföras.");
      }
      return;
    }
    setToast("Ett sparat och godkänt kundupplägg krävs.");
  }

  async function createAndAnalyzeManualProspect(payload: { company_name: string; website_url: string; contact_name: string; contact_email: string; city: string; legitimate_interest_note: string }): Promise<void> {
    if (!token) {
      setManualProspectOpen(false);
      setToast("Logga in för att spara och analysera en webbplats.");
      return;
    }
    setManualProspectBusy(true);
    try {
      const prospect = await createManualProspect(apiBase, token, {
        ...payload,
        contact_name: payload.contact_name || null,
        contact_email: payload.contact_email || null,
        contact_verified: false,
        city: payload.city || null,
        legal_basis: "legitimate_interest_b2b",
        source_provider: "manual",
        source_url: payload.website_url,
        retention_days: 180
      });
      setManualProspectOpen(false);
      const lead = apiProspectToLead(prospect);
      setLeads((current) => [lead, ...current.filter((item) => item.apiId !== prospect.id)]);
      setSelectedId(lead.id);
      setDetailTab("analysis");
      if (!fetchEnabled) {
        await refreshWorkspace();
        setSelectedId(lead.id);
        setToast("Prospektet är sparat. Webbhämtning är avstängd — analysen startar när fetch är på.");
        return;
      }
      setToast("Prospektet är sparat. Den säkra webbplatsanalysen startar …");
      const analysis = await analyzeProspect(apiBase, token, prospect.id, true);
      await refreshWorkspace();
      setSelectedId(lead.id);
      setToast(`Analysen är klar med ${analysis.evidence.length} verifierbara källbevis.`);
    } catch (error) {
      setToast(operatorErrorMessage(error, "Webbplatsen kunde inte analyseras."));
    } finally {
      setManualProspectBusy(false);
    }
  }

  async function importCsvProspects(csvText: string): Promise<void> {
    if (!token) {
      setCsvBulkOpen(false);
      setToast("CSV-import kräver en aktiv SalesOS-session.");
      return;
    }
    setCsvBulkBusy(true);
    try {
      const result = await createProspectsFromCsv(apiBase, token, csvText);
      await refreshWorkspace();
      setCsvBulkOpen(false);
      setToast(
        `CSV: ${result.created.length} skapade, ${result.skipped.length} hoppade över (max ${result.max_rows}). Ingen e-post importerad.`
      );
    } catch (error) {
      setToast(operatorErrorMessage(error, "CSV-listan kunde inte importeras."));
    } finally {
      setCsvBulkBusy(false);
    }
  }

  async function verifySelectedContact(source: string): Promise<void> {
    if (!token || !selected.apiId) {
      setToast("Kontaktverifiering kräver en aktiv SalesOS-session.");
      return;
    }
    setContactVerifyBusy(true);
    try {
      const prospect = await updateProspect(apiBase, token, selected.apiId, {
        contact_verified: true,
        contact_verification_source: source
      });
      setLeads((current) => current.map((lead) => lead.id === selected.id ? { ...lead, contact: { ...lead.contact, verified: prospect.contact_verified }, updated: "Kontakt verifierad nyss" } : lead));
      setContactVerifyOpen(false);
      setToast("Kontakten är verifierad och verifieringskällan finns i revisionsloggen.");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Kontakten kunde inte verifieras.");
    } finally {
      setContactVerifyBusy(false);
    }
  }

  async function suppressSelectedContact(): Promise<void> {
    if (!token || !selected.apiId || !selected.contact.email) {
      setToast("En sparad kontakt med e-post krävs för att skapa en spärr.");
      return;
    }
    if (!window.confirm(`Spärra ${selected.contact.email} från all framtida prospekteringskontakt i denna tenant?`)) return;
    try {
      await suppressProspect(apiBase, token, selected.apiId, selected.contact.email);
      setLeads((current) => current.map((lead) => lead.id === selected.id ? { ...lead, doNotContact: true, updated: "Kontakt spärrad nyss" } : lead));
      setToast("Kontakten är spärrad. Alla framtida leveranser blockeras.");
      await refreshWorkspace();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Kontakten kunde inte spärras.");
    }
  }

  async function sendTestDelivery(): Promise<void> {
    if (!token) {
      setToast("Logga in för att skicka en testleverans.");
      return;
    }
    if (!selected?.proposalId) {
      setToast("Skapa och godkänn ett kundupplägg innan du testar utskicket.");
      return;
    }
    if (selected.status !== "approved") {
      setToast("Godkänn utkastet först. Testleverans använder det godkända e-postinnehållet.");
      return;
    }
    if (!operatorEmail) {
      setToast("Din operatörsprofil saknar e-post. Logga in igen och försök på nytt.");
      return;
    }
    setTestDeliveryBusy(true);
    try {
      await updateProposal(apiBase, token, selected.proposalId, { email_body: emailBody, email_subject: emailSubject });
      const emailCfg = apiSummary?.providers.email;
      const canSendSmtp = Boolean(
        emailCfg?.real_send_enabled && emailCfg?.provider === "smtp_generic" && emailCfg.configured
      );
      const delivery = await queueProposalDelivery(
        apiBase,
        token,
        selected.proposalId,
        canSendSmtp ? "smtp_generic" : "queue",
        undefined,
        fromAddress || emailCfg?.from_addresses?.[0],
        operatorEmail
      );
      setToast(
        delivery.external_sent
          ? `Testleverans skickad till ${delivery.recipient}.`
          : `Testleverans köad (${delivery.status}). Verklig e-post kräver smtp_generic på host.`
      );
    } catch (error) {
      setToast(error instanceof Error ? `Testleveransen stoppades: ${error.message}` : "Testleveransen kunde inte genomföras.");
    } finally {
      setTestDeliveryBusy(false);
    }
  }

  async function saveAutomation(enabled: boolean): Promise<void> {
    if (!token) {
      setToast("Logga in för att spara automationspolicy.");
      return;
    }
    try {
      const policy = await updateProspectingPolicy(apiBase, token, {
        mode: enabled ? "rules_assisted" : "manual_review",
        auto_analyze: enabled,
        auto_generate_proposal: enabled,
        auto_queue_after_approval: enabled,
        minimum_score: apiPolicy?.minimum_score ?? 80,
        daily_delivery_limit: apiPolicy?.daily_delivery_limit ?? 20
      });
      setApiPolicy(policy);
      setAutomationEnabled(policy.mode === "rules_assisted");
      setAutomationOpen(false);
      setToast(policy.scheduler_enabled ? "Regelstyrd automation är sparad och schemaläggaren är aktiv." : "Automationsreglerna är sparade. Bakgrundskörning förblir låst tills schemaläggaren aktiveras av operatör.");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Automationspolicyn kunde inte sparas.");
    }
  }

  function selectLead(id: number) {
    setSelectedId(id);
    setDetailTab("analysis");
  }

  if (!sessionToken) {
    return <NovaLoginGate apiBase={apiBase} onLogin={handleLogin} />;
  }

  return (
    <div className="wpa-app">
      <aside className={`wpa-sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="wpa-brand"><span className="wpa-brand__mark"><Icon name="sparkles" size={19} /></span><div><strong>Nova</strong><small>Webbprospektering</small></div><button aria-label="Stäng meny" onClick={() => setSidebarOpen(false)} type="button"><Icon name="close" /></button></div>
        <div className="wpa-agent-state"><span className={agentRunning ? "running" : ""}><i /></span><div><strong>Nova</strong><small>{agentRunning ? "Arbetar med ny sökning" : "Agent online · redo"}</small></div></div>
        <nav className="wpa-nav" aria-label="Huvudnavigation">
          <small>ARBETSFLÖDE</small>
          <a aria-current="page" href={homePath}><Icon name="layout" /> Översikt</a>
          <button onClick={() => { setFilter("all"); setSidebarOpen(false); }} type="button"><Icon name="building" /> Prospekt <b>{leads.length}</b></button>
          <button onClick={() => { setFilter("review"); setSidebarOpen(false); }} type="button"><Icon name="activity" /> Analyser <b>{reviewCount}</b></button>
          <button onClick={() => { setDetailTab("proposal"); setSidebarOpen(false); }} type="button"><Icon name="file" /> Kundförslag</button>
          <button onClick={() => { setFilter("approved"); setSidebarOpen(false); }} type="button"><Icon name="mail" /> Utskick</button>
          <small>HANTERA</small>
          <button onClick={() => setAutomationOpen(true)} type="button"><Icon name="wand" /> Automation <span className="wpa-beta">BETA</span></button>
          <button onClick={() => (liveSession ? setSettingsOpen(true) : setToast("Synkronisera arbetsytan först."))} type="button"><Icon name="settings" /> Inställningar</button>
        </nav>
        <div className="wpa-sidebar-policy">
          <div><Icon name={automationEnabled ? "wand" : "shield"} size={18} /><span><strong>{automationEnabled ? "Regelstyrt läge" : "Manuell kontroll"}</strong><small>{automationEnabled ? "Kvalificerade leveranser kan köas" : "Allt verifieras före leverans"}</small></span></div>
          <button onClick={() => setAutomationOpen(true)} type="button">Hantera <Icon name="chevron" size={14} /></button>
        </div>
        <div className="wpa-sidebar-user"><span>NO</span><div><strong>{operatorEmail || "Operatör"}</strong><small>{liveSession ? "Inloggad" : "Session"}</small></div><button aria-label="Logga ut" onClick={handleLogout} type="button"><Icon name="close" size={14} /></button></div>
      </aside>
      {sidebarOpen ? <button aria-label="Stäng meny" className="wpa-sidebar-scrim" onClick={() => setSidebarOpen(false)} type="button" /> : null}

      <main className="wpa-main">
        <header className="wpa-topbar">
          <div className="wpa-topbar__title"><button aria-label="Öppna meny" className="wpa-mobile-menu" onClick={() => setSidebarOpen(true)} type="button"><Icon name="menu" /></button><div><span>{liveSession ? "NOVA · LIVE" : "NOVA"}</span><h1>{liveSession ? "Webbprospektering" : "Nova"}</h1><p>{apiState === "live_empty" ? "Inga sparade webbplatser ännu. Analysera en publik URL för att skapa evidens, kundupplägg och mötesfilm." : liveSession ? <>Nova har <strong>{leads.length}</strong> sparade möjligheter i den här arbetsytan.</> : "Synkroniserar tenant-arbetsytan …"}</p></div></div>
          <div className="wpa-topbar__actions"><label className="wpa-global-search"><Icon name="search" size={17} /><input aria-label="Sök i alla företag" onChange={(event) => setSearch(event.target.value)} placeholder="Sök företag …" value={search} /><kbd>⌘ K</kbd></label><button aria-label="Notiser" className="wpa-notification" type="button"><Icon name="notification" /><i /></button><button className="wpa-button secondary analyze-url" onClick={() => setManualProspectOpen(true)} type="button"><Icon name="globe" size={16} /> Analysera URL</button><button className="wpa-button secondary" onClick={() => setCsvBulkOpen(true)} type="button"><Icon name="file" size={16} /> CSV-lista</button><button className="wpa-button primary new-search" disabled={!discoveryConfigured} onClick={() => setCampaignOpen(true)} title={discoveryConfigured ? undefined : "Places är avstängt. Använd Analysera URL eller CSV."} type="button"><Icon name="plus" size={17} /> Ny sökning</button></div>
        </header>

        <div className="wpa-content">
          <section className={`wpa-runtime-banner ${apiState}`}>
            <span><Icon name={apiState === "live" || apiState === "live_empty" ? "shield" : "activity"} size={16} /></span>
            <div>
              <strong>{apiState === "live" ? "Säker API-session · beständiga data" : apiState === "live_empty" ? "API ansluten · arbetsytan är tom" : apiState === "loading" ? "Synkroniserar arbetsytan …" : "API kunde inte nås"}</strong>
              <small>{apiState === "live" ? `${apiSummary?.providers.website_fetch?.enabled ? "Webbanalys aktiverad" : "Webbanalys låst av operatör"} · ${apiSummary?.providers.email?.real_send_enabled ? "verklig e-post aktiverad" : "extern e-post låst"}` : apiState === "live_empty" ? "Lägg till en URL för en källbelagd analys eller starta en kampanj." : apiState === "error" ? "Kontrollera API-anslutningen och försök igen." : "Hämtar policy, prospekt och leverantörsstatus."}</small>
            </div>
            {apiState === "error" ? <button onClick={() => void refreshWorkspace(true)} type="button"><Icon name="refresh" size={13} /> Försök igen</button> : <button onClick={() => void refreshWorkspace(true)} type="button"><Icon name="refresh" size={13} /> Synkronisera</button>}
          </section>
          <section className="wpa-stats" aria-label="Nyckeltal">
            <article><span className="blue"><Icon name="search" /></span><div><small>Analyserade webbplatser</small><strong>{apiSummary?.analyzed_sites ?? 0}</strong><p><b>Sparade</b> i tenant</p></div></article>
            <article><span className="violet"><Icon name="target" /></span><div><small>Kvalificerade möjligheter</small><strong>{apiSummary?.qualified_opportunities ?? leads.length}</strong><p><b>{leads.length}</b> visas nu</p></div></article>
            <article><span className="amber"><Icon name="clipboard" /></span><div><small>Väntar på granskning</small><strong>{apiSummary?.awaiting_review ?? reviewCount}</strong><p>Din åtgärd krävs</p></div></article>
            <article><span className="green"><Icon name="trend" /></span><div><small>Potentiellt ordervärde</small><strong>{Math.round((apiSummary?.potential_value_sek ?? totalPipeline) / 1000)} tkr</strong><p><b>Aktuell</b> pipeline</p></div></article>
          </section>

          <section className={`wpa-agent-run ${agentRunning ? "is-running" : ""}`}>
            <div className="wpa-agent-run__main"><span className="wpa-agent-orb"><Icon name="sparkles" size={21} /></span><div><span>{agentRunning ? "NOVA ARBETAR" : "LIVE-ARBETSYTA"}</span><h2>{agentRunning ? "Söker, källkontrollerar och kvalificerar …" : apiState === "live_empty" ? "Ingen aktiv kampanj" : campaignCriteria}</h2><p>{agentRunning ? "Publika företagsuppgifter → webbplatskontroll → kvalitetspoäng" : apiSummary?.providers.website_fetch?.enabled ? "Webbanalys är på. Lägg till en URL eller starta en sökning — inget skickas utan godkännande." : "Webbanalys är avstängd av operatör. Du kan spara URL:er, men hämtning av HTML är låst."}</p></div></div>
            <div className="wpa-flow" aria-label="Agentens arbetsflöde">{[
              ["search", "Hitta", `${leads.length} sparade`], ["target", "Kvalificera", `${reviewCount} att granska`], ["activity", "Analysera", "Evidens"], ["file", "Skapa förslag", "Versionerat"], ["shield", "Verifiera", "Manuellt"]
            ].map(([icon, label, meta], index) => <div className={index < 3 ? "done" : index === 3 ? "current" : ""} key={label}><span><Icon name={icon as IconName} size={15} /></span><p><strong>{label}</strong><small>{meta}</small></p>{index < 4 ? <i><Icon name="chevron" size={13} /></i> : null}</div>)}</div>
            <button className="wpa-run-action" disabled={!discoveryConfigured} onClick={() => setCampaignOpen(true)} title={discoveryConfigured ? undefined : "Places är avstängt. Använd Analysera URL."} type="button">Justera sökning <Icon name="settings" size={15} /></button>
            {agentRunning ? <div className="wpa-run-progress"><span /></div> : null}
          </section>

          <div className="wpa-workspace">
            <section className="wpa-prospects-card">
              <header className="wpa-section-header"><div><h2>Möjligheter</h2><span>{filteredLeads.length} av {leads.length} visade</span></div><div><div className="wpa-filter-tabs" role="group" aria-label="Filtrera möjligheter">{([['all', 'Alla'], ['review', 'Att granska'], ['qualified', 'Kvalificerade'], ['approved', 'Godkända']] as [FilterKey, string][]).map(([key, label]) => <button aria-pressed={filter === key} className={filter === key ? "active" : ""} key={key} onClick={() => setFilter(key)} type="button">{label}</button>)}</div><button aria-label="Fler filter" className="wpa-filter-button" type="button"><Icon name="filter" size={16} /> Filter</button></div></header>
              <div className="wpa-table-wrap">
                <table className="wpa-prospects-table">
                  <thead><tr><th>Företag</th><th>Förbättringspoäng</th><th>Status</th><th>Potential</th><th aria-label="Åtgärder" /></tr></thead>
                  <tbody>{filteredLeads.map((lead) => (
                    <tr className={selected?.id === lead.id ? "selected" : ""} key={lead.id} onClick={() => selectLead(lead.id)}>
                      <td><div className="wpa-company-cell"><span style={{ background: `${lead.accent}16`, color: lead.accent }}>{lead.initials}</span><div><strong>{lead.company}</strong><small><Icon name="globe" size={12} /> {lead.domain} <i /> {lead.city}</small></div></div></td>
                      <td><div className="wpa-score-cell"><strong>{lead.score}</strong><div><span style={{ width: `${lead.score}%` }} /></div><small>{lead.score >= 80 ? "Hög" : "God"} potential</small></div></td>
                      <td><span className={`wpa-status ${statusClass(lead.status)}`}>{lead.status === "analyzing" ? <i /> : null}{lead.status === "approved" ? <Icon name="check" size={12} /> : null}{STATUS_LABELS[lead.status]}</span><small className="wpa-updated">{lead.updated}</small></td>
                      <td><strong className="wpa-opportunity">{formatSek(lead.opportunity)}</strong><small className="wpa-updated">Estimerat projekt</small></td>
                      <td><button aria-label={`Öppna ${lead.company}`} className="wpa-row-action" onClick={(event) => { event.stopPropagation(); selectLead(lead.id); }} type="button"><Icon name="chevron" size={16} /></button></td>
                    </tr>
                  ))}</tbody>
                </table>
                {filteredLeads.length === 0 ? (
                  liveSession && leads.length === 0 ? (
                    <div className="wpa-empty wpa-empty--live">
                      <Icon name="globe" />
                      <strong>Inga sparade webbplatser ännu</strong>
                      <p>Analysera en publik URL. Nova hämtar evidens och skapar kundupplägg — inget skickas utan ditt godkännande.</p>
                      <button onClick={() => setManualProspectOpen(true)} type="button">Analysera URL</button>
                    </div>
                  ) : (
                    <div className="wpa-empty"><Icon name="search" /><strong>Inga företag matchar filtret</strong><p>Prova en annan sökning eller visa alla möjligheter.</p><button onClick={() => { setFilter("all"); setSearch(""); }} type="button">Rensa filter</button></div>
                  )
                ) : null}
              </div>
              <footer className="wpa-table-footer"><span>Senast uppdaterad nyss</span><button onClick={() => void refreshWorkspace(true)} type="button"><Icon name="refresh" size={14} /> Uppdatera</button></footer>
            </section>

            {selected ? (
            <aside className="wpa-detail-card" aria-label={`Detalj för ${selected.company}`}>
              <header className="wpa-detail-head">
                <div className="wpa-detail-company"><span style={{ background: `${selected.accent}16`, color: selected.accent }}>{selected.initials}</span><div><h2>{selected.company}</h2><a href={`https://${selected.domain}`} rel="noreferrer" target="_blank">{selected.domain} <Icon name="external" size={12} /></a></div></div>
                <button aria-label="Fler val" className="wpa-icon-button" type="button"><Icon name="more" /></button>
              </header>
              <div className="wpa-company-meta"><span><Icon name="building" size={14} /> {selected.industry}</span><span>{selected.employees} anställda</span><span>{selected.turnover}</span></div>
              <div className="wpa-detail-tabs" role="tablist"><button aria-selected={detailTab === "analysis"} className={detailTab === "analysis" ? "active" : ""} onClick={() => setDetailTab("analysis")} role="tab" type="button">Analys</button><button aria-selected={detailTab === "proposal"} className={detailTab === "proposal" ? "active" : ""} onClick={() => setDetailTab("proposal")} role="tab" type="button">Nytt upplägg</button><button aria-selected={detailTab === "email"} className={detailTab === "email" ? "active" : ""} onClick={() => setDetailTab("email")} role="tab" type="button">E-post</button></div>

              <div className="wpa-detail-body">
                {detailTab === "analysis" ? <>
                  <section className="wpa-score-summary"><div className="wpa-score-ring" style={{ "--score": `${selected.score * 3.6}deg` } as CSSProperties}><span><strong>{selected.score}</strong><small>/100</small></span></div><div><span>FÖRBÄTTRINGSPOTENTIAL</span><h3>{selected.score >= 80 ? "Stor affärsmöjlighet" : "Tydlig förbättringsmöjlighet"}</h3><p>Högre poäng betyder fler verifierade möjligheter att skapa mätbar effekt.</p></div></section>
                  <section><div className="wpa-subhead"><h3>Teknisk översikt</h3><span>Senast testad idag</span></div><div className="wpa-metrics-grid"><MetricBar label="Prestanda" value={selected.metrics.performance} /><MetricBar label="SEO" value={selected.metrics.seo} /><MetricBar label="Tillgänglighet" value={selected.metrics.accessibility} /><MetricBar label="Mobil" value={selected.metrics.mobile} /></div>{selected.screenshot ? <figure className="wpa-page-screenshot"><img alt={`Mobil skärmbild av ${selected.domain}`} src={selected.screenshot} /><figcaption>Mobil rendering från PageSpeed Insights</figcaption></figure> : null}</section>
                  <section><div className="wpa-subhead"><h3>Viktigaste observationerna</h3><span>{selected.evidence?.length ? `${selected.evidence.length} källbevis` : "Observationer"}</span></div><div className="wpa-findings">{selected.findings.map((finding) => <article key={finding.title}><span className={finding.severity}><Icon name={finding.icon} size={16} /></span><div><strong>{finding.title}</strong><p>{finding.detail}</p></div><i className={finding.severity} /></article>)}</div>{selected.evidence?.length ? <details className="wpa-evidence"><summary><Icon name="shield" size={14} /> Visa verifierbart källunderlag</summary><div>{selected.evidence.slice(0, 8).map((item) => <article key={item.id}><span>{item.label}</span><code>{typeof item.value === "string" ? item.value || "Saknas" : JSON.stringify(item.value)}</code><a href={item.url} rel="noreferrer" target="_blank">Källa <Icon name="external" size={10} /></a></article>)}</div></details> : null}</section>
                  <section className="wpa-contact"><div className="wpa-subhead"><h3>Beslutsfattare</h3>{selected.contact.verified ? <span className="verified"><Icon name="check" size={12} /> Verifierad</span> : <span>Behöver verifieras</span>}</div><div><span><Icon name="user" /></span><p><strong>{selected.contact.name}</strong><small>{selected.contact.role}</small>{selected.contact.email ? <a href={`mailto:${selected.contact.email}`}>{selected.contact.email}</a> : <small>E-post saknas</small>}</p>{selected.apiId && !selected.contact.verified && selected.contact.email ? <button className="wpa-verify-contact" onClick={() => setContactVerifyOpen(true)} type="button"><Icon name="check" size={11} /> Verifiera</button> : null}</div></section>
                  {selected.apiId ? <section className="wpa-compliance"><div><Icon name="shield" size={15} /><span><strong>Kontaktpolicy</strong><small>{selected.doNotContact ? "Spärrad — inget utskick tillåts" : `Rättslig grund: ${selected.legalBasis || "måste verifieras"}`}</small></span></div><div className="wpa-compliance-actions">{selected.sourceUrl ? <a href={selected.sourceUrl} rel="noreferrer" target="_blank">Ursprungskälla <Icon name="external" size={11} /></a> : null}{selected.contact.email && !selected.doNotContact ? <button onClick={() => void suppressSelectedContact()} type="button">Spärra kontakt</button> : null}</div></section> : null}
                </> : null}

                {detailTab === "proposal" ? <>
                  <div className="wpa-proposal-heading"><span><Icon name="sparkles" size={16} /> AGENTGENERERAT UTKAST</span><h3>{selected.proposalHeadline || `Nytt webbupplägg för ${selected.company}`}</h3><p>Utformat från verifierade behov, bransch och befintligt innehåll.</p></div>
                  <WebsiteMockup lead={selected} />
                  <section className="wpa-meeting-film">
                    <div className="wpa-meeting-film__signal"><span><Icon name="sparkles" size={18} /></span><i /><i /></div>
                    <div><small>NOVA · KUNDANPASSAD MÖTESFILM</small><h3>Gör analysen omöjlig att bläddra förbi.</h3><p>Nio självkörande kapitel med evidens, målbild, affärseffekt och nästa steg. Textning, valfri svensk webbläsarröst, helskärm och möteskontroller ingår.</p></div>
                    <div className="wpa-meeting-film__actions"><button className="wpa-button primary" onClick={() => void openMeetingPresentation()} type="button"><Icon name="eye" size={15} /> Starta mötesfilmen</button><button className="wpa-button secondary" onClick={() => setInternalBusinessCaseOpen(true)} type="button"><Icon name="shield" size={14} /> Intern kalkyl</button></div>
                  </section>
                  <section><div className="wpa-subhead"><h3>Föreslagen struktur</h3><span>{selected.proposalSitemap?.length || 6} sidor</span></div><div className="wpa-sitemap">{(selected.proposalSitemap || ["Start", "Tjänster", "Projekt", "Om oss", "Kontakt", "Offert"]).map((page) => <span key={page}>{page}</span>)}</div></section>
                  <section><div className="wpa-subhead"><h3>Effekt & effektivisering</h3></div><div className="wpa-benefits">{(selected.proposalBenefits || [{ title: "Fler relevanta leads", detail: "Tydliga erbjudanden och CTA per kundbehov." }, { title: "Mindre manuellt arbete", detail: "Kvalificerande formulär och automatisk mötesbokning." }, { title: "Starkare lokal SEO", detail: "Ortssidor och teknisk struktur som går att mäta." }]).map((benefit, index) => <article key={`${benefit.title}-${index}`}><Icon name={(["trend", "bolt", "search"] as IconName[])[index % 3]} /><div><strong>{benefit.title}</strong><p>{benefit.detail}</p></div></article>)}</div></section>
                  {selected.proposalPackages?.length ? <section><div className="wpa-subhead"><h3>Genomförandenivåer</h3><span>Exkl. moms</span></div><div className="wpa-proposal-packages">{selected.proposalPackages.map((item) => <article className={item.recommended ? "recommended" : ""} key={item.name}><span>{item.recommended ? "REKOMMENDERAD" : "PAKET"}</span><strong>{item.name}</strong><b>{formatSek(item.price_sek)}</b><small>{item.features.slice(0, 3).join(" · ")}</small></article>)}</div></section> : null}
                  {selected.proposalTimeline?.length ? <section><div className="wpa-subhead"><h3>Leveransplan</h3></div><div className="wpa-proposal-timeline">{selected.proposalTimeline.map((item) => <div key={`${item.week}-${item.title}`}><strong>{item.week}</strong><span>{item.title}</span></div>)}</div></section> : null}
                  <section className="wpa-scope"><div><span>Rekommenderad investering</span><strong>{formatSek(selected.proposalPackages?.find((item) => item.recommended)?.price_sek || selected.opportunity)}</strong><small>Engångsprojekt · exkl. moms</small></div><div><span>Estimerad leverans</span><strong>4–6 veckor</strong><small>Från godkänt innehåll</small></div></section>
                </> : null}

                {detailTab === "email" ? <>
                  <div className="wpa-email-state"><span className={selected.status === "approved" ? "approved" : "draft"}><Icon name={selected.status === "approved" ? "check" : "file"} size={14} /> {selected.status === "approved" ? "Godkänd för leverans" : "Utkast · ej skickat"}</span><small>Senast sparat nyss</small></div>
                  <section className="wpa-email-compose"><label>Till<div><input readOnly value={`${selected.contact.name} <${selected.contact.email}>`} />{selected.contact.verified ? <span><Icon name="check" size={11} /> Verifierad</span> : null}</div></label>{(apiSummary?.providers.email?.from_addresses?.length || 0) > 0 ? <label>Avsändare<select onChange={(event) => setFromAddress(event.target.value)} value={fromAddress || apiSummary?.providers.email?.from_addresses?.[0] || ""}>{(apiSummary?.providers.email?.from_addresses || []).map((address) => <option key={address} value={address}>{address}</option>)}</select></label> : null}<label>Ämne<input onChange={(event) => setEmailSubject(event.target.value)} value={emailSubject} /></label><label>Meddelande<textarea onChange={(event) => setEmailBody(event.target.value)} rows={16} value={emailBody} /></label></section>
                  <section className="wpa-attachment"><span><Icon name="file" /></span><div><strong>Analys, kundupplägg & mötesfilm</strong><small>Personlig webblänk · kundanpassad · självkörande presentation</small></div><button onClick={() => setDetailTab("proposal")} type="button"><Icon name="eye" size={15} /> Förhandsvisa</button></section>
                  <div className="wpa-email-note"><Icon name="shield" size={16} /><span>{apiSummary?.providers.email?.real_send_enabled && apiSummary.providers.email.provider === "smtp_generic" ? "Efter godkännande skickas mailet från den valda avsändaren. Kill-switch och spärrlista gäller." : "Utskicket köas tills smtp_generic och kill-switch är aktiverade på host."}</span></div>
                </> : null}
              </div>

              <footer className="wpa-detail-footer">
                {detailTab === "analysis" ? <><button className="wpa-button secondary" disabled={!fetchEnabled} onClick={analyzeSelected} title={fetchEnabled ? undefined : "Webbhämtning avstängd"} type="button"><Icon name="refresh" size={15} /> Analysera igen</button><button className="wpa-button primary" disabled={selected.status === "analyzing"} onClick={createProposal} type="button"><Icon name="sparkles" size={15} /> {selected.status === "analyzing" ? "Analyserar …" : "Skapa kundupplägg"}</button></> : null}
                {detailTab === "proposal" ? <><button className="wpa-button secondary" onClick={selected.status === "approved" ? () => void createProposal() : () => setProposalEditorOpen(true)} type="button"><Icon name={selected.status === "approved" ? "plus" : "file"} size={15} /> {selected.status === "approved" ? "Skapa ny version" : "Redigera upplägg"}</button><button className="wpa-button primary" onClick={() => setDetailTab("email")} type="button">Skapa e-post <Icon name="arrow" size={15} /></button></> : null}
                {detailTab === "email" ? <><button className="wpa-button secondary" disabled={testDeliveryBusy} onClick={() => void sendTestDelivery()} type="button">{testDeliveryBusy ? "Skickar test …" : "Skicka test till mig"}</button><button className={`wpa-button primary ${selected.status === "approved" ? "approved" : ""}`} disabled={selected.doNotContact || !selected.contact.email} onClick={() => setReviewOpen(true)} type="button"><Icon name={selected.status === "approved" ? "check" : "shield"} size={15} /> {selected.status === "approved" ? "Visa verifiering" : "Granska & godkänn"}</button></> : null}
              </footer>
            </aside>
            ) : (
            <aside className="wpa-detail-card wpa-detail-card--empty" aria-label="Tom Nova-arbetsyta">
              <div className="wpa-empty wpa-empty--live">
                <Icon name="globe" />
                <strong>Börja med en publik webbplats</strong>
                <p>Sparade, tenant-isolerade prospekt visas här efter analys eller import.</p>
                <button className="wpa-button primary" onClick={() => setManualProspectOpen(true)} type="button"><Icon name="plus" size={15} /> Analysera URL</button>
              </div>
            </aside>
            )}
          </div>
        </div>
      </main>

      {campaignOpen ? <CampaignModal onClose={() => setCampaignOpen(false)} onStart={(criteria) => void startCampaign(criteria)} /> : null}
      {manualProspectOpen ? <ManualProspectModal busy={manualProspectBusy} fetchEnabled={fetchEnabled} onClose={() => setManualProspectOpen(false)} onCreate={(payload) => void createAndAnalyzeManualProspect(payload)} /> : null}
      {csvBulkOpen ? <CsvBulkModal busy={csvBulkBusy} onClose={() => setCsvBulkOpen(false)} onImport={(csvText) => void importCsvProspects(csvText)} /> : null}
      {contactVerifyOpen && selected ? <ContactVerificationModal busy={contactVerifyBusy} lead={selected} onClose={() => setContactVerifyOpen(false)} onVerify={(source) => void verifySelectedContact(source)} /> : null}
      {proposalEditorOpen && selected ? <ProposalEditorModal busy={proposalEditorBusy} lead={selected} onClose={() => setProposalEditorOpen(false)} onSave={(payload) => void saveProposalContent(payload)} /> : null}
      {internalBusinessCaseOpen && selected ? <InternalBusinessCaseModal lead={selected} onClose={() => setInternalBusinessCaseOpen(false)} /> : null}
      {reviewOpen && selected ? <ReviewModal lead={selected} onApprove={approveDelivery} onClose={() => setReviewOpen(false)} /> : null}
      {automationOpen ? <AutomationModal onClose={() => setAutomationOpen(false)} onSave={(enabled) => void saveAutomation(enabled)} /> : null}
      {settingsOpen ? <ProviderSettingsModal onClose={() => setSettingsOpen(false)} onOpenAutomation={() => { setSettingsOpen(false); setAutomationOpen(true); }} policy={apiPolicy} summary={apiSummary} /> : null}
      {toast ? <div aria-live="polite" className="wpa-toast"><span><Icon name="check" size={15} /></span>{toast}<button aria-label="Stäng" onClick={() => setToast(null)} type="button"><Icon name="close" size={14} /></button></div> : null}
    </div>
  );
}
