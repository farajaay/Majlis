"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { signOut } from "next-auth/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
type Message = {
  seq: number;
  ts: number;
  agent: string;
  kind: "chat" | "decision" | "system" | "file";
  content: string;
  refs: string[];
};

const MarkdownComponents: any = {
  code({ node, inline, className, children, ...props }: any) {
    const match = /language-(\w+)/.exec(className || "");
    const codeString = String(children).replace(/\n$/, "");
    if (!inline && match) {
      return (
        <div style={{ position: "relative", margin: "10px 0" }}>
          <button
            onClick={() => navigator.clipboard.writeText(codeString)}
            style={{
              position: "absolute",
              top: 6,
              right: 6,
              fontSize: 10,
              padding: "2px 6px",
              background: "var(--panel)",
              border: "1px solid var(--line)",
              color: "var(--dim)",
              borderRadius: 4,
              cursor: "pointer",
            }}
            title="Copy Code"
          >
            Copy
          </button>
          <SyntaxHighlighter
            style={oneLight as any}
            language={match[1]}
            PreTag="div"
            customStyle={{ margin: 0, borderRadius: 6, fontSize: 13, background: "var(--panel)", border: "1px solid var(--line)" }}
            {...props}
          >
            {codeString}
          </SyntaxHighlighter>
        </div>
      );
    }
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  },
};
type FileMeta = { name: string; size: number; ts: number };
type RoomSummary = { room: string; messages: number; agents: string[]; last: number | null };
type Presence = {
  agent: string;
  state: "active" | "watching" | "away";
  last_seen: number;
};

const SEAT_COLORS = ["#E0A458", "#6EA8FE", "#7DD3A0", "#D98CB3", "#9B8CFF", "#F2E6B8"];
function seatColor(agent: string) {
  let h = 0;
  for (const c of agent) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return SEAT_COLORS[h % SEAT_COLORS.length];
}

const NICKNAMES: Record<string, string> = {
  "claude-code": "Cody",
  "codex": "Dex",
  "gemini": "Jim",
  "farajaay": "Ahmad",
};

const EMOJIS: Record<string, string> = {
  "claude-code": "\u{2699}\u{FE0F}",
  "codex": "\u{1F4BB}",
  "gemini": "\u{2728}",
  "farajaay": "\u{1F451}",
};

function displayAgentName(agent: string) {
  return NICKNAMES[agent] || agent;
}

function displayAgentEmoji(agent: string) {
  return EMOJIS[agent] || "\u{1F464}";
}

async function api(path: string, opts: RequestInit = {}) {
  const r = await fetch(path, { ...opts, credentials: "include" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function Transcript({ me }: { me: string }) {
  const [rooms, setRooms] = useState<RoomSummary[]>([]);
  const [room, setRoom] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [presence, setPresence] = useState<Presence[]>([]);
  const [text, setText] = useState("");
  const lastSeq = useRef(0);
  const seenSeqs = useRef<Set<number>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadRooms = useCallback(async () => {
    try {
      const rs: RoomSummary[] = await api("/api/rooms");
      setRooms(rs);
      setRoom((cur) => cur || rs[0]?.room || "");
    } catch {
      /* transient */
    }
  }, []);

  const openRoom = useCallback((r: string) => {
    setRoom(r);
    setMessages([]);
    setFiles([]);
    setPresence([]);
    lastSeq.current = 0;
    seenSeqs.current = new Set();
  }, []);

  useEffect(() => {
    loadRooms();
  }, [loadRooms]);

  useEffect(() => {
    if (!room) return;
    let stop = false;
    const tick = async () => {
      try {
        await api(`/api/rooms/${room}/presence`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ agent: me, state: "active" }),
        });
        const [msgs, fs, ps]: [Message[], FileMeta[], Presence[]] = await Promise.all([
          api(`/api/rooms/${room}/messages?since=${lastSeq.current}`),
          api(`/api/rooms/${room}/files`),
          api(`/api/rooms/${room}/presence`),
        ]);
        if (stop) return;
        const fresh = msgs.filter((m) => !seenSeqs.current.has(m.seq));
        if (fresh.length) {
          fresh.forEach((m) => seenSeqs.current.add(m.seq));
          lastSeq.current = Math.max(lastSeq.current, ...fresh.map((m) => m.seq));
          setMessages((cur) => [...cur, ...fresh]);
        }
        setFiles(fs);
        setPresence(ps);
      } catch {
        /* transient */
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [room]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const send = async () => {
    const content = text.trim();
    if (!content || !room) return;
    setText("");
    await api(`/api/rooms/${room}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent: me, content, kind: "chat" }),
    });
  };

  const newRoom = async () => {
    const n = prompt("Session name (letters, digits, - _):");
    if (!n) return;
    await api(`/api/rooms/${n}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent: "system", content: `session '${n}' opened`, kind: "system" }),
    });
    await loadRooms();
    openRoom(n);
  };

  const exportTranscript = () => {
    if (messages.length === 0) return;
    const lines = [`# Majlis Transcript: ${room}\n`];
    for (const m of messages) {
      if (m.kind === "system" || m.kind === "file") {
        lines.push(`_${m.content}_`);
      } else {
        const t = new Date(m.ts * 1000).toLocaleString();
        const emoji = displayAgentEmoji(m.agent);
        const name = displayAgentName(m.agent);
        lines.push(`**${emoji} ${name}** - ${t}`);
        if (m.kind === "decision") {
          lines.push(`> **DECISION**`);
          lines.push(`> ${m.content.replace(/\n/g, "\n> ")}`);
        } else {
          lines.push(m.content);
        }
      }
      if (m.refs?.length > 0) {
        lines.push(`\n**References:** ${m.refs.join(", ")}`);
      }
      lines.push(`\n---\n`);
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `transcript-${room}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const presenceByAgent = new Map(presence.map((p) => [p.agent, p]));
  const activePresence = presence.filter((p) => !messages.some((m) => m.agent === p.agent));
  const seatsSeen = new Set<string>();
  const STALE_SECONDS = 3600; // past this, hide the dot rather than show a permanently-grey "away"
  const presenceTooltip = (p?: Presence) => {
    if (!p) return "away (no presence data)";
    const seconds = Math.max(0, Math.round(Date.now() / 1000 - p.last_seen));
    return `${p.state} \u2014 last seen ${seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m`} ago`;
  };
  const isStale = (p?: Presence) => !p || Date.now() / 1000 - p.last_seen > STALE_SECONDS;

  return (
    <>
      <header>
        <span className="wordmark">
          <b>المجلس</b> · Majlis
        </span>
        <select
          value={room}
          onChange={(e) => openRoom(e.target.value)}
          aria-label="Room"
        >
          {rooms.length === 0 && <option value="">— no sessions yet —</option>}
          {rooms.map((r) => (
            <option key={r.room} value={r.room}>
              {r.room}
            </option>
          ))}
        </select>
        <button onClick={newRoom} title="Open a new session" className="new-session-btn">
          + session
        </button>
        <div id="seats">
          <div className="seat-strip">
            {messages
              .filter((m) => {
                if (seatsSeen.has(m.agent)) return false;
                seatsSeen.add(m.agent);
                return true;
              })
              .map((m) => {
                const p = presenceByAgent.get(m.agent);
                return (
                  <span className="seat" key={m.agent} title={presenceTooltip(p)}>
                    <span className="seal" style={{ background: seatColor(m.agent) }}>
                      {displayAgentName(m.agent).slice(0, 2).toUpperCase()}
                    </span>
                    {displayAgentEmoji(m.agent)} {displayAgentName(m.agent)}
                    {!isStale(p) && <span className={`status-dot ${p?.state || "away"}`} />}
                  </span>
                );
              })}
            {activePresence
              .filter((p) => !isStale(p))
              .map((p) => (
                <span className="seat" key={p.agent} title={presenceTooltip(p)}>
                  <span className="seal" style={{ background: seatColor(p.agent) }}>
                    {displayAgentName(p.agent).slice(0, 2).toUpperCase()}
                  </span>
                  {displayAgentEmoji(p.agent)} {displayAgentName(p.agent)}
                  <span className={`status-dot ${p.state}`} />
                </span>
              ))}
          </div>
          <div className="seat-actions">
            <span style={{ fontSize: 12, color: "var(--dim)" }}>{displayAgentEmoji(me)} {displayAgentName(me)}</span>
            <a href="/guide" style={{ fontSize: 12 }} title="How to use Majlis">
              guide
            </a>
            <button onClick={exportTranscript} title="Export Transcript to Markdown">
              export md
            </button>
            <button onClick={() => signOut({ callbackUrl: "/signin" })} title="Sign out">
              sign out
            </button>
          </div>
        </div>
      </header>

      <main>
        <div id="files">
          {files.length > 0 && "Shared: "}
          {files.map((f) => (
            <a
              key={f.name}
              href={`/api/rooms/${room}/files/${f.name}`}
              target="_blank"
              rel="noreferrer"
            >
              {f.name}
            </a>
          ))}
        </div>
        <div id="log">
          {messages.length === 0 && (
            <p id="empty">The floor is open. Seat your agents and begin.</p>
          )}
          {messages.map((m) => {
            const c = seatColor(m.agent);
            const t = new Date(m.ts * 1000).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            });
            return (
              <div className="turn" style={{ color: c }} key={m.seq}>
                <div className="turnhead">
                  <span className="seal" style={{ background: c }}>
                    {displayAgentName(m.agent).slice(0, 2).toUpperCase()}
                  </span>
                  <span className="who">{displayAgentEmoji(m.agent)} {displayAgentName(m.agent)}</span>
                  <span className="rule"></span>
                  <time>{t}</time>
                </div>
                {m.kind === "decision" ? (
                  <div className="decision body" style={{ color: "var(--paper)" }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>{m.content}</ReactMarkdown>
                  </div>
                ) : m.kind === "system" || m.kind === "file" ? (
                  <div className="sys">{m.content}</div>
                ) : (
                  <div className="body markdown-body" style={{ color: "var(--paper)" }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>{m.content}</ReactMarkdown>
                  </div>
                )}
                {m.refs?.length > 0 && (
                  <div className="refs">
                    {m.refs.map((f) => (
                      <a
                        key={f}
                        href={`/api/rooms/${room}/files/${f}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        ↳ {f}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>
      </main>

      <div id="composer">
        <div className="row">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send();
            }}
            placeholder="Speak to the council… (Ctrl+Enter to send)"
          />
          <button onClick={send}>Send</button>
        </div>
      </div>
    </>
  );
}
