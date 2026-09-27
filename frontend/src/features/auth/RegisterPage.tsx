import { ArrowRightOutlined } from "@ant-design/icons";
import { Button, Form, Input } from "antd";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api08Register } from "../../api/generated/sdk.gen";
import type { RegisterRequest } from "../../api/types";
import { ApiErrorNotice } from "../../components/ApiErrorNotice";
import { PasswordInput } from "../../components/forms/PasswordInput";
import { displayNameRules, emailRules, passwordRules } from "../../components/forms/rules";
import { AuthShell } from "../../components/layout/AuthShell";

type RegistrationValues = RegisterRequest & { confirmPassword: string };

export function RegisterPage() {
  const [form] = Form.useForm<RegistrationValues>();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    document.title = "Create account | IT Service Desk";
    return () => { request.current?.abort(); };
  }, []);

  async function submit(values: RegistrationValues) {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError(null);
    const body: RegisterRequest = { display_name: values.display_name.trim(), email: values.email.trim(), password: values.password };
    try {
      await api08Register({ body, signal: controller.signal });
      if (controller.signal.aborted) return;
      form.resetFields();
      navigate("/login", { replace: true, state: { registered: true, email: body.email } });
    } catch (failure) { if (!controller.signal.aborted) setError(failure); }
    finally {
      if (!controller.signal.aborted) setBusy(false);
      if (request.current === controller) request.current = null;
    }
  }

  return <AuthShell>
    <p className="eyebrow">GET STARTED</p><h1>Create your account</h1>
    <p className="page-intro">Register as a user to access IT support.</p>
    {error != null && <ApiErrorNotice error={error} />}
    <Form form={form} name="register" layout="vertical" requiredMark={false} disabled={busy}
      validateTrigger="onBlur" onFinish={submit} scrollToFirstError={{ focus: true }}>
      <Form.Item name="display_name" label="Display name" rules={displayNameRules}>
        <Input autoComplete="name" maxLength={100} placeholder="Your full name" />
      </Form.Item>
      <Form.Item name="email" label="Email address" rules={emailRules}>
        <Input autoComplete="username" inputMode="email" maxLength={254} placeholder="you@organisation.com" />
      </Form.Item>
      <Form.Item name="password" label="Password" rules={passwordRules} extra="Use 8–128 characters.">
        <PasswordInput autoComplete="new-password" maxLength={128} placeholder="Create a password" />
      </Form.Item>
      <Form.Item name="confirmPassword" label="Confirm password" dependencies={["password"]} rules={[
        { required: true, message: "Confirm your password." },
        ({ getFieldValue }) => ({ validator(_, value: string) {
          return !value || getFieldValue("password") === value ? Promise.resolve() : Promise.reject(new Error("Passwords do not match."));
        } }),
      ]}>
        <PasswordInput autoComplete="new-password" maxLength={128} placeholder="Repeat your password" />
      </Form.Item>
      <Button type="primary" htmlType="submit" block loading={busy} icon={<ArrowRightOutlined aria-hidden="true" />} iconPlacement="end">Create account</Button>
    </Form>
    <p className="form-switch">Already have an account? <Link to="/login">Sign in</Link></p>
    <p className="session-note">Engineer, vendor and manager access is assigned by your administrator.</p>
  </AuthShell>;
}
