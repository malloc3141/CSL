"use client";

import { useI18n } from "@/i18n";
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
  const { t } = useI18n();
  return (
    <Card>
      <Heading>{title}</Heading>
      {buckets.length === 0 ? (
        <Meta>{t("noLlmCalls")}</Meta>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <th>{keyLabel}</th>
                <th className="num">{t("calls")}</th>
                <th className="num">{t("errors")}</th>
                <th className="num">{t("inputTokens")}</th>
                <th className="num">{t("cachedInput")}</th>
                <th className="num">{t("cacheHit")}</th>
                <th className="num">{t("outputTokens")}</th>
                <th className="num">{t("reasoningTokens")}</th>
                <th className="num">{t("averageLatency")}</th>
                <th className="num">{t("cost")}</th>
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
  const { t } = useI18n();
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
          {loading ? t("loading") : t("refresh")}
        </Button>
        {error ? <ErrorText>{error}</ErrorText> : null}
      </Row>

      <Card>
        <Heading>{t("openRouterSpend")}</Heading>
        {!apiKeySet ? (
          <Meta>{t("noApiKey")}</Meta>
        ) : report?.openrouterError ? (
          <ErrorText>{t("keyInfoError")} {report.openrouterError}</ErrorText>
        ) : key ? (
          <>
            <Grid>
              <Stat label={t("totalSpent")} value={usd(key.usage)} hint={key.label ?? undefined} />
              <Stat label={t("today")} value={usd(key.usageDaily)} />
              <Stat label={t("week")} value={usd(key.usageWeekly)} />
              <Stat label={t("month")} value={usd(key.usageMonthly)} />
              <Stat
                label={t("keyLimit")}
                value={key.limit == null ? t("noLimit") : usd(key.limitRemaining)}
                hint={key.limit == null ? t("keyLimitHint") : t("limitAmount", { amount: usd(key.limit) })}
              />
            </Grid>
            {key.limit ? <Bar $ratio={key.usage / key.limit} /> : null}
            <Meta>{t("spendNote")}</Meta>
          </>
        ) : (
          <Meta>{t("loading")}</Meta>
        )}
      </Card>

      {total ? (
        <Card>
          <Heading>{t("serverLlmCalls")}</Heading>
          <Grid>
            <Stat label={t("calls")} value={int(total.calls)} hint={total.errors ? t("errorCount", { count: int(total.errors) }) : undefined} />
            <Stat label={t("inputTokens")} value={int(total.promptTokens)} />
            <Stat
              label={t("cacheHit")}
              value={percent(total.cacheHitRate)}
              hint={
                total.cacheMeasuredTokens
                  ? `${int(total.cachedTokens)} of ${int(total.cacheMeasuredTokens)} input tokens read from cache` +
                    (total.cacheWriteTokens ? `, ${int(total.cacheWriteTokens)} written` : "")
                  : t("noCacheData")
              }
            />
            <Stat
              label={t("outputTokens")}
              value={int(total.completionTokens)}
              hint={total.reasoningTokens ? t("includedReasoning", { count: int(total.reasoningTokens) }) : undefined}
            />
            <Stat label={t("cost")} value={usd(total.cost, total.estimated)} />
            <Stat
              label={t("averageSession")}
              value={perSession == null ? "–" : usd(perSession, total.estimated)}
              hint={t("sessionCount", { count: withLlm.length })}
            />
            <Stat label={t("averageLatency")} value={`${total.avgSeconds.toFixed(1)}s`} />
          </Grid>
          {total.estimated || total.unpricedCalls ? (
            <Notice>
              {t("estimatedCost")}
              {total.unpricedCalls ? ` ${t("unknownPriceCount", { count: total.unpricedCalls })}` : ""}
            </Notice>
          ) : null}
          <Meta>
            {t("cacheHitNote")}
          </Meta>
          <Meta>
            {t("cancelledCalls")}
          </Meta>
        </Card>
      ) : null}

      {report ? (
        <>
          <BucketTable title={t("byModel")} keyLabel={t("model")} buckets={report.byModel} />
          <BucketTable title={t("byDay")} keyLabel={t("day")} buckets={report.byDay} />
        </>
      ) : null}
    </>
  );
}
