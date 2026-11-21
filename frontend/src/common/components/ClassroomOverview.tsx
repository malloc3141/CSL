"use client";

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
const PARTICIPANTS: OverviewParticipant[] = [
  {
    name: "Peer 1",
    peerIndex: 0,
    basis: "A common misconception about the topic",
    belief: "“Could a simple, everyday explanation account for this?”",
    note: "Brings an intuitive perspective for the classroom to examine.",
  },
  {
    name: "Peer 2",
    peerIndex: 1,
    basis: "An alternative hypothesis to explore",
    belief: "“What if another factor is responsible?”",
    note: "Offers a different explanation to compare with your own ideas.",
  },
  {
    name: "Tutor",
    peerIndex: null,
    basis: "Discussion guidance and explanation checking",
    belief: "“What evidence would help us test these explanations?”",
    note: "Helps compare assumptions and evidence to build understanding.",
  },
];

export function ClassroomOverview({
  topic,
  participants = PARTICIPANTS,
}: {
  topic: string;
  /** The session's participants (snapshot.participants with their initial states). */
  participants?: OverviewParticipant[];
}) {
  return (
    <Overview>
      <Heading>Your classroom is ready!</Heading>
      <Description>
        Meet the participants who will help you explore {topic} from {participants.length === 3 ? "three" : participants.length} perspectives.
        The peers are learners like you, so what they say can be wrong. The tutor guides the discussion and will
        ask you to explain your own understanding; it does not have to be complete or correct.
      </Description>
      <Grid>
        {participants.map((participant) => (
          <Participant key={participant.name}>
            <Badge $peerIndex={participant.peerIndex}>{participant.name}</Badge>
            <Details>
              <dt>Creation basis</dt>
              <dd>{participant.basis}</dd>
              <dt>Initial understanding / role</dt>
              <dd>{participant.belief}</dd>
            </Details>
            <Note>{participant.note ?? ""}</Note>
          </Participant>
        ))}
      </Grid>
    </Overview>
  );
}
