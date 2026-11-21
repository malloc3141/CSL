"use client";

import { useCallback, useMemo, useState } from "react";
import styled from "styled-components";
import { Button } from "@/common/components";
import { adminApi } from "@/lib/csl";
import type { Accuracy, AdminEvent, AdminSessionDetail, AdminSessionRow, Message, StateVersion } from "@/lib/csl";
import {
  Card,
  ErrorText,
  Heading,
  Input,
  Meta,
  Pre,
  Row,
  Table,
  TableWrap,
  dateTime,
  errorMessage,
  usd,
  useAdminLoad,
} from "./ui";

const Split = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;

  @media (min-width: 1100px) {
    grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
    align-items: start;
  }
`;

const Transcript = styled.ol`
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const Line = styled.li<{ $role: Message["role"] }>`
  padding: 10px 12px;
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme, $role }) =>
    $role === "user"
      ? theme.colors.GREEN[50]
      : $role === "tutor"
        ? theme.colors.BLUE[50]
        : $role === "peer"
          ? theme.colors.GRAY[100]
          : theme.colors.YELLOW[50]};
  font-size: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
`;

const Speaker = styled.div`
  margin-bottom: 4px;
  color: ${({ theme }) => theme.colors.GRAY[500]};
  font-size: 12px;
`;

const Details = styled.details`
  font-size: 13px;

  summary {
    cursor: pointer;
    font-weight: 600;
  }
  ul {
    margin: 6px 0;
    padding-left: 18px;
  }
`;

const MARK: Record<Accuracy, string> = { correct: "○", partial: "△", incorrect: "✕" };
const mark = (accuracy: Accuracy | null) => (accuracy ? `${MARK[accuracy]} ` : "");

function StateHistory({ name, versions }: { name: string; versions: StateVersion[] }) {
  return (
    <Details>
      <summary>
        {name} · {versions.length} versions
      </summary>
      {[...versions].reverse().map((v) => (
        <div key={v.version}>
          <Meta>
            v{v.version}
            {v.turnNumber ? ` · changed in turn ${v.turnNumber}` : " · initial state"} · {dateTime(v.createdAt)}
          </Meta>
          <ul>
            {v.state.beliefs.map((b) => (
              <li key={b.id}>
                {mark(b.accuracy)}
                {b.text}
              </li>
            ))}
            <li>
              Explanation: {mark(v.state.explanationAccuracy)}
              {v.state.explanation}
            </li>
            {v.state.openQuestions.map((q) => (
              <li key={q}>Question: {q}</li>
            ))}
          </ul>
          {v.changes.length ? (
            <Meta>
              Changes:{" "}
              {v.changes.map((c) => `${c.field} ${c.kind}${c.after ? ` → ${c.after}` : ""}`).join(" / ")}
            </Meta>
          ) : null}
        </div>
      ))}
    </Details>
  );
}

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function EventLog({ token, sessionId }: { token: string; sessionId: string }) {
  const [events, setEvents] = useState<AdminEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [type, setType] = useState("");

  const load = async () => {
    setError(null);
    try {
      setEvents(await adminApi.events(token, sessionId));
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };

  const types = useMemo(() => [...new Set((events ?? []).map((e) => e.type))].sort(), [events]);
  const shown = (events ?? []).filter((e) => !type || e.type === type);

  return (
    <Card>
      <Row>
        <Heading>Event log</Heading>
        <Button variant="ghost" onClick={load}>
          {events ? "Reload" : "Load"}
        </Button>
        {events ? (
          <>
            <select value={type} onChange={(event) => setType(event.target.value)} aria-label="Event type">
              <option value="">All ({events.length})</option>
              {types.map((t) => (
                <option key={t} value={t}>
                  {t} ({events.filter((e) => e.type === t).length})
                </option>
              ))}
            </select>
            <Button variant="ghost" onClick={() => download(`csl-${sessionId}-events.json`, events)}>
              Download JSON
            </Button>
          </>
        ) : null}
      </Row>
      {error ? <ErrorText>{error}</ErrorText> : null}
      {events ? (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <th className="num">seq</th>
                <th>Time</th>
                <th>Type</th>
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((e) => (
                <tr key={e.seq}>
                  <td className="num">{e.seq}</td>
                  <td>{dateTime(e.ts)}</td>
                  <td>{e.type}</td>
                  <td className="wrap">
                    <code>{JSON.stringify(e.data)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      ) : null}
    </Card>
  );
}

function SessionView({ token, sessionId }: { token: string; sessionId: string }) {
  const fetcher = useCallback(() => adminApi.session(token, sessionId), [token, sessionId]);
  const { data: detail, error, reload: load } = useAdminLoad<AdminSessionDetail>(fetcher);

  if (error) return <ErrorText>{error}</ErrorText>;
  if (!detail) return <Meta>Loading…</Meta>;

  const s = detail.snapshot;
  const peers = s.participants.filter((p) => p.role === "peer");
  const sections: { title: string; messages: Message[] }[] = [
    { title: "Setup chat", messages: s.messages.filter((m) => m.channel === "init") },
    { title: "Discussion", messages: s.messages.filter((m) => m.channel === "discussion") },
  ];

  return (
    <>
      <Card>
        <Row>
          <Heading>{s.topic}</Heading>
          <Button variant="ghost" onClick={load}>
            Refresh
          </Button>
          <Button variant="ghost" onClick={() => download(`csl-${s.sessionId}.json`, detail)}>
            Download JSON
          </Button>
        </Row>
        <Meta>
          {s.sessionId} · {s.pipeline || "?"} · {s.phase} / {s.status} · {s.language} · started {dateTime(s.createdAt)} ·{" "}
          {detail.live ? "in memory" : "stored copy"}
        </Meta>
        {s.focus ? <Meta>focus: {s.focus}</Meta> : null}
        {s.participants.length ? (
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
            {s.participants.map((p) => (
              <li key={p.id}>
                <b>{p.name}</b> ({p.role}) {p.origin ? `— ${p.origin}` : ""} {p.description ? `/ ${p.description}` : ""}
              </li>
            ))}
          </ul>
        ) : null}
      </Card>

      {sections.map(({ title, messages }) =>
        messages.length ? (
          <Card key={title}>
            <Heading>
              {title} ({messages.length})
            </Heading>
            <Transcript>
              {messages.map((m) => (
                <Line key={m.id} $role={m.role}>
                  <Speaker>
                    {m.turnNumber ? `${m.turnNumber}. ` : ""}
                    {m.speakerName} · {dateTime(m.createdAt)}
                    {m.invited ? " · invited explanation" : ""}
                  </Speaker>
                  {m.text}
                </Line>
              ))}
            </Transcript>
          </Card>
        ) : null,
      )}

      {peers.length ? (
        <Card>
          <Heading>Knowledge state history</Heading>
          {peers.map((p) =>
            s.states[p.id] ? <StateHistory key={p.id} name={p.name} versions={s.states[p.id]} /> : null,
          )}
        </Card>
      ) : null}

      <Card>
        <Details>
          <summary>Pipeline scratch</summary>
          <Pre>{JSON.stringify(detail.scratch, null, 2)}</Pre>
        </Details>
      </Card>

      <EventLog key={sessionId} token={token} sessionId={sessionId} />
    </>
  );
}

export function SessionsTab({ token }: { token: string }) {
  const fetcher = useCallback(() => adminApi.sessions(token), [token]);
  const { data: rows, error, reload: load } = useAdminLoad<AdminSessionRow[]>(fetcher);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const q = query.trim().toLowerCase();
  const shown = (rows ?? []).filter((r) => !q || r.topic.toLowerCase().includes(q) || r.sessionId.startsWith(q));

  return (
    <Split>
      <Card>
        <Row>
          <Heading>Sessions {rows ? `(${rows.length})` : ""}</Heading>
          <Button variant="ghost" onClick={load}>
            Refresh
          </Button>
        </Row>
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by topic or session ID" />
        {error ? <ErrorText>{error}</ErrorText> : null}
        {rows && !rows.length ? <Meta>No sessions yet.</Meta> : null}
        {shown.length ? (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Topic</th>
                  <th>Phase</th>
                  <th>User</th>
                  <th>Pipeline</th>
                  <th className="num">Messages</th>
                  <th className="num">LLM</th>
                  <th className="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr
                    key={r.sessionId}
                    className={`clickable${selected === r.sessionId ? " selected" : ""}`}
                    onClick={() => setSelected(r.sessionId)}
                  >
                    <td>{dateTime(r.createdAt)}</td>
                    <td className="wrap">
                      {r.topic}
                      {r.live ? " ●" : ""}
                    </td>
                    <td>{r.phase ?? "?"}</td>
                    <td>{r.userName ?? "–"}</td>
                    <td>{r.pipeline ?? "–"}</td>
                    <td className="num">{r.messageCount}</td>
                    <td className="num">{r.llmCalls || "–"}</td>
                    <td className="num">{r.llmCalls ? usd(r.cost) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : null}
        <Meta>● = currently loaded in server memory</Meta>
      </Card>

      <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
        {selected ? (
          <SessionView key={selected} token={token} sessionId={selected} />
        ) : (
          <Card>
            <Meta>Pick a session from the list.</Meta>
          </Card>
        )}
      </div>
    </Split>
  );
}
