"use client";
import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
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

type FileMeta = { name: string; size: number; ts: number };
type RoomSummary = { room: string; messages: number; agents: string[]; last: number | null };
type Presence = {
  agent: string;
  state: "active" | "watching" | "away";
  last_seen: number;
};

type ComposerMode = "ask" | "provoke" | "verify" | "decide" | "build";

type SeatStat = {
  agent: string;
  count: number;
  lastTs: number;
  decisions: number;
  files: number;
  presence?: Presence;
};

const MarkdownComponents: any = {
  code({ inline, className, children, ...props }: any) {
    const match = /language-(\w+)/.exec(className || "");
    const codeString = String(children).replace(/\n$/, "");
    if (!inline && match) {
      return (
        <div className="code-block-wrap">
          <button
            onClick={() => navigator.clipboard.writeText(codeString)}
            className="copy-code"
            title="Copy code"
            type="button"
          >
            Copy
          </button>
          <SyntaxHighlighter
            style={oneLight as any}
            language={match[1]}
            PreTag="div"
            customStyle={{
              margin: 0,
              borderRadius: 6,
              fontSize: 13,
              background: "var(--panel)",
              border: "1px solid var(--line)",
            }}
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

const SEAT_COLORS = ["#d89035", "#3f7fca", "#4f9d69", "#c05d86", "#7664d7", "#b8952f", "#2f9c95"];
const STALE_SECONDS = 3600;

const NICKNAMES: Record<string, string> = {
  "claude-code": "Cody",
  codex: "Dex",
  gemini: "Jim",
  farajaay: "Ahmad",
};

const EMOJIS: Record<string, string> = {
  "claude-code": "CC",
  codex: "DX",
  gemini: "GM",
  farajaay: "AH",
  system: "SY",
};

const MODES: Array<{
  key: ComposerMode;
  label: string;
  cue: string;
  placeholder: string;
}> = [
  { key: "ask", label: "Ask", cue: "Clarify the next useful answer", placeholder: "Ask: What should the council resolve next?" },
  { key: "provoke", label: "Provoke", cue: "Challenge weak assumptions", placeholder: "Provoke: Stress-test this plan from the strongest opposing view." },
  { key: "verify", label: "Verify", cue: "Request evidence or checks", placeholder: "Verify: Confirm the risky assumptions and cite the result." },
  { key: "decide", label: "Decide", cue: "Record an ADR-style outcome", placeholder: "Decide: We will ... because ... Follow-ups: ..." },
  { key: "build", label: "Build", cue: "Ask for implementation", placeholder: "Build: Implement the scoped change and report verification." },
];

function seatColor(agent: string) {
  let h = 0;
  for (const c of agent) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return SEAT_COLORS[h % SEAT_COLORS.length];
}

function displayAgentName(agent: string) {
  return NICKNAMES[agent] || agent;
}

function displayAgentEmoji(agent: string) {
  return EMOJIS[agent] || displayAgentName(agent).slice(0, 2).toUpperCase();
}

function compactTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function relativeAge(ts?: number | null) {
  if (!ts) return "no activity yet";
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function isStale(p?: Presence) {
  return !p || Date.now() / 1000 - p.last_seen > STALE_SECONDS;
}

function presenceTooltip(p?: Presence) {
  if (!p) return "away - no presence data";
  return `${p.state} - last seen ${relativeAge(p.last_seen)}`;
}

function safeFirstLine(content: string, max = 120) {
  const first = content.split(/\r?\n/).find(Boolean)?.trim() || "No detail recorded";
  return first.length > max ? `${first.slice(0, max - 3)}...` : first;
}

function detectMode(content?: string): ComposerMode | null {
  if (!content) return null;
  const match = /^(Ask|Provoke|Verify|Decide|Build)(?:\s+@[\w.-]+)?\s*:/i.exec(content.trim());
  if (!match) return null;
  return match[1].toLowerCase() as ComposerMode;
}

function stripModePrefix(content: string) {
  return content.trim().replace(/^(Ask|Provoke|Verify|Decide|Build)(?:\s+@[\w.-]+)?\s*:\s*/i, "");
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
  const [mode, setMode] = useState<ComposerMode>("ask");
  const [target, setTarget] = useState("all");
  const [drawerOpen, setDrawerOpen] = useState(false);
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
    setTarget("all");
    setDrawerOpen(false);
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
  }, [me, room]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const presenceByAgent = useMemo(() => new Map(presence.map((p) => [p.agent, p])), [presence]);
  const decisions = useMemo(() => messages.filter((m) => m.kind === "decision"), [messages]);
  const currentRoom = rooms.find((r) => r.room === room);
  const latestMessage = messages[messages.length - 1];
  const latestPrompt = [...messages]
    .reverse()
    .find((m) => m.kind === "chat" && (m.agent === me || m.agent === "farajaay")) || latestMessage;
  const detectedMode = detectMode(latestPrompt?.content);
  const activeMode = detectedMode || mode;
  const currentObjective = latestPrompt ? stripModePrefix(safeFirstLine(latestPrompt.content, 140)) : "The floor is open.";

  const seatStats = useMemo(() => {
    const stats = new Map<string, SeatStat>();
    const ensure = (agent: string): SeatStat => {
      const existing = stats.get(agent);
      if (existing) return existing;
      const created = { agent, count: 0, lastTs: 0, decisions: 0, files: 0, presence: presenceByAgent.get(agent) };
      stats.set(agent, created);
      return created;
    };
    for (const p of presence) ensure(p.agent).presence = p;
    for (const m of messages) {
      if (m.agent === "system") continue;
      const stat = ensure(m.agent);
      stat.count += 1;
      stat.lastTs = Math.max(stat.lastTs, m.ts);
      if (m.kind === "decision") stat.decisions += 1;
      if (m.kind === "file") stat.files += 1;
    }
    ensure(me);
    return [...stats.values()].sort((a, b) => {
      const aLive = isStale(a.presence) ? 0 : 1;
      const bLive = isStale(b.presence) ? 0 : 1;
      return bLive - aLive || b.lastTs - a.lastTs || a.agent.localeCompare(b.agent);
    });
  }, [me, messages, presence, presenceByAgent]);

  const operationEvents = useMemo(() => {
    const opPattern = /(watch|claim|invoke|invocation|fail|error|blocked|started|complete|commit|push|shared file)/i;
    return messages
      .filter((m) => m.kind === "system" || m.kind === "file" || opPattern.test(m.content))
      .slice(-7)
      .reverse();
  }, [messages]);

  const targetOptions = seatStats.filter((s) => s.agent !== me && s.agent !== "system");
  const activeSeatCount = seatStats.filter((s) => !isStale(s.presence) && s.presence?.state !== "away").length;
  const modeMeta = MODES.find((m) => m.key === mode) || MODES[0];

  const chooseMode = (next: ComposerMode) => {
    setMode(next);
    const nextMeta = MODES.find((m) => m.key === next) || MODES[0];
    if (!text.trim()) setText(`${nextMeta.label}: `);
  };

  const shapeContent = (raw: string) => {
    const content = raw.trim();
    const meta = MODES.find((m) => m.key === mode) || MODES[0];
    const targetPrefix = target === "all" ? "" : ` @${target}`;
    if (detectMode(content)) return content;
    return `${meta.label}${targetPrefix}: ${content}`;
  };

  const send = async () => {
    const content = text.trim();
    if (!content || !room) return;
    const outgoing = shapeContent(content);
    setText("");
    await api(`/api/rooms/${room}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent: me, content: outgoing, kind: mode === "decide" ? "decision" : "chat" }),
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
        const mark = displayAgentEmoji(m.agent);
        const name = displayAgentName(m.agent);
        lines.push(`**${mark} ${name}** - ${t}`);
        if (m.kind === "decision") {
          lines.push(`> **DECISION**`);
          lines.push(`> ${m.content.replace(/\n/g, "\n> ")}`);
        } else {
          lines.push(m.content);
        }
      }
      if (m.refs?.length > 0) lines.push(`\n**References:** ${m.refs.join(", ")}`);
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

  return (
    <>
      <header className="command-header">
        <div className="brand-zone">
          <span className="wordmark">
            <b>Majlis</b>
            <span>agent council</span>
          </span>
          <div className="room-picker">
            <label htmlFor="room-select">Room</label>
            <select id="room-select" value={room} onChange={(e) => openRoom(e.target.value)} aria-label="Room">
              {rooms.length === 0 && <option value="">no sessions yet</option>}
              {rooms.map((r) => (
                <option key={r.room} value={r.room}>
                  {r.room}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="state-zone">
          <div>
            <span className="stat-label">Mode</span>
            <strong>{MODES.find((m) => m.key === activeMode)?.label || "Ask"}</strong>
          </div>
          <div>
            <span className="stat-label">Objective</span>
            <strong title={currentObjective}>{currentObjective}</strong>
          </div>
          <div>
            <span className="stat-label">Seats</span>
            <strong>{activeSeatCount} live</strong>
          </div>
          <div>
            <span className="stat-label">Turns</span>
            <strong>{currentRoom?.messages ?? messages.length}</strong>
          </div>
        </div>

        <div className="control-zone">
          <button onClick={newRoom} title="Open a new session" type="button">
            + session
          </button>
          <button onClick={() => setDrawerOpen(true)} disabled={decisions.length === 0} title="Open decisions" type="button">
            ADRs
          </button>
          <button onClick={exportTranscript} disabled={messages.length === 0} title="Export transcript to Markdown" type="button">
            export
          </button>
          <a href="/guide" title="How to use Majlis">
            guide
          </a>
          <button onClick={() => signOut({ callbackUrl: "/signin" })} title="Sign out" type="button">
            sign out
          </button>
        </div>
      </header>

      <div className="app-shell">
        <main className="council-floor">
          <section className="shared-files" aria-label="Shared files">
            <span>{files.length ? "Shared files" : "No shared files"}</span>
            {files.map((f) => (
              <a key={f.name} href={`/api/rooms/${room}/files/${f.name}`} target="_blank" rel="noreferrer">
                {f.name}
              </a>
            ))}
          </section>

          <section id="log" aria-label="Transcript">
            {messages.length === 0 && (
              <div id="empty">
                <strong>The floor is open.</strong>
                <span>Seat your agents and begin with an ask, decision, verification request, or build command.</span>
              </div>
            )}
            {messages.map((m) => (
              <Turn
                key={m.seq}
                message={m}
                me={me}
                room={room}
                presence={presenceByAgent.get(m.agent)}
              />
            ))}
            <div ref={bottomRef} />
          </section>
        </main>

        <aside className="context-rail" aria-label="Council context">
          <section className="rail-panel">
            <div className="rail-head">
              <h2>Seats</h2>
              <span>{seatStats.length}</span>
            </div>
            <div className="seat-list">
              {seatStats.map((s) => (
                <div className="seat-row" key={s.agent} title={presenceTooltip(s.presence)}>
                  <span className="seal" style={{ background: seatColor(s.agent) }}>
                    {displayAgentEmoji(s.agent)}
                  </span>
                  <div>
                    <strong>{displayAgentName(s.agent)}</strong>
                    <span>{s.count} turns - last {relativeAge(s.lastTs || s.presence?.last_seen)}</span>
                  </div>
                  <span className={`status-dot ${isStale(s.presence) ? "away" : s.presence?.state || "away"}`} />
                </div>
              ))}
            </div>
          </section>

          <section className="rail-panel">
            <div className="rail-head">
              <h2>Recent Decisions</h2>
              <button onClick={() => setDrawerOpen(true)} disabled={decisions.length === 0} type="button">
                Open
              </button>
            </div>
            {decisions.length === 0 ? (
              <p className="rail-empty">No decisions recorded yet.</p>
            ) : (
              <ol className="decision-list">
                {decisions.slice(-4).reverse().map((d) => (
                  <li key={d.seq}>
                    <span>#{d.seq} - {compactTime(d.ts)}</span>
                    <strong>{safeFirstLine(stripModePrefix(d.content), 88)}</strong>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="rail-panel">
            <div className="rail-head">
              <h2>Operations</h2>
              <span>{operationEvents.length}</span>
            </div>
            {operationEvents.length === 0 ? (
              <p className="rail-empty">No watcher, claim, invocation, file, or failure events detected in this room.</p>
            ) : (
              <ol className="op-list">
                {operationEvents.map((event) => (
                  <li key={event.seq}>
                    <span>#{event.seq} - {compactTime(event.ts)}</span>
                    <strong>{safeFirstLine(event.content, 92)}</strong>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </aside>
      </div>

      <Composer
        mode={mode}
        modeMeta={modeMeta}
        target={target}
        targetOptions={targetOptions}
        text={text}
        onMode={chooseMode}
        onTarget={setTarget}
        onText={setText}
        onSend={send}
      />

      <DecisionDrawer
        open={drawerOpen}
        decisions={decisions}
        onClose={() => setDrawerOpen(false)}
      />
    </>
  );
}

function Turn({
  message,
  me,
  room,
  presence,
}: {
  message: Message;
  me: string;
  room: string;
  presence?: Presence;
}) {
  const color = seatColor(message.agent);
  const role =
    message.kind === "decision"
      ? "decision"
      : message.kind === "system"
        ? "system"
        : message.kind === "file"
          ? "file"
          : message.agent === me || message.agent === "farajaay"
            ? "prompt"
            : "agent";
  const mode = detectMode(message.content);
  const failed = /(fail|error|blocked|exception|unauthorized)/i.test(message.content);
  const className = `turn turn-${role}${failed ? " turn-failure" : ""}`;
  const style = { "--seat-color": color } as CSSProperties;

  return (
    <article className={className} style={style}>
      <div className="turn-head">
        <span className="seq-badge">#{message.seq}</span>
        <span className="seal" style={{ background: color }}>
          {displayAgentEmoji(message.agent)}
        </span>
        <div className="turn-meta">
          <strong>{displayAgentName(message.agent)}</strong>
          <span>
            {roleLabel(role, failed)}
            {mode ? ` - ${MODES.find((m) => m.key === mode)?.label}` : ""}
            {presence && !isStale(presence) ? ` - ${presence.state}` : ""}
          </span>
        </div>
        <time>{compactTime(message.ts)}</time>
      </div>

      {message.kind === "system" || message.kind === "file" ? (
        <div className="sys">{message.content}</div>
      ) : (
        <div className="body markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
            {message.content}
          </ReactMarkdown>
        </div>
      )}

      {message.refs?.length > 0 && (
        <div className="refs">
          {message.refs.map((f) => (
            <a key={f} href={`/api/rooms/${room}/files/${f}`} target="_blank" rel="noreferrer">
              ref: {f}
            </a>
          ))}
        </div>
      )}
    </article>
  );
}

function roleLabel(role: string, failed: boolean) {
  if (failed) return "Failure";
  if (role === "prompt") return "Prompt";
  if (role === "agent") return "Reply";
  if (role === "decision") return "Decision";
  if (role === "file") return "File";
  return "System";
}

function Composer({
  mode,
  modeMeta,
  target,
  targetOptions,
  text,
  onMode,
  onTarget,
  onText,
  onSend,
}: {
  mode: ComposerMode;
  modeMeta: { key: ComposerMode; label: string; cue: string; placeholder: string };
  target: string;
  targetOptions: SeatStat[];
  text: string;
  onMode: (mode: ComposerMode) => void;
  onTarget: (target: string) => void;
  onText: (text: string) => void;
  onSend: () => void;
}) {
  return (
    <div id="composer">
      <div className="composer-inner">
        <div className="mode-strip" role="tablist" aria-label="Composer mode">
          {MODES.map((m) => (
            <button
              key={m.key}
              className={mode === m.key ? "active" : ""}
              onClick={() => onMode(m.key)}
              title={m.cue}
              type="button"
            >
              {m.label}
            </button>
          ))}
        </div>
        <div className="composer-controls">
          <label>
            Target
            <select value={target} onChange={(e) => onTarget(e.target.value)} aria-label="Target seat">
              <option value="all">All seats</option>
              {targetOptions.map((s) => (
                <option key={s.agent} value={s.agent}>
                  {displayAgentName(s.agent)}
                </option>
              ))}
            </select>
          </label>
          <span>{modeMeta.cue}</span>
        </div>
        <div className="composer-row">
          <textarea
            value={text}
            onChange={(e) => onText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) onSend();
            }}
            placeholder={`${modeMeta.placeholder} (Ctrl+Enter to send)`}
          />
          <button onClick={onSend} type="button">
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

function DecisionDrawer({
  open,
  decisions,
  onClose,
}: {
  open: boolean;
  decisions: Message[];
  onClose: () => void;
}) {
  return (
    <div className={`drawer-backdrop ${open ? "open" : ""}`} aria-hidden={!open}>
      <aside className="decision-drawer" aria-label="Decision records">
        <div className="drawer-head">
          <div>
            <span className="stat-label">Decision Log</span>
            <h2>ADR Drawer</h2>
          </div>
          <button onClick={onClose} type="button">
            Close
          </button>
        </div>
        {decisions.length === 0 ? (
          <p className="rail-empty">No decisions recorded yet.</p>
        ) : (
          <ol className="drawer-decisions">
            {decisions.slice().reverse().map((d) => (
              <li key={d.seq}>
                <div>
                  <span>#{d.seq} - {compactTime(d.ts)} - {displayAgentName(d.agent)}</span>
                  <strong>{safeFirstLine(stripModePrefix(d.content), 110)}</strong>
                </div>
                <div className="body markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
                    {d.content}
                  </ReactMarkdown>
                </div>
              </li>
            ))}
          </ol>
        )}
      </aside>
    </div>
  );
}
