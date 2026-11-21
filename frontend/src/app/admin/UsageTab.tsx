"use client";

import { useCallback } from "react";
import styled from "styled-components";
import { Button } from "@/common/components";
import { adminApi } from "@/lib/csl";
import type { AdminSessionRow, UsageBucket, UsageReport } from "@/lib/csl";
import {
  Card,
  ErrorText,
  Grid,
  Heading,
  Meta,
  Notice,
  Row,
  Stat,
  Table,
  TableWrap,
  int,
  percent,
  usd,
  useAdminLoad,
} from "./ui";

const Bar = styled.div<{ $ratio: number }>`
  height: 8px;
  border-radius: 4px;
  background: ${({ theme }) => theme.colors.GRAY[200]};
  overflow: hidden;

  &::after {
    content: "";
    display: block;
    height: 100%;
    width: ${({ $ratio }) => Math.min(100, Math.max(0, $ratio * 100))}%;
    background: ${({ theme, $ratio }) => ($ratio > 0.8 ? theme.colors.ROSE[900] : theme.colors.SLATE[600])};
  }
`;

function BucketTable({ title, keyLabel, buckets }: { title: string; keyLabel: string; buckets: UsageBucket[] }) {
  return (
    <Card>
      <Heading>{title}</Heading>
      {buckets.length === 0 ? (
        <Meta>No LLM calls recorded.</Meta>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <th>{keyLabel}</th>
                <th className="num">Calls</th>
                <th className="num">Errors</th>
                <th className="num">Input tokens</th>
                <th className="num">Cached input</th>
                <th className="num">Cache hit rate</th>
                <th className="num">Output tokens</th>
                <th className="num">Reasoning tokens</th>
                <th className="num">Avg latency</th>
                <th className="num">Cost</th>
              </tr>
            </thead>
            <tbody>
              {buckets.map((b) => (
                <tr key={b.key}>
                  <td>{b.key}</td>
                  <td className="num">{int(b.calls)}</td>
                  <td className="num">{b.errors ? int(b.errors) : "–"}</td>
                  <td className="num">{int(b.promptTokens)}</td>
                  <td className="num">{b.cacheMeasuredTokens ? int(b.cachedTokens) : "–"}</td>
                  <td className="num">{percent(b.cacheHitRate)}</td>
                  <td className="num">{int(b.completionTokens)}</td>
                  <td className="num">{b.reasoningTokens ? int(b.reasoningTokens) : "–"}</td>
                  <td className="num">{b.avgSeconds.toFixed(1)}s</td>
                  <td className="num">
                    {usd(b.cost, b.estimated)}
                    {b.unpricedCalls ? ` (+${b.unpricedCalls} unpriced)` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}
    </Card>
  );
}

export function UsageTab({ token, apiKeySet }: { token: string; apiKeySet: boolean }) {
  const fetcher = useCallback(() => Promise.all([adminApi.usage(token), adminApi.sessions(token)]), [token]);
  const { data, error, loading, reload } = useAdminLoad(fetcher);
  const report: UsageReport | null = data?.[0] ?? null;
  const sessions: AdminSessionRow[] = data?.[1] ?? [];

  const key = report?.openrouter ?? null;
  const total = report?.total;
  const withLlm = sessions.filter((s) => s.llmCalls > 0);
  const perSession = withLlm.length ? withLlm.reduce((sum, s) => sum + s.cost, 0) / withLlm.length : null;

  return (
    <>
      <Row>
        <Button variant="ghost" onClick={reload} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
        {error ? <ErrorText>{error}</ErrorText> : null}
      </Row>

      <Card>
        <Heading>OpenRouter key spend (what is actually billed)</Heading>
        {!apiKeySet ? (
          <Meta>OPENROUTER_API_KEY is not set on the server.</Meta>
        ) : report?.openrouterError ? (
          <ErrorText>Could not get the key info from OpenRouter: {report.openrouterError}</ErrorText>
        ) : key ? (
          <>
            <Grid>
              <Stat label="Total spent" value={usd(key.usage)} hint={key.label ?? undefined} />
              <Stat label="Today" value={usd(key.usageDaily)} />
              <Stat label="This week" value={usd(key.usageWeekly)} />
              <Stat label="This month" value={usd(key.usageMonthly)} />
              <Stat
                label="Key limit / remaining"
                value={key.limit == null ? "No limit" : usd(key.limitRemaining)}
                hint={key.limit == null ? "A per-key limit can be set on OpenRouter" : `Limit ${usd(key.limit)}`}
              />
            </Grid>
            {key.limit ? <Bar $ratio={key.usage / key.limit} /> : null}
            <Meta>Counted by OpenRouter: includes spend from anywhere else this key is used, and may lag a few minutes.</Meta>
          </>
        ) : (
          <Meta>Loading…</Meta>
        )}
      </Card>

      {total ? (
        <Card>
          <Heading>LLM calls from this server (event log)</Heading>
          <Grid>
            <Stat label="Calls" value={int(total.calls)} hint={total.errors ? `${int(total.errors)} errors` : undefined} />
            <Stat label="Input tokens" value={int(total.promptTokens)} />
            <Stat
              label="Cache hit rate"
              value={percent(total.cacheHitRate)}
              hint={
                total.cacheMeasuredTokens
                  ? `${int(total.cachedTokens)} of ${int(total.cacheMeasuredTokens)} input tokens read from cache` +
                    (total.cacheWriteTokens ? `, ${int(total.cacheWriteTokens)} written` : "")
                  : "No call has reported cache figures yet"
              }
            />
            <Stat
              label="Output tokens"
              value={int(total.completionTokens)}
              hint={total.reasoningTokens ? `incl. ${int(total.reasoningTokens)} reasoning` : undefined}
            />
            <Stat label="Cost" value={usd(total.cost, total.estimated)} />
            <Stat
              label="Average per LLM session"
              value={perSession == null ? "–" : usd(perSession, total.estimated)}
              hint={`${withLlm.length} sessions`}
            />
            <Stat label="Avg latency" value={`${total.avgSeconds.toFixed(1)}s`} />
          </Grid>
          {total.estimated || total.unpricedCalls ? (
            <Notice>
              ≈ marks costs estimated from list prices for calls where OpenRouter reported no cost.
              {total.unpricedCalls ? ` ${total.unpricedCalls} calls with an unknown price are left out.` : ""}
            </Notice>
          ) : null}
          <Meta>
            Cache hit rate: input tokens read from the provider&apos;s prompt cache, divided by the input tokens of
            the calls that reported a cache figure (older calls, logged before this was recorded, are left out). Some providers, Anthropic among them, cache
            only when the request asks for it (cache_control). The csl pipeline&apos;s discussion calls do; the
            baseline, and with it csl&apos;s state updates, does not, so those calls show 0%.
          </Meta>
          <Meta>
            Turns cancelled midway (prefetched turns dropped when the learner interjects) report no tokens
            and are missing here. For the exact amount, use the OpenRouter key spend above.
          </Meta>
        </Card>
      ) : null}

      {report ? (
        <>
          <BucketTable title="By model" keyLabel="Model" buckets={report.byModel} />
          <BucketTable title="By day" keyLabel="Day" buckets={report.byDay} />
        </>
      ) : null}
    </>
  );
}
