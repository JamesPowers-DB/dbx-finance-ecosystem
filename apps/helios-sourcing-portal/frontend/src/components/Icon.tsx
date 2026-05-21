import React from "react";

export type IconName =
  | "home" | "landscape" | "contracts" | "suppliers" | "savings"
  | "bot" | "monitor" | "search" | "bell" | "arrow" | "arrow-right"
  | "chev_r" | "chev_d" | "chev_l" | "plus" | "check" | "x"
  | "filter" | "download" | "upload" | "send" | "warn" | "star"
  | "cal" | "table" | "lightning" | "cog" | "link" | "refresh"
  | "data" | "user" | "shield" | "doc" | "build" | "sliders"
  | "book" | "question" | "external" | "package" | "spark";

const ICON_PATHS: Record<IconName, string> = {
  home:       "M3 9l9-7 9 7v11a2 2 0 0 1-2 2h-4v-7H10v7H6a2 2 0 0 1-2-2V9z",
  landscape:  "M3 18l6-8 4 5 3-4 5 7M3 21h18",
  contracts:  "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m-6 9h6m-6 4h6m-6-8h6",
  suppliers:  "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm14 10v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  savings:    "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
  bot:        "M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h3a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3v-7a3 3 0 0 1 3-3h3V5.73A2 2 0 0 1 10 4a2 2 0 0 1 2-2zM9 12a1 1 0 1 0 0 2 1 1 0 0 0 0-2zm6 0a1 1 0 1 0 0 2 1 1 0 0 0 0-2z",
  monitor:    "M2 3h20a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm10 18v-3m-4 3h8",
  search:     "M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z",
  bell:       "M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0",
  arrow:      "M5 12h14M12 5l7 7-7 7",
  "arrow-right": "M5 12h14M12 5l7 7-7 7",
  chev_r:     "M9 18l6-6-6-6",
  chev_d:     "M6 9l6 6 6-6",
  chev_l:     "M15 18l-6-6 6-6",
  plus:       "M12 5v14M5 12h14",
  check:      "M20 6L9 17l-5-5",
  x:          "M18 6L6 18M6 6l12 12",
  filter:     "M22 3H2l8 9.46V19l4 2v-8.54L22 3z",
  download:   "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  upload:     "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  send:       "M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z",
  warn:       "M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4m0 4h.01",
  star:       "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z",
  cal:        "M3 4h18v18H3V4zm0 7h18M8 2v4m8-4v4",
  table:      "M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18",
  lightning:  "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
  cog:        "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm8.73-6a9.05 9.05 0 0 0-.14-1.49l2.12-1.65-2-3.46-2.5.96A9 9 0 0 0 15 2.69L14.58 0h-4L10 2.69A9 9 0 0 0 6.79 4.36l-2.5-.96-2 3.46 2.12 1.65A9.05 9.05 0 0 0 4.27 9c0 .5.04 1 .14 1.49L2.29 12.14l2 3.46 2.5-.96A9 9 0 0 0 10 16.31l.42 2.69h4l.42-2.69a9 9 0 0 0 3.21-1.67l2.5.96 2-3.46-2.12-1.65c.1-.49.14-.99.14-1.49z",
  link:       "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
  refresh:    "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
  data:       "M3 3h18v18H3V3zm9 4v10M7 12h10",
  user:       "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  shield:     "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  doc:        "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11z",
  build:      "M2 20h20M17 20V8l-5-6-5 6v12m4-6h2",
  sliders:    "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
  book:       "M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 19.5A2.5 2.5 0 0 0 6.5 22H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15z",
  question:   "M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01",
  external:   "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3",
  package:    "M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16zM3.27 6.96L12 12.01l8.73-5.05M12 22.08V12",
  spark:      "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
};

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
  stroke?: number;
  style?: React.CSSProperties;
}

export function Icon({ name, size = 16, color = "currentColor", stroke = 1.6, style }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0, ...style }}
    >
      <path d={ICON_PATHS[name] ?? ICON_PATHS.home} />
    </svg>
  );
}
