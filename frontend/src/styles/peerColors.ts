import type { DefaultTheme } from "styled-components";

const PEER_COLOR_KEYS = ["PURPLE", "ORANGE", "YELLOW", "ROSE"] as const;

export function peerColor(theme: DefaultTheme, index: number) {
  const key = PEER_COLOR_KEYS[index % PEER_COLOR_KEYS.length];
  return theme.colors[key];
}
