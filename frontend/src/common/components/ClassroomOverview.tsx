"use client";

import { useI18n } from "@/i18n";
import type { Language } from "@/lib/csl";
import styled from "styled-components";
import { peerColor } from "@/styles/peerColors";

const Overview = styled.div`
  padding-block: 16px 32px;
`;

const Heading = styled.h2`
  margin: 0 0 12px;
  font-size: 24px;
`;

const Description = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.GRAY[500]};
  font-size: 14px;
  line-height: 1.7;
`;

const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
  margin-top: 40px;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

const Participant = styled.article`
  display: grid;
  grid-template-rows: subgrid;
  grid-row: span 6;
  row-gap: 12px;
  padding: 20px;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.md};
`;

const Badge = styled.h3<{ $peerIndex: number | null }>`
  align-self: start;
  justify-self: start;
  min-width: 100px;
  margin: 0 0 12px;
  padding: 8px 12px;
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme, $peerIndex }) => $peerIndex === null ? theme.colors.BLUE[50] : peerColor(theme, $peerIndex)[50]};
  color: ${({ theme, $peerIndex }) => $peerIndex === null ? theme.colors.BLUE[900] : peerColor(theme, $peerIndex)[900]};
  font-size: 18px;
`;

const Details = styled.dl`
  display: contents;

  dt {
    margin: 0;
    color: ${({ theme }) => theme.colors.GRAY[500]};
    font-size: 12px;
    font-weight: 600;
  }

  dd { margin: 0; font-size: 14px; line-height: 1.6; font-weight: 600; }

  dd + dt {
    margin-top: 12px;
    padding-top: 20px;
    border-top: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  }
`;

const Note = styled(Description)`
  margin: 0;
  padding-top: 16px;
  font-size: 12px;
`;

export type OverviewParticipant = {
  name: string;
  /** 0-based index among the peers (picks the colour); null for the tutor. */
  peerIndex: number | null;
  /** Why this participant exists. */
  basis: string;
  /** Initial understanding (peer) or role (tutor). */
  belief: string;
  note?: string;
};

// Shown when no participants are passed (component demo).
function demoParticipants(t: ReturnType<typeof useI18n>["t"]): OverviewParticipant[] {
  return [
    {
      name: t("peerOne"),
      peerIndex: 0,
      basis: t("peerOneBasis"),
      belief: t("peerOneBelief"),
      note: t("peerOneNote"),
    },
    {
      name: t("peerTwo"),
      peerIndex: 1,
      basis: t("peerTwoBasis"),
      belief: t("peerTwoBelief"),
      note: t("peerTwoNote"),
    },
    {
      name: t("tutor"),
      peerIndex: null,
      basis: t("tutorBasis"),
      belief: t("tutorBelief"),
      note: t("tutorNote"),
    },
  ];
}

export function ClassroomOverview({
  topic,
  participants,
  discussionLanguage,
}: {
  topic: string;
  discussionLanguage?: Language;
  /** The session's participants (snapshot.participants with their initial states). */
  participants?: OverviewParticipant[];
}) {
  const { t } = useI18n();
  const { t: discussionT } = useI18n(discussionLanguage);
  const people = participants ?? demoParticipants(t);
  return (
    <Overview>
      <Heading>{t("overviewReady")}</Heading>
      <Description>
        {t("overviewIntro", { topic, count: people.length })}
      </Description>
      <Grid>
        {people.map((participant) => (
          <Participant key={participant.name}>
            <Badge $peerIndex={participant.peerIndex}>{participant.name}</Badge>
            <Details>
              <dt>{(participant.peerIndex === null ? discussionT : t)("creationBasis")}</dt>
              <dd>{participant.basis}</dd>
              <dt>{(participant.peerIndex === null ? discussionT : t)("initialRole")}</dt>
              <dd>{participant.belief}</dd>
            </Details>
            <Note>{participant.note ?? ""}</Note>
          </Participant>
        ))}
      </Grid>
    </Overview>
  );
}
