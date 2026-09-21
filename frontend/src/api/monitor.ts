import { apiClient } from "./client";
import type {
  HealthResponse,
  MonitorResponse,
  SkillSummary,
} from "../types/api";

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>("/health");
  return data;
}

export async function getMonitor(): Promise<MonitorResponse> {
  const { data } = await apiClient.get<MonitorResponse>("/monitor");
  return data;
}

export async function getSkills(): Promise<SkillSummary> {
  const { data } = await apiClient.get<SkillSummary>("/skills");
  return data;
}

export async function reloadSkills(): Promise<SkillSummary> {
  const { data } = await apiClient.post<SkillSummary>("/skills/reload");
  return data;
}
