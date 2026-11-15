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
        <Meta>기록된 LLM 호출이 없습니다.</Meta>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <th>{keyLabel}</th>
                <th className="num">호출</th>
                <th className="num">오류</th>
                <th className="num">입력 토큰</th>
                <th className="num">출력 토큰</th>
                <th className="num">추론 토큰</th>
                <th className="num">평균 지연</th>
                <th className="num">비용</th>
              </tr>
            </thead>
            <tbody>
              {buckets.map((b) => (
                <tr key={b.key}>
                  <td>{b.key}</td>
                  <td className="num">{int(b.calls)}</td>
                  <td className="num">{b.errors ? int(b.errors) : "–"}</td>
                  <td className="num">{int(b.promptTokens)}</td>
                  <td className="num">{int(b.completionTokens)}</td>
                  <td className="num">{b.reasoningTokens ? int(b.reasoningTokens) : "–"}</td>
                  <td className="num">{b.avgSeconds.toFixed(1)}s</td>
                  <td className="num">
                    {usd(b.cost, b.estimated)}
                    {b.unpricedCalls ? ` (+${b.unpricedCalls} 미산정)` : ""}
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
          {loading ? "불러오는 중…" : "새로고침"}
        </Button>
        {error ? <ErrorText>{error}</ErrorText> : null}
      </Row>

      <Card>
        <Heading>OpenRouter 키 사용량 (실제 청구 기준)</Heading>
        {!apiKeySet ? (
          <Meta>서버에 OPENROUTER_API_KEY가 설정되어 있지 않습니다.</Meta>
        ) : report?.openrouterError ? (
          <ErrorText>OpenRouter에서 키 정보를 받지 못했습니다: {report.openrouterError}</ErrorText>
        ) : key ? (
          <>
            <Grid>
              <Stat label="누적 사용" value={usd(key.usage)} hint={key.label ?? undefined} />
              <Stat label="오늘" value={usd(key.usageDaily)} />
              <Stat label="이번 주" value={usd(key.usageWeekly)} />
              <Stat label="이번 달" value={usd(key.usageMonthly)} />
              <Stat
                label="키 한도 / 남은 금액"
                value={key.limit == null ? "한도 없음" : usd(key.limitRemaining)}
                hint={key.limit == null ? "OpenRouter에서 키별 한도를 걸 수 있습니다" : `한도 ${usd(key.limit)}`}
              />
            </Grid>
            {key.limit ? <Bar $ratio={key.usage / key.limit} /> : null}
            <Meta>OpenRouter 기준 집계라 이 키를 다른 곳에서 쓴 비용도 포함되고, 몇 분 늦게 반영될 수 있습니다.</Meta>
          </>
        ) : (
          <Meta>불러오는 중…</Meta>
        )}
      </Card>

      {total ? (
        <Card>
          <Heading>이 서버의 LLM 호출 (이벤트 로그 기준)</Heading>
          <Grid>
            <Stat label="호출" value={int(total.calls)} hint={total.errors ? `오류 ${int(total.errors)}` : undefined} />
            <Stat label="입력 토큰" value={int(total.promptTokens)} />
            <Stat
              label="출력 토큰"
              value={int(total.completionTokens)}
              hint={total.reasoningTokens ? `추론 ${int(total.reasoningTokens)} 포함` : undefined}
            />
            <Stat label="비용" value={usd(total.cost, total.estimated)} />
            <Stat
              label="LLM 세션당 평균"
              value={perSession == null ? "–" : usd(perSession, total.estimated)}
              hint={`${withLlm.length}개 세션`}
            />
            <Stat label="평균 지연" value={`${total.avgSeconds.toFixed(1)}s`} />
          </Grid>
          {total.estimated || total.unpricedCalls ? (
            <Notice>
              ≈ 표시는 OpenRouter가 비용을 보고하지 않은 호출을 모델 정가로 추정한 값입니다.
              {total.unpricedCalls ? ` 가격을 알 수 없는 호출 ${total.unpricedCalls}건은 빠져 있습니다.` : ""}
            </Notice>
          ) : null}
          <Meta>
            중간에 취소된 발언(학습자가 끼어들어 버려진 선생성 턴)은 토큰이 기록되지 않아 여기서는 빠집니다. 정확한
            금액은 위의 OpenRouter 키 사용량을 보세요.
          </Meta>
        </Card>
      ) : null}

      {report ? (
        <>
          <BucketTable title="모델별" keyLabel="모델" buckets={report.byModel} />
          <BucketTable title="날짜별" keyLabel="날짜" buckets={report.byDay} />
        </>
      ) : null}
    </>
  );
}
