"use client";

import { useState } from "react";
import { useServerInsertedHTML } from "next/navigation";
import {
  ServerStyleSheet,
  StyleSheetManager,
  ThemeProvider,
} from "styled-components";
import { GlobalStyle } from "@/styles/global";
import colors from "@/styles/themes/colors";
import fonts from "@/styles/themes/fonts";
import responsive from "@/styles/themes/responsive";
import round from "@/styles/themes/round";

const theme = { colors, fonts, responsive, round };

export function Providers({ children }: { children: React.ReactNode }) {
  const [styledComponentsStyleSheet] = useState(() => new ServerStyleSheet());

  useServerInsertedHTML(() => {
    const styles = styledComponentsStyleSheet.getStyleElement();
    styledComponentsStyleSheet.instance.clearTag();
    return <>{styles}</>;
  });

  const tree = (
    <ThemeProvider theme={theme}>
      <GlobalStyle />
      {children}
    </ThemeProvider>
  );

  if (typeof window !== "undefined") {
    return tree;
  }

  return (
    <StyleSheetManager sheet={styledComponentsStyleSheet.instance}>
      {tree}
    </StyleSheetManager>
  );
}
