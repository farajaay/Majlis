"use client";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * PythiaPanel — a collapsible dark "oracle" console for the hosted council.
 *
 * It watches the room the PYTHIA bridge (scripts/pythia_bridge.py, pointed at
 * this deployment with MAJLIS_TOKEN) posts into, and renders its
 * brief/alert/forecast turns in PYTHIA's ops aesthetic, plus a scrolling event
 * ticker. The "◎ map" toggle embeds PYTHIA's live world map — but only if a
 * *publicly reachable* PYTHIA URL is supplied (a hosted page cannot reach a
 * PYTHIA running on localhost). The URL is user-set and persisted locally.
 */

type OracleMsg = { seq: number; ts: number; agent: string; kind: string; content: string };

const PY_KINDS: Record<string, { tag: string; cls: string }> = {
  brief: { tag: "WORLD BRIEF", cls: "k-brief" },
  alert: { tag: "ALERT", cls: "k-alert" },
  forecast: { tag: "FORECAST", cls: "k-forecast" },
};
const meta = (k: string) => PY_KINDS[k] || { tag: (k || "note").toUpperCase(), cls: "k-note" };
const compactTime = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

async function api(path: string) {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function PythiaPanel() {
  const [room, setRoom] = useState("oracle");
  const [open, setOpen] = useState(false);
  const [mapView, setMapView] = useState(false);
  const [base, setBase] = useState("");
  const [items, setItems] = useState<OracleMsg[]>([]);
  const [live, setLive] = useState(false);
  const sinceRef = useRef(0);
  const seenRef = useRef<Set<number>>(new Set());
  const feedRef = useRef<HTMLDivElement>(null);

  // read persisted prefs after mount (avoids SSR/hydration mismatch)
  useEffect(() => {
    setRoom(localStorage.getItem("pythia_room") || "oracle");
    setBase(localStorage.getItem("pythia_base") || "");
    if (localStorage.getItem("pythia_open")) setOpen(true);
  }, []);

  const poll = useCallback(async () => {
    try {
      const msgs: OracleMsg[] = await api(`/api/rooms/${room}/messages?since=${sinceRef.current}`);
      const fresh = msgs.filter((m) => !seenRef.current.has(m.seq));
      if (fresh.length) {
        fresh.forEach((m) => seenRef.current.add(m.seq));
        sinceRef.current = Math.max(sinceRef.current, ...fresh.map((m) => m.seq));
        setItems((cur) => [...cur, ...fresh]);
      }
      setLive(true);
    } catch {
      setLive(false);
    }
  }, [room]);

  // poll the oracle room only while the panel is open
  useEffect(() => {
    if (!open) return;
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, [open, poll]);

  // keep the feed pinned to the newest card
  useEffect(() => {
    if (!mapView) feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [items, mapView]);

  const toggleOpen = (next?: boolean) => {
    setOpen((cur) => {
      const v = next === undefined ? !cur : next;
      if (typeof window !== "undefined") localStorage.setItem("pythia_open", v ? "1" : "");
      return v;
    });
  };

  const saveBase = (v: string) => {
    const clean = v.trim().replace(/\/+$/, "");
    setBase(clean);
    if (typeof window !== "undefined") localStorage.setItem("pythia_base", clean);
  };

  const tickerItems = items
    .filter((m) => m.kind === "alert" || m.kind === "forecast")
    .slice(-8)
    .map((m) => m.content.replace(/\s+/g, " ").trim());

  const cards = items.filter((m) => m.kind !== "system");

  return (
    <>
      <button
        id="pythia-handle"
        className={live ? "live-ok" : ""}
        aria-label="Toggle PYTHIA oracle panel"
        aria-expanded={open}
        onClick={() => toggleOpen()}
        type="button"
      >
        <span className="py-dot" />
        PYTHIA
      </button>

      <aside id="pythia" className={`${open ? "open" : ""} ${live ? "live-ok" : ""}`} aria-label="PYTHIA oracle feed">
        <div className="py-head">
          <span className="py-live">
            <span className="py-dot" />
            PYTHIA
          </span>
          <span className="py-sub">{room + (live ? " · live" : " · offline")}</span>
          <span className="py-spacer" />
          <button
            className={`py-pill ${mapView ? "on" : ""}`}
            onClick={() => setMapView((v) => !v)}
            title="Toggle live world map"
            type="button"
          >
            ◎ map
          </button>
          <button className="py-pill" onClick={() => toggleOpen(false)} title="Close panel" type="button">
            ✕
          </button>
        </div>

        {!mapView ? (
          <div id="pythia-feed" className="py-feed" ref={feedRef} aria-live="polite">
            {cards.length === 0 ? (
              <div className="py-empty">
                awaiting oracle feed…
                <br />
                <small>
                  point the bridge here:
                  <br />
                  MAJLIS_BASE=&lt;this site&gt; MAJLIS_TOKEN=&lt;PAT&gt;
                  <br />
                  python3 scripts/pythia_bridge.py
                </small>
              </div>
            ) : (
              cards.map((m) => {
                const mt = meta(m.kind);
                return (
                  <div className={`py-card ${mt.cls}`} key={m.seq}>
                    <div className="py-cardhead">
                      <span className="py-tag">{mt.tag}</span>
                      <span className="py-agent">{m.agent}</span>
                      <span className="py-t">{compactTime(m.ts)}</span>
                    </div>
                    <div className="py-body">{m.content}</div>
                  </div>
                );
              })
            )}
          </div>
        ) : (
          <div id="pythia-map" className="py-map">
            <div className="py-mapbar">
              <input
                value={base}
                placeholder="https://your-pythia-host"
                aria-label="PYTHIA base URL"
                onChange={(e) => setBase(e.target.value)}
                onBlur={(e) => saveBase(e.target.value)}
              />
              {base && (
                <a href={base} target="_blank" rel="noopener noreferrer">
                  open ↗
                </a>
              )}
            </div>
            {base ? (
              <iframe title="PYTHIA live world map" src={base} referrerPolicy="no-referrer" />
            ) : (
              <div className="py-empty">
                set a public PYTHIA URL above
                <br />
                <small>a hosted page can’t reach a PYTHIA on localhost</small>
              </div>
            )}
          </div>
        )}

        <div className="py-foot">
          <span className="py-tick">
            {tickerItems.length === 0
              ? "no signals yet"
              : tickerItems.map((s, i) => (
                  <span key={i}>
                    {i > 0 && <span className="sep">◦</span>}
                    {s}
                  </span>
                ))}
          </span>
        </div>
      </aside>
    </>
  );
}
