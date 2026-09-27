import { EyeInvisibleOutlined, EyeOutlined } from "@ant-design/icons";
import { Input, type InputProps } from "antd";
import { useState } from "react";

export function PasswordInput(props: InputProps) {
  const [visible, setVisible] = useState(false);
  return <Input {...props} type={visible ? "text" : "password"} suffix={
    <button type="button" className="password-toggle" aria-label={visible ? "Hide password" : "Show password"}
      aria-pressed={visible} onClick={(event) => { event.stopPropagation(); setVisible(!visible); }}>
      {visible ? <EyeInvisibleOutlined aria-hidden="true" /> : <EyeOutlined aria-hidden="true" />}
    </button>
  } />;
}
