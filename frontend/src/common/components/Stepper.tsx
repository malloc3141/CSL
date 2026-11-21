"use client";

import { useI18n } from "@/i18n";
import styled from "styled-components";

const List = styled.ol<{ $count: number }>`
  display: grid;
  grid-template-columns: repeat(${({ $count }) => Math.max(1, $count)}, minmax(0, 1fr));
  gap: 18px;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const Item = styled.li`
  min-width: 0;
`;

const StepButton = styled.button<{ $current: boolean; $complete: boolean }>`
  display: block;
  width: 100%;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  font-family: inherit;
  cursor: pointer;

  &:disabled {
    cursor: default;
  }
  color: ${({ theme }) => theme.colors.SLATE[600]};
  font-size: 13px;
  font-weight: ${({ $current }) => ($current ? 700 : 500)};

  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.colors.SLATE[600]};
    outline-offset: 4px;
  }

  &::before {
    content: "";
    display: block;
    height: 4px;
    margin-bottom: 6px;
    border-radius: 2px;
    background: ${({ theme, $current, $complete }) =>
      $current || $complete ? "#7393bd" : theme.colors.GRAY[200]};
  }
`;

type StepperProps = {
  steps: string[];
  current: number;
  onStepClick?: (index: number) => void;
};

export function Stepper({ steps, current, onStepClick }: StepperProps) {
  const { t } = useI18n();
  return (
    <List $count={steps.length} aria-label={t("setupProgress")}>
      {steps.map((step, index) => (
        <Item key={step}>
          <StepButton
            type="button"
            $current={index === current}
            $complete={index < current}
            disabled={index >= current || !onStepClick}
            aria-current={index === current ? "step" : undefined}
            onClick={() => onStepClick?.(index)}
          >
            {index + 1} {step}
          </StepButton>
        </Item>
      ))}
    </List>
  );
}
