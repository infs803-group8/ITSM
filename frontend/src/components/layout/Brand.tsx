import { CustomerServiceOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";

export function Brand() {
  return <Link to="/" className="brand" aria-label="IT Service Desk home">
    <span className="brand-symbol"><CustomerServiceOutlined aria-hidden="true" /></span>
    <span><strong>IT SERVICE DESK</strong><small>SUPPORT WORKSPACE</small></span>
  </Link>;
}
