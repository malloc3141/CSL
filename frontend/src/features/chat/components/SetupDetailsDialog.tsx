import { useId } from "react";
import type { Ref } from "react";
import { X } from "lucide-react";
import styled from "styled-components";
import { Button } from "@/common/components";
import { useI18n } from "@/i18n";
import type { SessionSnapshot } from "@/lib/csl";

const Dialog = styled.dialog`
  box-sizing: border-box;
  width: min(560px, calc(100% - 32px));
  max-height: calc(100dvh - 32px);
  overscroll-behavior: contain;
  padding: 24px;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.md};
  background: ${({ theme }) => theme.colors.WHITE};
  color: ${({ theme }) => theme.colors.GRAY[900]};

  &::backdrop { background: rgb(0 0 0 / 40%); }
  header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  h2 { margin: 0; font-size: 18px; }
  dl { margin: 16px 0; }
  dt, summary { font-weight: 600; }
  dd { margin: 4px 0 12px; }
  summary { cursor: pointer; }
  ol { padding-inline-start: 24px; }
  li + li { margin-top: 12px; }
  p { margin: 4px 0 0; white-space: pre-wrap; }
  dd, p { overflow-wrap: anywhere; }
`;

const CloseButton = styled(Button)`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
`;

type SetupDetailsDialogProps = {
  dialogRef: Ref<HTMLDialogElement>;
  snapshot: SessionSnapshot;
};

export function SetupDetailsDialog({ dialogRef, snapshot }: SetupDetailsDialogProps) {
  const { t } = useI18n();
  const titleId = useId();
  const topic = snapshot.topic || t("defaultTopic");
  const messages = snapshot.messages.filter((message) => message.channel === "init");

  return (
    <Dialog ref={dialogRef} aria-labelledby={titleId}>
      <header>
        <h2 id={titleId}>{t("setupDetails")}</h2>
        <form method="dialog">
          <CloseButton type="submit" variant="ghost" aria-label={t("closeSetupDetails")}>
            <X size={18} aria-hidden="true" />
          </CloseButton>
        </form>
      </header>
      <dl>
        <dt>{t("topic")}</dt>
        <dd>{topic}</dd>
        <dt>{t("learningDirection")}</dt>
        <dd>{snapshot.focus ?? t("defaultDirection", { topic })}</dd>
      </dl>
      {messages.length > 0 && (
        <details>
          <summary>{t("setupChat")}</summary>
          <ol>
            {messages.map((message) => (
              <li key={message.id}>
                <strong>{message.role === "user" ? t("you") : message.speakerName}</strong>
                <p>{message.text}</p>
              </li>
            ))}
          </ol>
        </details>
      )}
    </Dialog>
  );
}
