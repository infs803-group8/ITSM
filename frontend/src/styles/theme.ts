import type { ThemeConfig } from "antd";

export const helpdeskTheme: ThemeConfig = {
  token: {
    colorPrimary: "#f4c400", colorText: "#1d2227", colorTextSecondary: "#606a73",
    colorBorder: "#bac1c6", colorError: "#b42318", colorSuccess: "#26734a",
    fontFamily: '"Segoe UI", Arial, sans-serif', fontSize: 14, borderRadius: 3,
    controlHeight: 44, motion: false,
  },
  components: {
    Button: { primaryColor: "#1d2227", primaryShadow: "none", defaultShadow: "none", fontWeight: 600 },
    Input: { activeBorderColor: "#8c7100", hoverBorderColor: "#8c7100", activeShadow: "0 0 0 2px rgb(244 196 0 / 15%)" },
  },
};
