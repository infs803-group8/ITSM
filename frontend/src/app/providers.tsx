import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type PropsWithChildren } from "react";
import { ConfigProvider } from "antd";
import enUS from "antd/locale/en_US";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "../features/auth/AuthProvider";
import { helpdeskTheme } from "../styles/theme";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } } }));
  return (
    <ConfigProvider theme={helpdeskTheme} locale={enUS}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter><AuthProvider>{children}</AuthProvider></BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  );
}
