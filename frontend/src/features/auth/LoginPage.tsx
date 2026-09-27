import { ArrowRightOutlined } from "@ant-design/icons";
import { Button, Form, Input } from "antd";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { shouldEnableMocks } from "../../api/config";
import type { LoginRequest } from "../../api/types";
import { ApiErrorNotice } from "../../components/ApiErrorNotice";
import { PasswordInput } from "../../components/forms/PasswordInput";
import { emailRules } from "../../components/forms/rules";
import { AuthShell } from "../../components/layout/AuthShell";
import { useAuth } from "./AuthProvider";

// This component and its fake credentials are excluded from production builds.
const DemoAccount = import.meta.env.DEV ? lazy(() => import("./DevDemoAccount")) : null;

export function LoginPage() {
  const { signIn, sessionExpired } = useAuth();
  const location = useLocation();
  const [form] = Form.useForm<LoginRequest>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const request = useRef<AbortController | null>(null);
  const registered = location.state?.registered === true;
  const email = typeof location.state?.email === "string" ? location.state.email : "";

  useEffect(() => {
    document.title = "Sign in | IT Service Desk";
    return () => { request.current?.abort(); };
  }, []);

  async function submit(values: LoginRequest) {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError(null);
    try { await signIn({ email: values.email.trim(), password: values.password }, controller.signal); }
    catch (failure) { if (!controller.signal.aborted) setError(failure); }
    finally {
      if (!controller.signal.aborted) setBusy(false);
      if (request.current === controller) request.current = null;
    }
  }

  return <AuthShell>
    <p className="eyebrow">WELCOME BACK</p>
    <h1>Sign in to your workspace</h1>
    <p className="page-intro">Access your service desk account.</p>
    {registered && <div className="inline-notice success" role="status">Account created. Sign in with your new password.</div>}
    {sessionExpired && <div className="inline-notice" role="status">Your session has expired. Please sign in again.</div>}
    {error != null && <ApiErrorNotice error={error} />}
    <Form form={form} name="login" layout="vertical" requiredMark={false} disabled={busy}
      initialValues={{ email }} onFinish={submit} validateTrigger="onBlur" scrollToFirstError={{ focus: true }}>
      <Form.Item name="email" label="Email address" rules={emailRules}>
        <Input autoComplete="username" inputMode="email" maxLength={254} placeholder="you@organisation.com" />
      </Form.Item>
      <Form.Item name="password" label="Password" rules={[{ required: true, message: "Enter your password." }, { max: 128, message: "Use 128 characters or fewer." }]}>
        <PasswordInput autoComplete="current-password" maxLength={128} placeholder="Enter your password" />
      </Form.Item>
      <Button type="primary" htmlType="submit" block loading={busy} icon={<ArrowRightOutlined aria-hidden="true" />} iconPlacement="end">Sign in</Button>
    </Form>
    <p className="form-switch">New to the service desk? <Link to="/register">Create an account</Link></p>
    <p className="session-note">For your security, refreshing this page will require you to sign in again.</p>
    {DemoAccount && shouldEnableMocks(import.meta.env) && <Suspense fallback={null}>
      <DemoAccount onFill={(values) => form.setFieldsValue(values)} />
    </Suspense>}
  </AuthShell>;
}
