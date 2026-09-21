import { apiClient } from "./client";
import type { EvalReport, EvalRunInput } from "../types/api";

export async function runEvaluation(input?: EvalRunInput): Promise<EvalReport> {
  const { data } = await apiClient.post<EvalReport>("/eval/run", input);
  return data;
}
