import styled from "styled-components";

export const ChatCheckbox = styled.label`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: ${({ theme }) => theme.colors.GRAY[900]};
  font-size: 13px;
  cursor: pointer;
  input { margin: 0; }
`;

export const ChatEmptyState = styled.p`
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: ${({ theme }) => theme.colors.SLATE[600]};
`;

