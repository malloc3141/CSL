"use client";

import styled, { css } from "styled-components";
import Link from "next/link";
import type { ComponentProps } from "react";

type ButtonVariant = "primary" | "ghost";

const StyledButton = styled.button<{ $variant: ButtonVariant }>`
  border: 1px solid transparent;
  border-radius: ${({ theme }) => theme.round.sm};
  padding: 8px 14px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  cursor: pointer;
  text-decoration: none;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  ${({ theme, $variant }) =>
    $variant === "primary"
      ? css`
          background: ${theme.colors.SLATE[600]};
          color: ${theme.colors.WHITE};

          &:hover:not(:disabled) {
            background: ${theme.colors.SLATE[700]};
          }
        `
      : css`
          background: ${theme.colors.WHITE};
          color: ${theme.colors.GRAY[900]};
          border-color: ${theme.colors.GRAY[200]};

          &:hover:not(:disabled) {
            background: ${theme.colors.GRAY[100]};
          }
        `}
`;

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
};

export function Button({ variant = "primary", type = "button", ...props }: ButtonProps) {
  return <StyledButton $variant={variant} type={type} {...props} />;
}

const StyledButtonLink = styled(StyledButton)`
  display: inline-block;
`;

type ButtonLinkProps = Omit<ComponentProps<typeof Link>, "as"> & { variant?: ButtonVariant };

export function ButtonLink({ variant = "primary", ...props }: ButtonLinkProps) {
  return <StyledButtonLink as={Link} $variant={variant} {...props} />;
}
