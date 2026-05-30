import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import type { Provider } from "../api/types";
import "./ProviderModelSelect.css";

interface ProviderModelSelectProps {
  provider: string;
  model: string;
  onProviderChange: (provider: string) => void;
  onModelChange: (model: string) => void;
  providers: Provider[];
  disabled?: boolean;
}

export function ProviderModelSelect({
  provider,
  model,
  onProviderChange,
  onModelChange,
  providers,
  disabled = false,
}: ProviderModelSelectProps) {
  const healthyProviders = providers.filter((item) => item.healthy);
  const selectedProvider = provider || healthyProviders[0]?.name || "";

  useEffect(() => {
    if (!provider && healthyProviders[0]) {
      onProviderChange(healthyProviders[0].name);
    }
  }, [provider, healthyProviders, onProviderChange]);

  const { data: modelsData, isLoading: modelsLoading, isError: modelsError } = useQuery({
    queryKey: queryKeys.providerModels(selectedProvider),
    queryFn: () => api.listProviderModels(selectedProvider),
    enabled: Boolean(selectedProvider),
  });

  const models = modelsData?.models ?? [];

  return (
    <div className="provider-model-select">
      <label className="form-field">
        <span className="form-field__label">Provider</span>
        <select
          className="form-field__input"
          aria-label="Provider"
          value={selectedProvider}
          disabled={disabled}
          onChange={(event) => {
            onProviderChange(event.target.value);
            onModelChange("");
          }}
        >
          {healthyProviders.length === 0 && (
            <option value="">No healthy providers</option>
          )}
          {healthyProviders.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}
            </option>
          ))}
        </select>
      </label>

      <label className="form-field">
        <span className="form-field__label">Model</span>
        <select
          className="form-field__input"
          aria-label="Model"
          value={model}
          disabled={disabled || !selectedProvider || modelsLoading}
          onChange={(event) => onModelChange(event.target.value)}
        >
          <option value="">
            {modelsLoading ? "Loading models…" : modelsError ? "Failed to load models" : "Select model"}
          </option>
          {models.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

export function qualifiedModel(provider: string, model: string): string {
  if (!provider || !model) {
    return "";
  }
  return `${provider}/${model}`;
}
