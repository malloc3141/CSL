import { createGlobalStyle } from "styled-components";

export const GlobalStyle = createGlobalStyle`
  *, *::before, *::after {
    box-sizing: border-box;
  }

  body {
    background: ${({ theme }) => theme.colors.GRAY[100]};
    color: ${({ theme }) => theme.colors.GRAY[900]};
    font-family: ${({ theme }) => theme.fonts.sans};
    line-height: 1.5;
  }

  button,
  input,
  textarea {
    font: inherit;
  }
`;
