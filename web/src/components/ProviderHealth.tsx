import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import "./ProviderHealth.css";

export function ProviderHealth() {
  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.providers,
    queryFn: api.listProviders,
    refetchOnWindowFocus: true,
  });

  if (isLoading) {
    return <div className="provider-health provider-health--loading">Providers…</div>;
  }

  if (isError || !data) {
    return (
      <div className="provider-health provider-health--error">Providers unavailable</div>
    );
  }

  return (
    <div className="provider-health">
      <span className="provider-health__label">Providers</span>
      {data.map((provider) => (
        <span key={provider.name} className="provider-chip" title={provider.base_url}>
          <span
            className={`provider-chip__dot provider-chip__dot--${provider.healthy ? "healthy" : "unhealthy"}`}
          />
          {provider.name}
        </span>
      ))}
    </div>
  );
}
