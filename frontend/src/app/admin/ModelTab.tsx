"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/common/components";
import { adminApi } from "@/lib/csl";
import type { ModelConfig, ModelInfo } from "@/lib/csl";
import { Card, ErrorText, Heading, Input, Label, Meta, Notice, Row, Table, TableWrap, errorMessage, price } from "./ui";

function PriceLine({ id, models }: { id: string; models: Map<string, ModelInfo> }) {
  if (!id) return null;
  const info = models.get(id);
  if (!info) {
    return models.size ? <ErrorText>OpenRouter 모델 목록에 없는 ID입니다.</ErrorText> : null;
  }
  return (
    <Meta>
      {info.name} · 100만 토큰당 입력 {price(info.promptPrice)} / 출력 {price(info.completionPrice)}
      {info.contextLength ? ` · 컨텍스트 ${info.contextLength.toLocaleString("en-US")}` : ""}
    </Meta>
  );
}

export function ModelTab({
  token,
  config,
  onChange,
}: {
  token: string;
  config: ModelConfig;
  onChange: (config: ModelConfig) => void;
}) {
  const [model, setModel] = useState(config.model);
  const [modelFast, setModelFast] = useState(config.modelFast);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    adminApi
      .models(token)
      .then(setModels)
      .catch((cause) => setListError(errorMessage(cause)));
  }, [token]);

  const byId = useMemo(() => new Map(models.map((m) => [m.id, m])), [models]);
  const filtered = useMemo(() => {
    const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    return models.filter((m) => words.every((w) => `${m.id} ${m.name}`.toLowerCase().includes(w))).slice(0, 40);
  }, [filter, models]);

  const save = async (update: { model: string; modelFast: string }) => {
    setSaving(true);
    setResult(null);
    try {
      const next = await adminApi.updateConfig(token, update);
      onChange(next);
      setModel(next.model);
      setModelFast(next.modelFast);
      setResult({ ok: true, text: "저장했습니다. 다음 LLM 호출부터 새 모델을 씁니다 (진행 중인 호출은 그대로)." });
    } catch (cause) {
      setResult({ ok: false, text: errorMessage(cause) });
    } finally {
      setSaving(false);
    }
  };

  const changed = model.trim() !== config.model || modelFast.trim() !== config.modelFast;

  return (
    <>
      <Card>
        <Heading>사용 중인 모델</Heading>
        {config.pipeline !== "baseline" ? (
          <Notice>
            현재 파이프라인은 <b>{config.pipeline}</b>입니다.
            {config.pipeline === "mock"
              ? " mock은 LLM을 호출하지 않으므로 여기서 바꾼 모델이 쓰이지 않습니다. backend/.env의 PIPELINE을 바꾸고 재시작해야 합니다."
              : " 이 파이프라인이 app/llm.py의 get_llm()을 쓰는 경우에만 아래 설정이 적용됩니다."}
          </Notice>
        ) : null}
        {!config.apiKeySet ? <Notice>서버에 OPENROUTER_API_KEY가 설정되어 있지 않습니다.</Notice> : null}

        <datalist id="openrouter-models">
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </datalist>

        <Label htmlFor="model">
          메인 모델 (발언 생성)
          <Input
            id="model"
            list="openrouter-models"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder={config.defaultModel || "예: anthropic/claude-sonnet-5.5"}
            autoComplete="off"
            spellCheck={false}
          />
        </Label>
        <PriceLine id={model.trim()} models={byId} />
        <Meta>.env 기본값: {config.defaultModel || "(없음)"} · 비우고 저장하면 기본값으로 돌아갑니다.</Meta>

        <Label htmlFor="model-fast">
          보조 모델 (발언자 선택, 지식 상태 업데이트)
          <Input
            id="model-fast"
            list="openrouter-models"
            value={modelFast}
            onChange={(event) => setModelFast(event.target.value)}
            placeholder={config.defaultModelFast || "비우면 메인 모델 사용"}
            autoComplete="off"
            spellCheck={false}
          />
        </Label>
        <PriceLine id={modelFast.trim()} models={byId} />
        <Meta>
          .env 기본값: {config.defaultModelFast || "(없음: 메인 모델 사용)"}
          {!modelFast.trim() && !config.defaultModelFast ? " · 지금은 보조 호출도 메인 모델로 나갑니다." : ""}
        </Meta>

        <Row>
          <Button onClick={() => save({ model: model.trim(), modelFast: modelFast.trim() })} disabled={saving || !changed}>
            {saving ? "저장 중…" : "저장"}
          </Button>
          <Button
            variant="ghost"
            onClick={() => save({ model: "", modelFast: "" })}
            disabled={saving || !config.overridden}
          >
            .env 값으로 되돌리기
          </Button>
          <Meta>{config.overridden ? "관리자 페이지에서 바꾼 값이 적용 중입니다 (재시작해도 유지)." : ".env 값 사용 중"}</Meta>
        </Row>
        {result ? <Notice $tone={result.ok ? "ok" : "warn"}>{result.text}</Notice> : null}
      </Card>

      <Card>
        <Heading>OpenRouter 모델 찾기</Heading>
        {listError ? <ErrorText>모델 목록을 불러오지 못했습니다: {listError}</ErrorText> : null}
        <Input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="검색어 (예: claude haiku, gpt luna, gemini flash)"
          aria-label="모델 검색"
        />
        {filtered.length ? (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <th>모델</th>
                  <th className="num">입력 /1M</th>
                  <th className="num">출력 /1M</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.map((m) => (
                  <tr key={m.id}>
                    <td className="wrap">
                      {m.id}
                      <Meta>{m.name}</Meta>
                    </td>
                    <td className="num">{price(m.promptPrice)}</td>
                    <td className="num">{price(m.completionPrice)}</td>
                    <td>
                      <Row>
                        <Button variant="ghost" onClick={() => setModel(m.id)}>
                          메인으로
                        </Button>
                        <Button variant="ghost" onClick={() => setModelFast(m.id)}>
                          보조로
                        </Button>
                      </Row>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <Meta>{models.length ? `${models.length}개 모델. 검색어를 입력하세요.` : "목록을 불러오는 중…"}</Meta>
        )}
      </Card>
    </>
  );
}
