import type colors from "./themes/colors";
import type fonts from "./themes/fonts";
import type responsive from "./themes/responsive";
import type round from "./themes/round";

export type ColorTheme = typeof colors;
export type FontTheme = typeof fonts;
export type ResponsiveTheme = typeof responsive;
export type RoundTheme = typeof round;

export type Theme = {
  colors: ColorTheme;
  fonts: FontTheme;
  responsive: ResponsiveTheme;
  round: RoundTheme;
};

declare module "styled-components" {
  export interface DefaultTheme extends Theme {}
}
