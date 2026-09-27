import { ReloadOutlined, SafetyCertificateOutlined, SaveOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, Switch } from "antd";
import { useEffect, useRef, useState } from "react";
import { api10GetMyProfile, api11UpdateMyProfile } from "../../api/generated/sdk.gen";
import type { UpdateProfileRequest } from "../../api/types";
import { ApiErrorNotice } from "../../components/ApiErrorNotice";
import { displayNameRules } from "../../components/forms/rules";
import { useAuth } from "../auth/AuthProvider";
import { isEngineer, roleLabels } from "../auth/roleLabels";

export function ProfilePage() {
  const { user, sessionVersion, acceptProfile } = useAuth();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<UpdateProfileRequest>();
  const [saved, setSaved] = useState(false);
  const request = useRef<AbortController | null>(null);
  const queryKey = ["profile", user!.user_id, sessionVersion];
  const profile = useQuery({
    queryKey,
    queryFn: async ({ signal }) => (await api10GetMyProfile({ signal })).data.data,
    // Refresh explicitly through the guarded entry points below. A reconnect
    // must not start another read while a write or an unsaved edit is pending.
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const current = profile.data;
  const displayName = Form.useWatch("display_name", form);
  const availability = Form.useWatch("is_available", form);
  const engineer = current ? isEngineer(current.role) : false;
  const changed = !!current && (displayName?.trim() !== current.display_name || (engineer && availability !== current.is_available));

  useEffect(() => {
    document.title = "My profile | IT Service Desk";
    return () => { request.current?.abort(); };
  }, []);
  useEffect(() => {
    if (!current) return;
    acceptProfile(current, sessionVersion);
    form.setFieldsValue({ display_name: current.display_name, is_available: current.is_available ?? false });
  }, [current, form, acceptProfile, sessionVersion]);

  const mutation = useMutation({
    onMutate: async ({ signal }) => {
      await queryClient.cancelQueries({ queryKey, exact: true });
      // The user may have left or signed out while cancellation was pending.
      signal.throwIfAborted();
    },
    mutationFn: async ({ body, signal }: { body: UpdateProfileRequest; signal: AbortSignal }) => {
      signal.throwIfAborted();
      const response = await api11UpdateMyProfile({ body, signal });
      signal.throwIfAborted();
      return response.data.data;
    },
    onSuccess: (updated) => {
      if (!acceptProfile(updated, sessionVersion)) return;
      queryClient.setQueryData(queryKey, updated);
      form.setFieldsValue({ display_name: updated.display_name, is_available: updated.is_available ?? false });
      setSaved(true);
    },
    onSettled: (_data, _error, variables) => {
      if (request.current?.signal === variables.signal) request.current = null;
    },
  });

  function submit(values: UpdateProfileRequest) {
    if (!current || request.current || !changed) return;
    const body: UpdateProfileRequest = {};
    if (values.display_name?.trim() !== current.display_name) body.display_name = values.display_name?.trim();
    if (engineer && values.is_available !== current.is_available) body.is_available = values.is_available;
    if (!Object.keys(body).length) return;
    const controller = new AbortController();
    // Acquire the lock synchronously, including the await in onMutate.
    request.current = controller;
    setSaved(false);
    mutation.mutate({ body, signal: controller.signal });
  }

  function cancel() {
    if (!current || request.current) return;
    form.resetFields();
    form.setFieldsValue({ display_name: current.display_name, is_available: current.is_available ?? false });
    mutation.reset();
    setSaved(false);
  }

  function refresh() {
    if (request.current || profile.isFetching || changed) return;
    setSaved(false);
    void profile.refetch();
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">ACCOUNT SETTINGS</p><h1>My profile</h1>
      <p>Manage your details and service desk availability.</p></div>
      <Button icon={<ReloadOutlined aria-hidden="true" />} loading={profile.isFetching} disabled={mutation.isPending || changed}
        onClick={refresh}>Refresh</Button>
    </div>
    {profile.isPending && <div className="panel loading-panel" role="status">Loading your profile…</div>}
    {profile.isError && <ApiErrorNotice error={profile.error}
      onRetry={mutation.isPending || changed || profile.isFetching ? undefined : refresh} />}
    {current && <>
      <section className="profile-summary" aria-label="Account summary">
        <span className="avatar">{current.display_name.slice(0, 2).toUpperCase()}</span>
        <div><h2>{current.display_name}</h2><p>{current.email}</p></div>
        <span className="role-badge">{roleLabels[current.role]}</span>
      </section>
      <div className="profile-grid">
        <section className="panel" aria-labelledby="personal-details"><header className="panel-heading">
          <h2 id="personal-details">Personal details</h2><p>Keep your account information up to date.</p></header>
          <div className="panel-body">
            {saved && <div className="inline-notice success" role="status">Your profile has been updated.</div>}
            {mutation.isError && <ApiErrorNotice error={mutation.error} />}
            <Form form={form} name="profile" layout="vertical" requiredMark={false} disabled={mutation.isPending}
              validateTrigger="onBlur" onFinish={submit} onValuesChange={() => { setSaved(false); mutation.reset(); }} scrollToFirstError={{ focus: true }}>
              <Form.Item name="display_name" label="Display name" rules={displayNameRules}>
                <Input autoComplete="name" maxLength={100} />
              </Form.Item>
              <Form.Item label="Email address" htmlFor="profile-email" extra="Your sign-in email cannot be changed here.">
                <Input id="profile-email" value={current.email} readOnly className="readonly-input" />
              </Form.Item>
              {engineer && <div className="availability-field">
                <Form.Item name="is_available" label="Available for assignments" valuePropName="checked">
                  <Switch aria-label="Available for assignments" />
                </Form.Item><p>Allow the service desk to assign new tickets to you.</p>
              </div>}
              <div className="form-actions"><Button type="primary" htmlType="submit" icon={<SaveOutlined aria-hidden="true" />}
                loading={mutation.isPending} disabled={!changed}>Save changes</Button>
                <Button onClick={cancel} disabled={!changed}>Cancel</Button></div>
            </Form>
          </div>
        </section>
        <aside className="panel" aria-labelledby="account-access"><header className="panel-heading">
          <h2 id="account-access">Account access</h2><p>Assigned by your organisation.</p></header>
          <dl className="account-facts"><div><dt>Role</dt><dd>{roleLabels[current.role]}</dd></div>
            <div><dt>Account ID</dt><dd className="mono">#{current.user_id}</dd></div>
            {current.vendor_org && <div><dt>Vendor organisation</dt><dd>{current.vendor_org.name}</dd></div>}
            <div><dt>Member since</dt><dd>{formatDate(current.created_at)}</dd></div>
          </dl>
          <div className="access-note"><SafetyCertificateOutlined /><p>Your permissions are determined by your role. Contact your administrator if you need different access.</p></div>
        </aside>
      </div>
      <p className="security-footnote"><SafetyCertificateOutlined /> Your session is kept in this page only. Reloading or closing it requires a new sign-in.</p>
    </>}
  </>;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : new Intl.DateTimeFormat("en-NZ", { dateStyle: "medium" }).format(date);
}
