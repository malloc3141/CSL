"use client";

import { useI18n } from "@/i18n";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/common/components";
import { adminApi } from "@/lib/csl";
import type { ModelConfig, ModelInfo } from "@/lib/csl";
import { Card, ErrorText, Heading, Input, Label, Meta, Notice, Row, Table, TableWrap, errorMessage, price } from "./ui";

function PriceLine({ id, models }: { id: string; models: Map<string, ModelInfo> }) {
  const { t } = useI18n();
  if (!id) return null;
  const info = models.get(id);
  if (!info) {
    return models.size ? <ErrorText>{t("notInModelList")}</ErrorText> : null;
  }
  return (
    <Meta>
      {info.name} {t("tokenPrice", { input: price(info.promptPrice), output: price(info.completionPrice) })}
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
  const { t } = useI18n();
  const [model, setModel] = useState(config.model);
  const [modelFast, setModelFast] = useState(config.modelFast);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<{ ok: true } | { ok: false; text: string } | null>(null);
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
      setResult({ ok: true });
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
        <Heading>{t("modelsInUse")}</Heading>
        {config.pipeline !== "baseline" ? (
          <Notice>
            {t("currentPipeline", { pipeline: config.pipeline })}
            {config.pipeline === "mock"
              ? t("mockModels")
              : t("customModels")}
          </Notice>
        ) : null}
        {!config.apiKeySet ? <Notice>{t("noApiKey")}</Notice> : null}

        <datalist id="openrouter-models">
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </datalist>

        <Label htmlFor="model">
          {t("mainModel")}
          <Input
            id="model"
            list="openrouter-models"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder={config.defaultModel || t("modelExample")}
            autoComplete="off"
            spellCheck={false}
          />
        </Label>
        <PriceLine id={model.trim()} models={byId} />
        <Meta>{t("envDefault")} {config.defaultModel || t("none")} {t("emptyResets")}</Meta>

        <Label htmlFor="model-fast">
          {t("fastModel")}
          <Input
            id="model-fast"
            list="openrouter-models"
            value={modelFast}
            onChange={(event) => setModelFast(event.target.value)}
            placeholder={config.defaultModelFast || t("emptyMain")}
            autoComplete="off"
            spellCheck={false}
          />
        </Label>
        <PriceLine id={modelFast.trim()} models={byId} />
        <Meta>
          {t("envDefault")} {config.defaultModelFast || t("noneUsesMain")}
          {!modelFast.trim() && !config.defaultModelFast ? t("fastUsesMain") : ""}
        </Meta>

        <Row>
          <Button onClick={() => save({ model: model.trim(), modelFast: modelFast.trim() })} disabled={saving || !changed}>
            {saving ? t("saving") : t("save")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => save({ model: "", modelFast: "" })}
            disabled={saving || !config.overridden}
          >
            {t("resetEnv")}
          </Button>
          <Meta>{config.overridden ? t("overrideActive") : t("usingEnv")}</Meta>
        </Row>
        {result ? <Notice $tone={result.ok ? "ok" : "warn"}>{result.ok ? t("savedModel") : result.text}</Notice> : null}
      </Card>

      <Card>
        <Heading>{t("findModel")}</Heading>
        {listError ? <ErrorText>{t("modelListError")} {listError}</ErrorText> : null}
        <Input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder={t("searchExample")}
          aria-label={t("searchModels")}
        />
        {filtered.length ? (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <th>{t("model")}</th>
                  <th className="num">{t("inputPerMillion")}</th>
                  <th className="num">{t("outputPerMillion")}</th>
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
                          {t("useAsMain")}
                        </Button>
                        <Button variant="ghost" onClick={() => setModelFast(m.id)}>
                          {t("useAsFast")}
                        </Button>
                      </Row>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <Meta>{models.length ? t("modelsCount", { count: models.length }) : t("loadingList")}</Meta>
        )}
      </Card>
    </>
  );
}
