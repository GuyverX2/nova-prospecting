"""Evidence-backed, self-running Nova meeting presentation renderer.

The renderer is deliberately deterministic and local: it derives a cinematic
meeting story from an already generated proposal and its verified analysis. It
does not call a model, fetch remote assets, or invent customer outcomes. The
result is a standalone HTML "meeting film" with captions, optional browser
narration, keyboard controls, and a reduced-motion fallback.
"""
from __future__ import annotations

import json
from html import escape
from typing import Any

from app.prospecting.models import WebsiteAnalysis, WebsiteProposal, WebsiteProspect


def _load(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _text(value: Any, fallback: str = "") -> str:
    cleaned = " ".join(str(value or "").split())
    return cleaned or fallback


def _finding_actions(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    mapped: list[dict[str, str]] = []
    action_by_key = {
        "pagespeed_performance": ("Tempo", "Prioritera mobil laddning, resurser och Core Web Vitals."),
        "slow_server": ("Tempo", "Korta serverns svarstid och mät den verkliga användarupplevelsen."),
        "server_latency": ("Tempo", "Trimma svarstid och verifiera förbättringen i Lighthouse."),
        "missing_title": ("Synlighet", "Ge varje prioriterad sida en unik, sökbar sidtitel."),
        "title_length": ("Synlighet", "Skärp sidtiteln runt erbjudande och viktigaste sökintention."),
        "missing_description": ("Budskap", "Skriv ett tydligt värdelöfte för sökresultat och delningar."),
        "h1_structure": ("Struktur", "För-rendera en tydlig huvudrubrik som bär sidans primära löfte."),
        "structured_data": ("Förtroende", "Lägg till Organization-, Service- och kontaktdata i JSON-LD."),
        "missing_lang": ("Tillgänglighet", "Ange rätt språk för sökmotorer och hjälpmedel."),
        "image_alt": ("Tillgänglighet", "Beskriv meningsbärande bilder och lämna dekorativa bilder tomma."),
        "form_labels": ("Konvertering", "Gör formulärfält tydliga för både människor och hjälpmedel."),
        "missing_viewport": ("Mobil", "Inför en responsiv mobilgrund och testa prioriterade kundresor."),
        "weak_cta": ("Konvertering", "Ge varje erbjudande en tydlig, relevant nästa handling."),
        "long_form": ("Konvertering", "Korta första formulärsteget och kvalificera först efter kontakt."),
        "local_visibility": ("Relevans", "Separera språk, marknader eller orter med egna tydliga landningssidor."),
        "no_https": ("Trygghet", "Säkra hela kundresan med konsekvent HTTPS."),
    }
    seen: set[str] = set()
    for item in findings:
        if item.get("severity") == "positive":
            continue
        key = str(item.get("key") or "")
        label, detail = action_by_key.get(
            key,
            (_text(item.get("title"), "Förbättring"), _text(item.get("detail"), "Verifiera och prioritera observationen.")),
        )
        if label in seen:
            continue
        seen.add(label)
        mapped.append({"label": label, "detail": detail})
        if len(mapped) == 4:
            break
    fallbacks = [
        {"label": "Budskap", "detail": "Matcha ett tydligt kundproblem med ett tydligt erbjudande."},
        {"label": "Bevis", "detail": "Gör kundcase och mätbara resultat synliga nära beslutet."},
        {"label": "Konvertering", "detail": "Skapa en kort väg från intresse till bokat nästa steg."},
        {"label": "Mätning", "detail": "Följ varje prioriterad kundresa från källa till kvalificerat lead."},
    ]
    for item in fallbacks:
        if len(mapped) == 4:
            break
        if item["label"] not in seen:
            mapped.append(item)
            seen.add(item["label"])
    return mapped


def build_meeting_story(
    row: WebsiteProposal,
    prospect: WebsiteProspect,
    analysis: WebsiteAnalysis,
) -> dict[str, Any]:
    """Build a truthful, presentation-ready story from persisted Nova evidence."""
    company = _text(prospect.company_name, "företaget")
    domain = _text(prospect.normalized_domain, "kundens webbplats")
    findings = _load(analysis.findings_json, [])
    non_positive = [item for item in findings if item.get("severity") != "positive"]
    positive = [item for item in findings if item.get("severity") == "positive"]
    top_findings = non_positive[:3]
    actions = _finding_actions(findings)
    benefits = _load(row.benefits_json, [])[:3]
    timeline = _load(row.timeline_json, [])[:4]
    packages = _load(row.packages_json, [])
    recommended = next((item for item in packages if item.get("recommended")), packages[0] if packages else None)
    technical = _load(analysis.technical_json, {})
    limitations = technical.get("limitations") if isinstance(technical, dict) else []
    static_scope = any("JavaScript was not executed" in str(item) for item in (limitations or []))

    strength_cards = [
        {
            "label": "Tydlig utgångspunkt",
            "value": _text(analysis.final_url or analysis.analyzed_url, domain),
        },
        {
            "label": "Säkrat underlag",
            "value": f"{len(_load(analysis.evidence_json, []))} verifierbara källbevis",
        },
    ]
    if positive:
        strength_cards.insert(0, {"label": "Styrka att skala", "value": _text(positive[0].get("title"), "Stabil digital grund")})
    else:
        strength_cards.insert(0, {"label": "Styrka att skala", "value": "Ett befintligt erbjudande att göra tydligare och mer mätbart"})

    finding_cards = [
        {
            "label": f"0{index + 1}",
            "value": _text(item.get("title"), "Verifierad observation"),
            "detail": _text(item.get("detail"), "Se analysens källunderlag."),
        }
        for index, item in enumerate(top_findings)
    ]
    if not finding_cards:
        finding_cards = [{"label": "01", "value": "Stabil teknisk grund", "detail": "Fördjupa nästa steg med innehålls-, konverterings- och användarmätning."}]

    benefit_cards = [
        {"label": _text(item.get("title"), "Effekt"), "value": _text(item.get("detail"), "Mätbar förbättring i prioriterad kundresa.")}
        for item in benefits
    ]
    if not benefit_cards:
        benefit_cards = [
            {"label": "Tydligare", "value": "Rätt budskap för rätt behov."},
            {"label": "Kortare", "value": "Färre steg till nästa handling."},
            {"label": "Mätbart", "value": "Synlig effekt från källa till lead."},
        ]

    roadmap_cards = [
        {"label": _text(item.get("week"), f"Steg {index + 1}"), "value": _text(item.get("title"), "Prioriterad leverans")}
        for index, item in enumerate(timeline[:3])
    ]
    if not roadmap_cards:
        roadmap_cards = [
            {"label": "0–30 dagar", "value": "Budskap, struktur och mätplan"},
            {"label": "31–60 dagar", "value": "Prioriterade sidor och konverteringsflöden"},
            {"label": "61–90 dagar", "value": "Test, lärande och optimering"},
        ]
    primary_effect = _text((benefits[0] if benefits else {}).get("title"), "Kvalificerade nästa steg")
    roadmap_cards.append({"label": "Primär effekt", "value": primary_effect})
    investment = recommended.get("price_sek") if recommended else None
    if isinstance(investment, (int, float)) and investment > 0:
        roadmap_cards.append({"label": "Investering", "value": f"{int(investment):,} SEK exkl. moms".replace(",", " ")})

    current_screenshot = None
    if isinstance(technical, dict):
        pagespeed = technical.get("pagespeed")
        candidate = pagespeed.get("final_screenshot") if isinstance(pagespeed, dict) else None
        if isinstance(candidate, str) and candidate.startswith("data:image/") and len(candidate) <= 750_000:
            current_screenshot = candidate

    comparison_cards = [
        {
            "label": "Nuläge",
            "value": _text((top_findings[0] if top_findings else {}).get("title"), "En bred kundresa med flera konkurrerande nästa steg"),
            "detail": _text((top_findings[0] if top_findings else {}).get("detail"), "Verifiera nuläget tillsammans i mötet."),
            "image": current_screenshot,
        },
        {
            "label": "Målbild · koncept",
            "value": _text(row.headline, f"Ett tydligare digitalt upplägg för {company}"),
            "detail": _text(row.summary, "Separata kundresor med rätt budskap, bevis och nästa steg."),
        },
    ]

    score_disclaimer = (
        "Prioriteringssignal från en avgränsad statisk sidanalys — valideras i mötet."
        if static_scope
        else "Prioriteringssignal från den avgränsade analysen — inte ett löfte om affärsutfall."
    )
    signal_cards = (
        [
            {"label": "Omfattning", "value": "1 publik sida"},
            {"label": "Källbevis", "value": str(len(_load(analysis.evidence_json, [])))},
            {"label": "Status", "value": "Validera i mötet"},
        ]
        if static_scope
        else [
            {"label": "SEO", "value": str(analysis.seo_score)},
            {"label": "Tillgänglighet", "value": str(analysis.accessibility_score)},
            {"label": "Mobil", "value": str(analysis.mobile_score)},
        ]
    )
    package_line = "Ett avgränsat nästa steg utan onödig ombyggnad."
    if recommended:
        package_line = f"Rekommenderat spår: {_text(recommended.get('name'), 'Tillväxt')} — {_text(', '.join(recommended.get('features') or []), 'prioriterad förbättring och mätning')}"

    scenes = [
        {
            "id": "opening",
            "eyebrow": "Nova · kundmöte",
            "title": f"{company} har redan grunden.",
            "body": "Nu gör vi den digitala närvaron tydligare, mer övertygande och enklare att mäta.",
            "duration": 14,
            "narration": f"{company} har redan ett erbjudande och en digital grund att bygga vidare på. Möjligheten är att göra varje signal tydligare, varje kundresa kortare och varje viktigt steg mätbart.",
            "visual": "orb",
            "cards": [],
        },
        {
            "id": "strength",
            "eyebrow": "Utgångsläge",
            "title": "Vi börjar med det som redan fungerar.",
            "body": "Förslaget förstärker befintliga tillgångar i stället för att börja om utan anledning.",
            "duration": 15,
            "narration": "Bra optimering börjar inte med att riva. Den börjar med att identifiera vad som redan skapar förtroende, och sedan göra just det lättare att hitta, förstå och välja.",
            "visual": "cards",
            "cards": strength_cards,
        },
        {
            "id": "signal",
            "eyebrow": "Förbättringspotential",
            "title": f"{analysis.improvement_score} av 100 i prioriteringssignal.",
            "body": score_disclaimer,
            "duration": 14,
            "narration": f"Nova visar en förbättringssignal på {analysis.improvement_score} av 100. Det är inte ett betyg på hela verksamheten, utan ett sätt att prioritera vad som bör verifieras och förbättras först.",
            "visual": "score",
            "cards": signal_cards,
        },
        {
            "id": "findings",
            "eyebrow": "Det som bromsar",
            "title": "Tre observationer. Ett tydligt fokus.",
            "body": "Varje punkt kommer från analysens sparade källunderlag och ska verifieras av en människa.",
            "duration": 18,
            "narration": "Här är de högst prioriterade observationerna. De gör samtalet konkret: inte allmänna åsikter om design, utan synliga hinder som kan kopplas till relevans, förtroende och nästa handling.",
            "visual": "findings",
            "cards": finding_cards,
        },
        {
            "id": "engine",
            "eyebrow": "Målbild",
            "title": "Fyra delar som arbetar tillsammans.",
            "body": "Synlighet skapar inte värde ensam. Budskap, bevis, konvertering och mätning måste bilda ett sammanhängande system.",
            "duration": 18,
            "narration": "Målbilden är inte bara en snyggare webbplats. Det är ett system där rätt besökare hittar in, förstår värdet, ser bevis, tar nästa steg och där utfallet går att följa.",
            "visual": "engine",
            "cards": [{"label": item["label"], "value": item["detail"]} for item in actions],
        },
        {
            "id": "structure",
            "eyebrow": "Före → efter",
            "title": "Från nuläge till en tydligare kundresa.",
            "body": "Målbilden är ett diskussionskoncept — inte färdig design. Den visar hur analysen kan omsättas i ett konkret vägval.",
            "duration": 17,
            "narration": f"Här blir skillnaden konkret. Nuläget visar den högst prioriterade friktionen. Målbilden visar hur {company} kan samla budskap, bevis och nästa steg i en tydligare kundresa. Konceptet ska valideras tillsammans, inte säljas in som färdig design.",
            "visual": "comparison",
            "cards": comparison_cards,
        },
        {
            "id": "impact",
            "eyebrow": "Affärseffekt",
            "title": "Optimera för beslut — inte bara trafik.",
            "body": "Varje förbättring kopplas till ett beteende som går att följa före och efter lansering.",
            "duration": 16,
            "narration": "Det viktiga är inte fler sidvisningar i sig. Det viktiga är fler relevanta beslut: att rätt person stannar, förstår, går vidare och blir ett kvalificerat nästa steg.",
            "visual": "impact",
            "cards": benefit_cards,
        },
        {
            "id": "roadmap",
            "eyebrow": "90-dagars pilot",
            "title": "Ett konkret beslut — med tydlig omfattning.",
            "body": f"{package_line} Affärskalkyl och slutliga villkor hanteras separat efter gemensam scope.",
            "duration": 18,
            "narration": "Vi behöver inte göra allt samtidigt. Piloten avgränsas till en prioriterad kundresa, ett primärt effektmått och tre tydliga leveranssteg. Slutliga villkor hanteras separat efter gemensam scope; här fokuserar vi på omfattning, arbetssätt och den effekt som ska följas.",
            "visual": "roadmap",
            "cards": roadmap_cards,
        },
        {
            "id": "closing",
            "eyebrow": "Nästa steg",
            "title": "Gör det starka omöjligt att missa.",
            "body": "Välj en prioriterad kundresa. Sätt nuläget. Bygg, mät och bevisa förbättringen tillsammans.",
            "duration": 15,
            "narration": f"{company} behöver inte fler lösa idéer. Nästa steg är att välja en prioriterad kundresa, sätta ett tydligt nuläge och bevisa förbättringen i en avgränsad sprint. Låt oss börja där effekten blir synlig först.",
            "visual": "orb",
            "cards": [],
        },
    ]
    return {
        "company": company,
        "domain": domain,
        "proposal_version": row.version,
        "scope_note": score_disclaimer,
        "scenes": scenes,
        "duration_seconds": sum(scene["duration"] for scene in scenes),
    }


def _card_html(card: dict[str, Any]) -> str:
    detail = _text(card.get("detail"))
    image = card.get("image")
    image_html = ""
    if isinstance(image, str) and image.startswith("data:image/") and len(image) <= 750_000:
        image_html = f'<img alt="Automatiserad mobil skärmbild av nuläget" src="{escape(image, quote=True)}">'
    return (
        "<article class=\"nova-meeting-card\">"
        f"{image_html}"
        f"<small>{escape(_text(card.get('label'), 'Fokus'))}</small>"
        f"<strong>{escape(_text(card.get('value'), 'Prioriterad förbättring'))}</strong>"
        f"{'<p>' + escape(detail) + '</p>' if detail else ''}"
        "</article>"
    )


def render_meeting_presentation_html(
    row: WebsiteProposal,
    prospect: WebsiteProspect,
    analysis: WebsiteAnalysis,
) -> str:
    """Render the Nova story as a standalone, self-running meeting film."""
    story = build_meeting_story(row, prospect, analysis)
    scene_html: list[str] = []
    for index, scene in enumerate(story["scenes"]):
        cards = "".join(_card_html(card) for card in scene["cards"])
        score = analysis.improvement_score if scene["visual"] == "score" else ""
        scene_html.append(
            f"<section class=\"nova-meeting-scene nova-meeting-scene--{escape(scene['visual'])}\" "
            f"data-duration=\"{int(scene['duration'])}\" data-narration=\"{escape(scene['narration'], quote=True)}\" "
            f"aria-hidden=\"{'false' if index == 0 else 'true'}\">"
            "<div class=\"nova-meeting-copy\">"
            f"<span class=\"nova-meeting-kicker\">{escape(scene['eyebrow'])}</span>"
            f"<h1>{escape(scene['title'])}</h1>"
            f"<p>{escape(scene['body'])}</p>"
            "</div>"
            "<div class=\"nova-meeting-visual\">"
            f"<div class=\"nova-meeting-score\"><b>{score}</b><span>{'prioriteringssignal' if score != '' else ''}</span></div>"
            f"<div class=\"nova-meeting-orb\"><i></i><i></i><strong>{escape(story['company'][:2].upper())}</strong></div>"
            f"<div class=\"nova-meeting-cards\">{cards}</div>"
            "</div>"
            f"<div class=\"nova-meeting-caption\">{escape(scene['narration'])}</div>"
            "</section>"
        )
    scenes = "".join(scene_html)
    total = int(story["duration_seconds"])
    title = f"Nova mötesfilm — {story['company']}"
    return f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive"><title>{escape(title)}</title>
<style>
:root{{--bg:#06101e;--panel:rgba(14,29,51,.78);--line:rgba(179,210,242,.18);--text:#f5f8fc;--muted:#9badc4;--blue:#4ba8ff;--cyan:#63e2d5;--coral:#ff9575}}
*{{box-sizing:border-box}}html,body{{width:100%;height:100%;margin:0;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",Arial,sans-serif;overflow:hidden}}
button,input{{font:inherit}}.nova-meeting{{position:relative;width:100vw;height:100svh;isolation:isolate;background:radial-gradient(circle at 82% 18%,rgba(50,126,207,.17),transparent 34%),radial-gradient(circle at 15% 94%,rgba(34,189,172,.12),transparent 32%),linear-gradient(145deg,#050d18,#09182b)}}
.nova-meeting:before{{position:absolute;inset:0;z-index:-1;content:"";background-image:linear-gradient(rgba(145,184,226,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(145,184,226,.035) 1px,transparent 1px);background-size:64px 64px;mask-image:linear-gradient(to bottom,transparent,#000 18%,#000 78%,transparent)}}
.nova-meeting-start{{position:absolute;inset:0;z-index:20;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;padding:clamp(30px,7vw,110px);background:linear-gradient(90deg,rgba(4,12,22,.98) 0 45%,rgba(4,12,22,.72) 68%,rgba(4,12,22,.95));transition:opacity .6s ease,visibility .6s ease}}
.nova-meeting.is-started .nova-meeting-start{{opacity:0;visibility:hidden}}.nova-meeting-brand{{display:flex;align-items:center;gap:11px;font-weight:720;letter-spacing:-.02em}}.nova-meeting-brand i{{display:grid;width:30px;height:30px;place-items:center;border:1px solid var(--cyan);border-radius:9px;transform:rotate(45deg);box-shadow:0 0 26px rgba(99,226,213,.2)}}
.nova-meeting-start small,.nova-meeting-kicker{{color:var(--cyan);font-size:12px;font-weight:750;letter-spacing:.16em;text-transform:uppercase}}.nova-meeting-start h1{{max-width:930px;margin:90px 0 20px;font-size:clamp(48px,7.4vw,102px);font-weight:560;letter-spacing:-.065em;line-height:.96}}.nova-meeting-start p{{max-width:680px;margin:0;color:var(--muted);font-size:clamp(17px,1.7vw,22px);line-height:1.55}}.nova-meeting-start button{{display:flex;align-items:center;gap:10px;margin-top:36px;border:0;border-radius:999px;padding:17px 25px;background:var(--text);color:#07111f;font-weight:750;cursor:pointer;box-shadow:0 18px 42px rgba(0,0,0,.3)}}
.nova-meeting-top{{position:absolute;top:0;right:0;left:0;z-index:8;display:flex;justify-content:space-between;align-items:center;padding:24px clamp(24px,4vw,68px);font-size:14px}}.nova-meeting-top>span{{color:var(--muted);font-size:11px;letter-spacing:.12em;text-transform:uppercase}}
.nova-meeting-scene{{position:absolute;inset:0;display:grid;grid-template-columns:minmax(0,1.02fr) minmax(360px,.98fr);align-items:center;gap:5vw;padding:105px clamp(28px,7vw,120px) 145px;opacity:0;visibility:hidden;transform:translateY(18px) scale(.992);transition:opacity .75s ease,transform .75s ease,visibility .75s ease}}.nova-meeting-scene.is-active{{opacity:1;visibility:visible;transform:none}}
.nova-meeting-copy{{max-width:850px}}.nova-meeting-kicker:before{{display:inline-block;width:26px;height:1px;margin:0 10px 3px 0;background:currentColor;content:""}}.nova-meeting-copy h1{{margin:20px 0 22px;font-size:clamp(44px,5.9vw,86px);font-weight:560;letter-spacing:-.06em;line-height:.98}}.nova-meeting-copy>p{{max-width:760px;margin:0;color:var(--muted);font-size:clamp(17px,1.6vw,23px);line-height:1.55}}
.nova-meeting-visual{{position:relative;display:grid;min-height:430px;place-items:center}}.nova-meeting-cards{{display:grid;width:100%;gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}}.nova-meeting-card{{display:grid;min-height:116px;align-content:center;gap:8px;border:1px solid var(--line);border-radius:18px;padding:18px 20px;background:linear-gradient(145deg,rgba(19,43,72,.86),rgba(9,24,43,.75));box-shadow:0 18px 50px rgba(0,0,0,.12)}}.nova-meeting-card img{{width:100%;max-height:170px;border:1px solid var(--line);border-radius:10px;object-fit:cover;object-position:top}}.nova-meeting-card small{{color:var(--cyan);font-size:10px;font-weight:750;letter-spacing:.13em;text-transform:uppercase}}.nova-meeting-card strong{{font-size:clamp(16px,1.4vw,22px);font-weight:580;line-height:1.2;overflow-wrap:anywhere}}.nova-meeting-card p{{margin:0;color:var(--muted);font-size:12px;line-height:1.4}}
.nova-meeting-scene--comparison .nova-meeting-cards{{grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch}}.nova-meeting-scene--comparison .nova-meeting-card{{min-height:300px;align-content:start}}.nova-meeting-scene--comparison .nova-meeting-card:first-child{{border-color:rgba(255,149,117,.34)}}.nova-meeting-scene--comparison .nova-meeting-card:first-child small{{color:var(--coral)}}
.nova-meeting-scene--findings .nova-meeting-cards,.nova-meeting-scene--impact .nova-meeting-cards{{grid-template-columns:1fr}}.nova-meeting-scene--roadmap .nova-meeting-cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}.nova-meeting-scene--roadmap .nova-meeting-card{{min-height:96px}}.nova-meeting-scene--journey .nova-meeting-cards{{grid-template-columns:repeat(3,1fr)}}.nova-meeting-scene--journey .nova-meeting-card{{min-height:90px}}
.nova-meeting-score{{display:none;width:290px;height:290px;place-items:center;border:1px solid rgba(99,226,213,.44);border-radius:50%;background:radial-gradient(circle,rgba(60,158,211,.2),rgba(5,17,31,.9) 68%);box-shadow:0 0 0 32px rgba(75,168,255,.035),0 0 0 64px rgba(75,168,255,.02),0 0 90px rgba(75,168,255,.2)}}.nova-meeting-score b{{font-size:92px;font-weight:500;letter-spacing:-.08em}}.nova-meeting-score span{{margin-top:-68px;color:var(--cyan);font-size:10px;letter-spacing:.15em;text-transform:uppercase}}.nova-meeting-scene--score .nova-meeting-score{{display:grid}}.nova-meeting-scene--score .nova-meeting-cards{{position:absolute;right:0;bottom:0;grid-template-columns:repeat(3,1fr)}}.nova-meeting-scene--score .nova-meeting-card{{min-height:76px;padding:12px 14px;text-align:center}}
.nova-meeting-orb{{position:relative;display:none;width:280px;height:280px;place-items:center;border:1px solid rgba(99,226,213,.4);border-radius:50%;background:radial-gradient(circle at 36% 30%,rgba(99,226,213,.23),rgba(7,20,37,.92) 64%);box-shadow:0 0 90px rgba(75,168,255,.24)}}.nova-meeting-orb:before,.nova-meeting-orb:after,.nova-meeting-orb i{{position:absolute;border:1px solid rgba(75,168,255,.24);border-radius:50%;content:"";animation:pulse 5s ease-in-out infinite alternate}}.nova-meeting-orb:before{{inset:-44px}}.nova-meeting-orb:after{{inset:-88px;animation-delay:-2s}}.nova-meeting-orb i:first-child{{inset:36px;border-color:rgba(99,226,213,.35)}}.nova-meeting-orb strong{{font-size:38px;font-weight:540;letter-spacing:-.06em}}.nova-meeting-scene--orb .nova-meeting-orb{{display:grid}}.nova-meeting-scene--orb .nova-meeting-cards{{display:none}}
.nova-meeting-caption{{position:absolute;right:clamp(28px,7vw,120px);bottom:82px;left:clamp(28px,7vw,120px);color:#c4d1e0;font-size:14px;line-height:1.5;text-align:center}}
.nova-meeting-controls{{position:absolute;right:0;bottom:0;left:0;z-index:9;display:flex;height:60px;align-items:center;gap:12px;padding:0 clamp(20px,4vw,68px);border-top:1px solid var(--line);background:rgba(4,12,22,.8);backdrop-filter:blur(16px)}}.nova-meeting-controls button{{display:grid;width:34px;height:34px;place-items:center;border:1px solid var(--line);border-radius:50%;background:rgba(255,255,255,.04);color:var(--text);cursor:pointer}}.nova-meeting-controls input{{min-width:100px;flex:1;accent-color:var(--cyan)}}.nova-meeting-controls span{{min-width:42px;color:var(--muted);font-size:11px}}.nova-meeting-controls b{{min-width:72px;color:var(--text);font-size:11px;text-align:center}}
@keyframes pulse{{to{{transform:scale(1.04);opacity:.55}}}}
@media(max-width:820px){{.nova-meeting-scene{{grid-template-columns:1fr;align-content:center;padding-top:82px;padding-bottom:142px}}.nova-meeting-copy h1{{font-size:clamp(38px,10vw,62px)}}.nova-meeting-visual{{min-height:230px}}.nova-meeting-caption{{bottom:70px;font-size:11px}}.nova-meeting-start h1{{margin-top:60px}}.nova-meeting-scene--score .nova-meeting-score{{width:180px;height:180px}}.nova-meeting-score b{{font-size:62px}}.nova-meeting-score span{{margin-top:-44px}}}}
@media(max-width:560px){{.nova-meeting-cards,.nova-meeting-scene--journey .nova-meeting-cards{{grid-template-columns:1fr 1fr}}.nova-meeting-card{{min-height:74px;padding:12px}}.nova-meeting-card p{{display:none}}.nova-meeting-caption{{display:none}}}}
@media(prefers-reduced-motion:reduce){{*,*:before,*:after{{animation:none!important;transition:none!important}}}}
</style></head><body><main class="nova-meeting" id="meeting">
<div class="nova-meeting-start"><div class="nova-meeting-brand"><i></i>SalesOS · Nova</div><div><h1>{escape(story['company'])}<br>nästa digitala rörelse.</h1><p>Kundanpassad mötesfilm · {len(story['scenes'])} kapitel · cirka {total // 60}:{total % 60:02d}. Byggd från Novas analys och det redigerade kundförslaget.</p><button id="start">▶&nbsp; Starta i helskärm</button></div></div>
<header class="nova-meeting-top"><div class="nova-meeting-brand"><i></i>Nova · {escape(story['company'])}</div><span>{escape(story['domain'])} · förslag v{int(story['proposal_version'])}</span></header>
{scenes}
<footer class="nova-meeting-controls"><button id="previous" aria-label="Föregående">‹</button><button id="play" aria-label="Pausa">Ⅱ</button><button id="next" aria-label="Nästa">›</button><span id="elapsed">0:00</span><input id="progress" aria-label="Filmens position" min="0" max="{total}" step="0.1" value="0" type="range"><span>{total // 60}:{total % 60:02d}</span><b id="chapter">01 / {len(story['scenes']):02d}</b><button id="mute" aria-label="Stäng av ljud">⌁</button><button id="fullscreen" aria-label="Helskärm">⛶</button></footer>
</main><script>
(()=>{{
const root=document.getElementById('meeting'),scenes=[...document.querySelectorAll('.nova-meeting-scene')],durations=scenes.map(s=>Number(s.dataset.duration)),starts=[];let sum=0;durations.forEach(d=>{{starts.push(sum);sum+=d}});const total=sum;
const start=document.getElementById('start'),play=document.getElementById('play'),progress=document.getElementById('progress'),elapsed=document.getElementById('elapsed'),chapter=document.getElementById('chapter'),mute=document.getElementById('mute');let current=0,playing=false,muted=false,last=performance.now(),active=-1;
const fmt=v=>`${{Math.floor(v/60)}}:${{String(Math.floor(v%60)).padStart(2,'0')}}`;
function voice(){{const list=speechSynthesis.getVoices();return list.find(v=>v.lang.toLowerCase().startsWith('sv')&&/female|woman|sara|sofie|elin|alva/i.test(v.name))||list.find(v=>v.lang.toLowerCase().startsWith('sv'))||null}}
function speak(i){{if(muted||!playing||!('speechSynthesis'in window))return;window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(scenes[i].dataset.narration||'');u.lang='sv-SE';u.rate=1.01;const v=voice();if(v)u.voice=v;speechSynthesis.speak(u)}}
function show(i,announce=true){{i=Math.max(0,Math.min(scenes.length-1,i));if(i===active)return;scenes.forEach((s,n)=>{{s.classList.toggle('is-active',n===i);s.setAttribute('aria-hidden',n===i?'false':'true')}});active=i;chapter.textContent=`${{String(i+1).padStart(2,'0')}} / ${{String(scenes.length).padStart(2,'0')}}`;if(announce)speak(i)}}
function indexAt(t){{let i=0;starts.forEach((s,n)=>{{if(t>=s)i=n}});return i}}
function update(){{progress.value=String(current);elapsed.textContent=fmt(current);show(indexAt(Math.min(current,total-.01)));}}
function setPlaying(value){{playing=value;play.textContent=value?'Ⅱ':'▶';play.setAttribute('aria-label',value?'Pausa':'Spela');if(!value&&'speechSynthesis'in window)window.speechSynthesis.cancel();if(value)speak(active<0?0:active)}}
function seek(v){{current=Math.max(0,Math.min(total-.01,v));show(indexAt(current),false);update();if(playing)speak(active)}}
function frame(now){{const delta=(now-last)/1000;last=now;if(playing){{current+=delta;if(current>=total){{current=total-.01;setPlaying(false)}}update()}}requestAnimationFrame(frame)}}
start.addEventListener('click',()=>{{root.classList.add('is-started');current=0;show(0,false);setPlaying(true);document.documentElement.requestFullscreen?.().catch(()=>{{}})}});play.addEventListener('click',()=>setPlaying(!playing));progress.addEventListener('input',e=>seek(Number(e.target.value)));document.getElementById('previous').addEventListener('click',()=>seek(starts[Math.max(0,indexAt(current)-1)]));document.getElementById('next').addEventListener('click',()=>seek(starts[Math.min(starts.length-1,indexAt(current)+1)]));mute.addEventListener('click',()=>{{muted=!muted;mute.textContent=muted?'×':'⌁';if(muted)window.speechSynthesis?.cancel();else if(playing)speak(active)}});document.getElementById('fullscreen').addEventListener('click',()=>document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen?.());
addEventListener('keydown',e=>{{if(e.code==='Space'){{e.preventDefault();setPlaying(!playing)}}else if(e.key==='ArrowRight')seek(current+5);else if(e.key==='ArrowLeft')seek(current-5);else if(e.key.toLowerCase()==='m')mute.click();else if(e.key.toLowerCase()==='f')document.getElementById('fullscreen').click()}});show(0,false);requestAnimationFrame(frame);
}})();
</script></body></html>"""
