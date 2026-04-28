import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SerendieProvider } from "@serendie/ui";
import type { ReactNode } from "react";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <SerendieProvider lang="ja" colorTheme="konjo">{children}</SerendieProvider>
    </QueryClientProvider>
  );
}
