import { apiClient } from "./client";
import type {
  KnowledgeDocument,
  KnowledgeImportResponse,
  KnowledgeStats,
  SearchResponse,
} from "../types/api";

export async function getKnowledgeStats(): Promise<KnowledgeStats> {
  const { data } = await apiClient.get<KnowledgeStats>("/knowledge/stats");
  return data;
}

export async function addKnowledge(
  documents: KnowledgeDocument[],
): Promise<KnowledgeImportResponse> {
  const { data } = await apiClient.post<KnowledgeImportResponse>("/knowledge/add", {
    documents,
  });
  return data;
}

export async function uploadKnowledge(file: File): Promise<KnowledgeImportResponse> {
  const form = new FormData();
  form.append("file", file);

  const { data } = await apiClient.post<KnowledgeImportResponse>(
    "/knowledge/upload",
    form,
  );
  return data;
}

export async function searchKnowledge(
  query: string,
  topK = 5,
): Promise<SearchResponse> {
  const { data } = await apiClient.post<SearchResponse>("/search", undefined, {
    params: { query, top_k: topK },
  });
  return data;
}
