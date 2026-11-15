"use client";

// Layout pieces and formatters shared by the admin tabs.

import { useCallback, useEffect, useState } from "react";
import styled from "styled-components";

export const Card = styled.section`
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 20px;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.md};
  background: ${({ theme }) => theme.colors.WHITE};
`;

export const Row = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
`;

export const Grid = styled.div<{ $min?: number }>`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(${({ $min }) => $min ?? 160}px, 1fr));
  gap: 12px;
`;

export const Heading = styled.h2`
  margin: 0;
  font-size: 15px;
`;

export const Meta = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.GRAY[500]};
  font-size: 13px;
`;

export const ErrorText = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.ROSE[900]};
  font-size: 13px;
`;

export const Notice = styled.p<{ $tone?: "warn" | "ok" }>`
  margin: 0;
  padding: 10px 12px;
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme, $tone }) => ($tone === "ok" ? theme.colors.GREEN[50] : theme.colors.YELLOW[50])};
  color: ${({ theme, $tone }) => ($tone === "ok" ? theme.colors.GREEN[900] : theme.colors.YELLOW[900])};
  font-size: 13px;
`;

export const Input = styled.input`
  min-width: 0;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme }) => theme.colors.WHITE};
  color: ${({ theme }) => theme.colors.GRAY[900]};
  padding: 9px 12px;
  font: inherit;
  font-size: 14px;

  &:focus {
    outline: 2px solid ${({ theme }) => theme.colors.SLATE[600]};
    outline-offset: 1px;
  }
`;

export const Label = styled.label`
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
`;

export const TableWrap = styled.div`
  overflow-x: auto;
`;

export const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;

  th,
  td {
    padding: 7px 10px;
    border-bottom: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
    text-align: left;
    vertical-align: top;
    white-space: nowrap;
  }
  th {
    color: ${({ theme }) => theme.colors.GRAY[500]};
    font-weight: 600;
  }
  td.num,
  th.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  td.wrap {
    white-space: normal;
    word-break: break-word;
  }
  tbody tr.clickable {
    cursor: pointer;
  }
  tbody tr.clickable:hover,
  tbody tr.selected {
    background: ${({ theme }) => theme.colors.GRAY[100]};
  }
`;

const StatBox = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme }) => theme.colors.GRAY[100]};

  strong {
    font-size: 20px;
    font-variant-numeric: tabular-nums;
  }
  span {
    color: ${({ theme }) => theme.colors.GRAY[500]};
    font-size: 12px;
  }
`;

export function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <StatBox>
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <span>{hint}</span> : null}
    </StatBox>
  );
}

export const Pre = styled.pre`
  margin: 0;
  max-height: 420px;
  overflow: auto;
  padding: 12px;
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme }) => theme.colors.GRAY[100]};
  font-family: var(--font-geist-mono), monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
`;

export function usd(value: number | null | undefined, estimated = false): string {
  if (value == null) return "–";
  const digits = value !== 0 && Math.abs(value) < 0.01 ? 4 : 2;
  return `${estimated ? "≈" : ""}$${value.toFixed(digits)}`;
}

export function int(value: number): string {
  return value.toLocaleString("en-US");
}

/** A ratio (0–1) as a percentage; "–" when there is nothing to divide by. */
export function percent(value: number | null | undefined): string {
  return value == null ? "–" : `${(value * 100).toFixed(1)}%`;
}

/** USD per million tokens. */
export function price(value: number): string {
  return value === 0 ? "–" : `$${value < 0.1 ? value.toFixed(3) : value.toFixed(2)}`;
}

export function dateTime(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString("en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function errorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

/**
 * Load data when `fetcher` changes (memoize it with useCallback) and on reload().
 * State is only set from the promise callbacks, never synchronously inside the effect.
 */
export function useAdminLoad<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    fetcher().then(
      (value) => {
        if (!alive) return;
        setData(value);
        setError(null);
        setLoading(false);
      },
      (cause) => {
        if (!alive) return;
        setError(errorMessage(cause));
        setLoading(false);
      },
    );
    return () => {
      alive = false;
    };
  }, [fetcher, nonce]);

  const reload = useCallback(() => {
    setLoading(true);
    setNonce((n) => n + 1);
  }, []);

  return { data, error, loading, reload };
}
