"use client";

import styled from "styled-components";

const Field = styled.label`
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: ${({ theme }) => theme.colors.GRAY[900]};
  font-size: 14px;
  font-weight: 600;
`;

const Input = styled.input`
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme }) => theme.colors.WHITE};
  color: ${({ theme }) => theme.colors.GRAY[900]};
  padding: 10px 12px;
  font-weight: 400;

  &:focus {
    outline: 2px solid ${({ theme }) => theme.colors.SLATE[600]};
    outline-offset: 1px;
  }
`;

type TextFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

export function TextField({ id, label, value, onChange, placeholder }: TextFieldProps) {
  return (
    <Field htmlFor={id}>
      {label}
      <Input
        id={id}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}
