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
    return models.size ? <ErrorText>Not in the OpenRouter model list.</ErrorText> : null;
  }
  return (
    <Meta>
      {info.name} · per 1M tokens: input {price(info.promptPrice)} / output {price(info.completionPrice)}
      {info.contextLength ? ` · context ${info.contextLength.toLocaleString("en-US")}` : ""}
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
      setResult({ ok: true, text: "Saved. The next LLM call uses the new model (calls in flight are not affected)." });
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
        <Heading>Models in use</Heading>
        {config.pipeline !== "baseline" ? (
          <Notice>
            The current pipeline is <b>{config.pipeline}</b>.
            {config.pipeline === "mock"
              ? " The mock pipeline makes no LLM calls, so the models set here are not used. Change PIPELINE in backend/.env and restart the backend."
              : " The settings below apply only if this pipeline uses get_llm() from app/llm.py."}
          </Notice>
        ) : null}
        {!config.apiKeySet ? <Notice>OPENROUTER_API_KEY is not set on the server.</Notice> : null}

        <datalist id="openrouter-models">
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </datalist>

        <Label htmlFor="model">
          Main model (writes the messages)
          <Input
            id="model"
            list="openrouter-models"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder={config.defaultModel || "e.g. anthropic/claude-sonnet-5.5"}
            autoComplete="off"
            spellCheck={false}
          />
        </Label>
        <PriceLine id={model.trim()} models={byId} />
        <Meta>.env default: {config.defaultModel || "(none)"} · Save it empty to go back to the default.</Meta>

        <Label htmlFor="model-fast">
          Fast model (picks the speaker, updates knowledge states)
          <Input
            id="model-fast"
            list="openrouter-models"
            value={modelFast}
            onChange={(event) => setModelFast(event.target.value)}
            placeholder={config.defaultModelFast || "Empty = use the main model"}
            autoComplete="off"
            spellCheck={false}
          />
        </Label>
        <PriceLine id={modelFast.trim()} models={byId} />
        <Meta>
          .env default: {config.defaultModelFast || "(none: uses the main model)"}
          {!modelFast.trim() && !config.defaultModelFast ? " · Fast calls currently go to the main model." : ""}
        </Meta>

        <Row>
          <Button onClick={() => save({ model: model.trim(), modelFast: modelFast.trim() })} disabled={saving || !changed}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button
            variant="ghost"
            onClick={() => save({ model: "", modelFast: "" })}
            disabled={saving || !config.overridden}
          >
            Reset to .env
          </Button>
          <Meta>{config.overridden ? "Override from the admin page is active (kept across restarts)." : "Using the .env values"}</Meta>
        </Row>
        {result ? <Notice $tone={result.ok ? "ok" : "warn"}>{result.text}</Notice> : null}
      </Card>

      <Card>
        <Heading>Find an OpenRouter model</Heading>
        {listError ? <ErrorText>Could not load the model list: {listError}</ErrorText> : null}
        <Input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Search (e.g. claude haiku, gpt luna, gemini flash)"
          aria-label="Search models"
        />
        {filtered.length ? (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th className="num">Input /1M</th>
                  <th className="num">Output /1M</th>
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
                          Use as main
                        </Button>
                        <Button variant="ghost" onClick={() => setModelFast(m.id)}>
                          Use as fast
                        </Button>
                      </Row>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <Meta>{models.length ? `${models.length} models. Type to search.` : "Loading the list…"}</Meta>
        )}
      </Card>
    </>
  );
}
