"use client";

import styled from "styled-components";

const List = styled.ol`
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const Item = styled.li<{ $current: boolean }>`
  color: ${({ theme }) => theme.colors.GRAY[900]};
  font-size: 13px;
  font-weight: ${({ $current }) => ($current ? 700 : 500)};
`;

type StepperProps = {
  steps: string[];
  current: number;
};

export function Stepper({ steps, current }: StepperProps) {
  return (
    <List>
      {steps.map((step, index) => (
        <Item key={step} $current={index === current} aria-current={index === current ? "step" : undefined}>
          {index + 1} {step}
        </Item>
      ))}
    </List>
  );
}
