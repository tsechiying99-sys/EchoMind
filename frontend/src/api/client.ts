import axios, { AxiosError } from "axios";

interface ApiErrorBody {
  detail?: string;
  message?: string;
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  timeout: 180_000,
  headers: {
    Accept: "application/json",
  },
});

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "请求已取消";
  }

  if (axios.isCancel(error)) {
    return "请求已取消";
  }

  if (error instanceof AxiosError) {
    const body = error.response?.data as ApiErrorBody | undefined;
    return body?.detail || body?.message || error.message || "网络请求失败";
  }

  return error instanceof Error ? error.message : "发生未知错误";
}
