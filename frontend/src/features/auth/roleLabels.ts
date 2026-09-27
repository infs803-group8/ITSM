import type { Role } from "../../api/types";

export const roleLabels: Record<Role, string> = {
  USER: "User", ENGINEER_TIER1: "Tier 1 engineer", ENGINEER_TIER2: "Tier 2 engineer",
  EXTERNAL_VENDOR: "External vendor", SERVICE_DESK_MANAGER: "Service desk manager",
};
export const isEngineer = (role: Role) => role === "ENGINEER_TIER1" || role === "ENGINEER_TIER2";
