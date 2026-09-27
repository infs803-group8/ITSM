import type { Rule } from "antd/es/form";

export const displayNameRules: Rule[] = [
  { required: true, whitespace: true, message: "Enter your display name." },
  { max: 100, message: "Use 100 characters or fewer." },
];
export const emailRules: Rule[] = [
  { required: true, whitespace: true, message: "Enter your email address." },
  { type: "email", transform: (value: string) => value?.trim(), message: "Enter a valid email address." },
  { max: 254, message: "Use 254 characters or fewer." },
];
export const passwordRules: Rule[] = [
  { required: true, message: "Enter your password." },
  { min: 8, max: 128, message: "Use between 8 and 128 characters." },
];
