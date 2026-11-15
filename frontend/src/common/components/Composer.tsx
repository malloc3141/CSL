"use client";

import styled from "styled-components";

const Form = styled.form`
  display: flex;
  gap: 8px;
  align-items: center;
`;

const Input = styled.input`
  flex: 1;
  min-width: 0;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme }) => theme.colors.WHITE};
  color: ${({ theme }) => theme.colors.GRAY[900]};
  padding: 10px 12px;

  &:focus {
    outline: 2px solid ${({ theme }) => theme.colors.SLATE[600]};
    outline-offset: 1px;
  }
`;

const Send = styled.button`
  border: 0;
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme }) => theme.colors.SLATE[600]};
  color: ${({ theme }) => theme.colors.WHITE};
  padding: 10px 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  &:hover:not(:disabled) {
    background: ${({ theme }) => theme.colors.SLATE[700]};
  }
`;

type ComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  disabled?: boolean;
};

export function Composer({
  value,
  onChange,
  onSubmit,
  placeholder = "Join the discussion...",
  disabled = false,
}: ComposerProps) {
  return (
    <Form
      onSubmit={(event) => {
        event.preventDefault();
        if (!disabled && value.trim()) onSubmit();
      }}
    >
      <Input
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        aria-label={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      <Send type="submit" disabled={disabled || !value.trim()}>
        Send
      </Send>
    </Form>
  );
}
