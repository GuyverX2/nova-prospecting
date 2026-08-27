import { useEffect, useMemo, useRef, useState } from "react";
import { MUSIC_TAIL, NovaAudioEngine } from "./novaAudio";
import "./presentation.css";
import "./nova.css";

type SceneId = "opening" | "problem" | "discovery" | "analysis" | "proposal" | "control" | "live" | "closing";

type Scene = {
  id: SceneId;
  eyebrow: string;
  title: string;
  caption: string;
};

const SCENES: Scene[] = [
  {
    id: "opening",
    eyebrow: "Nova · demofilm",
    title: "Hittar möjligheten. Lämnar beslutet till er.",
    caption:
      "Nova är SalesOS webbprospekteringsagent. Den söker, källkontrollerar och prioriterar — inte som en autonom säljare."
  },
  {
    id: "problem",
    eyebrow: "Där tiden går",
    title: "Rätt bolag tar för lång tid att hitta.",
    caption: "Signaler finns överallt. Det som saknas är evidens, och ett tydligt nästa steg när ni ska agera."
  },
  {
    id: "discovery",
    eyebrow: "Sökning",
    title: "Publika uppgifter. Kontrollerad webb.",
    caption: "Nova utgår från publika företagsuppgifter, granskar nuvarande webb och lyfter det som går att förbättra."
  },
  {
    id: "analysis",
    eyebrow: "Underlag",
    title: "Poäng med synlig evidens.",
    caption: "Varje möjlighet får poäng, teknisk översikt och källkontrollerat underlag. Ni ser varför den syns."
  },
  {
    id: "proposal",
    eyebrow: "Kundupplägg",
    title: "Ett utkast ni äger.",
    caption: "Nova tar fram ett redigerbart kundupplägg. Rubriker, paket och mejl ändras av er innan något lämnar bordet."
  },
  {
    id: "control",
    eyebrow: "Mandat",
    title: "Ingen e-post går ut av sig själv.",
    caption: "Mänsklig verifiering, spärrlista och spårbarhet sitter före leverans. AI hjälper. Människan beslutar."
  },
  {
    id: "live",
    eyebrow: "Efter filmen",
    title: "Se agenten på riktigt.",
    caption: "Det ni öppnar sedan är den live Nova-arbetsytan — inte en tillrättalagd film."
  },
  {
    id: "closing",
    eyebrow: "Nova",
    title: "Nästa möjlighet, med evidens.",
    caption: "Öppna Nova och ta fram nästa möjlighet med underlag, mandat och nästa steg på samma skärm."
  }
];

const NARRATION_FILES: string[] = SCENES.map(
  (scene, index) => `/presentation/nova-${String(index + 1).padStart(2, "0")}-${scene.id}.mp3`
);

const NOMINAL_DURATION = 150 + MUSIC_TAIL;

function formatTime(seconds: number, total: number) {
  const safe = Math.max(0, Math.min(total, seconds));
  return `${Math.floor(safe / 60)}:${Math.floor(safe % 60).toString().padStart(2, "0")}`;
}

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`presentationBrand ${compact ? "presentationBrand--compact" : ""}`}>
      <span className="presentationBrand__mark" aria-hidden="true"><i /><i /></span>
      <span>SalesOS · Nova</span>
    </span>
  );
}

function Icon({ name }: { name: "play" | "pause" | "sound" | "muted" | "fullscreen" | "restart" }) {
  const paths = {
    play: <path d="M8 5v14l11-7z" />,
    pause: <path d="M7 5h4v14H7zm6 0h4v14h-4z" />,
    sound: <path d="M4 10v4h4l5 4V6L8 10H4zm12.2-2.2a6 6 0 0 1 0 8.4M18.8 5.2a9.5 9.5 0 0 1 0 13.6" />,
    muted: <path d="M4 10v4h4l5 4V6L8 10H4zm12-1 6 6m0-6-6 6" />,
    fullscreen: <path d="M8 3H3v5m13-5h5v5M8 21H3v-5m13 5h5v-5" />,
    restart: <path d="M4 4v6h6M5.5 16.5A8 8 0 1 0 6 7" />
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24">{paths[name]}</svg>;
}

function SceneVisual({ id }: { id: SceneId }) {
  if (id === "opening" || id === "closing") {
    return (
      <div className={`novaOrb ${id === "closing" ? "novaOrb--finale" : ""}`} aria-hidden="true">
        <div className="novaOrb__ring novaOrb__ring--one" />
        <div className="novaOrb__ring novaOrb__ring--two" />
        <div className="novaOrb__ring novaOrb__ring--three" />
        <i className="novaOrb__spark novaOrb__spark--one" />
        <i className="novaOrb__spark novaOrb__spark--two" />
        <div className="novaOrb__core">
          <strong>Nova</strong>
          <small>{id === "closing" ? "öppna demon" : "agent online"}</small>
        </div>
      </div>
    );
  }
  if (id === "problem") {
    return (
      <div className="novaScatter" aria-hidden="true">
        <svg className="novaScatter__lines" viewBox="0 0 520 320" preserveAspectRatio="none">
          <path d="M80 70 C180 40 240 140 260 160" />
          <path d="M430 80 C340 90 320 130 260 160" />
          <path d="M90 250 C170 210 210 230 260 160" />
          <path d="M430 250 C340 240 320 200 260 160" />
        </svg>
        {[
          ["Bolag", "oklart"],
          ["Webb", "saknas"],
          ["Poäng", "—"],
          ["Nästa steg", "?"]
        ].map(([label, value], index) => (
          <div className={`novaScatter__card novaScatter__card--${index + 1}`} key={label}>
            <span>{label}</span>
            <b>{value}</b>
          </div>
        ))}
      </div>
    );
  }
  if (id === "discovery") {
    return (
      <div className="novaRadar" aria-hidden="true">
        <div className="novaRadar__dish">
          <i />
          <b />
          <b />
          <em />
        </div>
        <span>Publika källor</span>
        <span>Webbkontroll</span>
        <span>Prioritering</span>
      </div>
    );
  }
  if (id === "analysis") {
    return (
      <div className="novaBoard" aria-hidden="true">
        {[
          ["Nordiska Fönster", "92", "3 källor"],
          ["Haga Markis", "81", "2 källor"],
          ["Kustkök Väst", "74", "3 källor"]
        ].map(([name, score, evidence], index) => (
          <div className="novaBoard__row" key={name} style={{ "--row-index": index } as React.CSSProperties}>
            <div>
              <span>{name}</span>
              <small>{evidence}</small>
            </div>
            <b>{score}</b>
            <i style={{ width: `${score}%` }} />
          </div>
        ))}
      </div>
    );
  }
  if (id === "proposal") {
    return (
      <div className="novaProposal" aria-hidden="true">
        <header>
          <small>Redigerbart utkast</small>
          <em>v1 · ej skickat</em>
        </header>
        <strong>Ny webb som säljer mer av det ni redan gör</strong>
        <p>Struktur, paket och nästa steg — klart att justera innan något lämnar bordet.</p>
        <ul>
          <li>Struktur</li>
          <li>Paket</li>
          <li>Mejl</li>
        </ul>
      </div>
    );
  }
  if (id === "control") {
    return (
      <div className="novaGate" aria-hidden="true">
        {["Kontakt verifierad", "Spärrlista tom", "Mänskligt godkännande"].map((item, index) => (
          <div className="novaGate__item" key={item} style={{ "--gate-index": index } as React.CSSProperties}>
            <i />
            {item}
            <b>✓</b>
          </div>
        ))}
        <p>ingen extern e-post skickades</p>
      </div>
    );
  }
  return (
    <div className="novaLive" aria-hidden="true">
      <div className="novaLive__browser">
        <header>
          <i /><i /><i />
          <span>salesos.se/nova</span>
        </header>
        <section>
          <small>Kontrollerad pilot</small>
          <strong>Samma flöde.<br />Samma mandat.</strong>
          <div>
            <span>Sökning</span>
            <span>Evidens</span>
            <span>Utkast</span>
            <span>Godkännande</span>
          </div>
        </section>
      </div>
      <div className="liveBadge"><i />LIVE DEMO NÄSTA</div>
    </div>
  );
}

export function NovaPresentation() {
  const engineRef = useRef<NovaAudioEngine | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [started, setStarted] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [finished, setFinished] = useState(false);
  const [duration, setDuration] = useState(NOMINAL_DURATION);
  const [sceneStarts, setSceneStarts] = useState<number[]>([]);

  useEffect(() => {
    let cancelled = false;
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) {
      setStatus("error");
      return;
    }
    const engine = new NovaAudioEngine(new Ctor());
    engineRef.current = engine;
    engine
      .load(NARRATION_FILES)
      .then(() => {
        if (cancelled) return;
        setDuration(engine.duration);
        setSceneStarts(engine.sceneStarts);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "Nova-film — SalesOS webbprospektering";
    return () => {
      document.title = previousTitle;
    };
  }, []);

  const activeSceneIndex = useMemo(() => {
    let index = 0;
    sceneStarts.forEach((start, sceneIndex) => {
      if (currentTime >= start) index = sceneIndex;
    });
    return index;
  }, [currentTime, sceneStarts]);
  const scene = SCENES[activeSceneIndex];

  useEffect(() => {
    if (!started) return;
    const timer = window.setInterval(() => {
      const engine = engineRef.current;
      if (!engine) return;
      const time = engine.currentTime();
      setCurrentTime(time);
      if (time >= duration - 0.05) {
        engine.pause();
        setPlaying(false);
        setFinished(true);
      }
    }, 100);
    return () => window.clearInterval(timer);
  }, [started, duration]);

  function togglePlayback() {
    const engine = engineRef.current;
    if (!engine) return;
    if (playing) {
      engine.pause();
      setPlaying(false);
      return;
    }
    if (finished || currentTime >= duration - 0.2) {
      engine.play(0);
      setCurrentTime(0);
      setFinished(false);
    } else {
      engine.resume();
    }
    setPlaying(true);
  }

  function seek(seconds: number) {
    const engine = engineRef.current;
    if (!engine) return;
    const target = Math.max(0, Math.min(duration - 0.05, seconds));
    setCurrentTime(target);
    setFinished(false);
    if (playing) {
      engine.seek(target);
      engine.resume();
    } else {
      engine.seek(target);
    }
  }

  function start(fullscreen: boolean) {
    const engine = engineRef.current;
    if (!engine) return;
    setStarted(true);
    setCurrentTime(0);
    if (fullscreen) document.documentElement.requestFullscreen().catch(() => undefined);
    engine.play(0);
    setPlaying(true);
  }

  function toggleMute() {
    const next = !muted;
    setMuted(next);
    engineRef.current?.setMuted(next);
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      /* browser can deny fullscreen without affecting playback */
    }
  }

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (!started) return;
      if (event.code === "Space") {
        event.preventDefault();
        togglePlayback();
      } else if (event.key === "ArrowRight") seek(currentTime + 5);
      else if (event.key === "ArrowLeft") seek(currentTime - 5);
      else if (event.key.toLowerCase() === "m") toggleMute();
      else if (event.key.toLowerCase() === "f") void toggleFullscreen();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  });

  return (
    <main className={`presentation presentation--nova presentation--${scene.id} ${started ? "is-started" : "is-intro"}`}>
      <div className="presentationBackdrop" aria-hidden="true">
        <div className="presentationBackdrop__glow presentationBackdrop__glow--one" />
        <div className="presentationBackdrop__glow presentationBackdrop__glow--two" />
        <div className="presentationBackdrop__key" />
        <div className="presentationBackdrop__grid" />
        <div className="presentationBackdrop__noise" />
      </div>

      {!started ? (
        <section className="presentationStart" aria-label="Starta Nova-filmen">
          <BrandMark />
          <div className="presentationStart__copy">
            <span className="presentationKicker">Nova-film · ca 2 min</span>
            <h1>Webbprospektering<br />med evidens och mandat.</h1>
            <p>En separat film om Nova. Arenas klickbara demo ligger kvar på /nova — den här sidan är bara filmen.</p>
          </div>
          <div className="presentationStart__actions">
            <button
              className="presentationButton presentationButton--primary"
              disabled={status !== "ready"}
              onClick={() => start(true)}
              type="button"
            >
              <Icon name="play" /> Starta i helskärm
            </button>
            <button
              className="presentationButton presentationButton--secondary"
              disabled={status !== "ready"}
              onClick={() => start(false)}
              type="button"
            >
              Starta i fönster
            </button>
          </div>
          <p className="presentationStart__status">
            <i className={status === "ready" ? "is-ready" : ""} />
            {status === "ready"
              ? "Nova-filmen, berättarröst och musik är redo"
              : status === "error"
                ? "Berättarrösten kunde inte laddas — kontrollera nätverket"
                : "Laddar berättarröst…"}
          </p>
          <a className="presentationStart__skip" href="/nova">Gå direkt till Nova</a>
        </section>
      ) : (
        <>
          <header className="presentationTopbar">
            <BrandMark compact />
            <div className="presentationTopbar__right">
              <div className={`presentationMeter ${playing && !muted ? "is-live" : ""}`} aria-hidden="true"><i /><i /><i /><i /><i /></div>
              <div className="presentationTopbar__chapter">
                <span>{String(activeSceneIndex + 1).padStart(2, "0")}</span>
                <i />
                <small>{String(SCENES.length).padStart(2, "0")}</small>
              </div>
            </div>
          </header>
          <section className="presentationStage" key={scene.id} aria-labelledby="nova-title">
            <div className="presentationStage__copy">
              <span className="presentationKicker">{scene.eyebrow}</span>
              <h1 id="nova-title">{scene.title}</h1>
              {scene.id === "live" ? <div className="presentationTruthTag"><i />Kontrollerad pilot i dag</div> : null}
              {scene.id === "closing" ? <a className="presentationCta" href="/nova">Öppna Nova <span>→</span></a> : null}
            </div>
            <div className="presentationStage__visual"><SceneVisual id={scene.id} /></div>
          </section>
          <div className="presentationCaption" aria-live="polite"><span>{scene.caption}</span></div>
          <footer className="presentationControls">
            <button aria-label={playing ? "Pausa" : "Spela"} onClick={togglePlayback} type="button"><Icon name={playing ? "pause" : "play"} /></button>
            <button aria-label="Starta om" onClick={() => { seek(0); if (!playing) togglePlayback(); }} type="button"><Icon name="restart" /></button>
            <span className="presentationControls__time">{formatTime(currentTime, duration)}</span>
            <input
              aria-label="Nova-filmens position"
              max={duration}
              min="0"
              onChange={(event) => seek(Number(event.target.value))}
              step="0.1"
              style={{ "--presentation-progress": `${(currentTime / duration) * 100}%` } as React.CSSProperties}
              type="range"
              value={Math.min(currentTime, duration)}
            />
            <span className="presentationControls__time">{formatTime(duration, duration)}</span>
            <button aria-label={muted ? "Slå på ljud" : "Stäng av ljud"} onClick={toggleMute} type="button">
              <Icon name={muted ? "muted" : "sound"} />
            </button>
            <button aria-label="Helskärm" onClick={() => void toggleFullscreen()} type="button">
              <Icon name="fullscreen" />
            </button>
          </footer>
        </>
      )}
    </main>
  );
}
