import type { AttachmentConfig, PresignData } from "./types";

export function validateAttachment(file: File, config: AttachmentConfig): string | null {
  if (file.size < 1 || file.size > config.max_size_bytes) return "Choose a non-empty file no larger than 10 MiB.";
  const extension = file.name.toLowerCase().split(".").pop();
  if (!config.allowed_types.some((rule) => rule.extension.replace(/^\./, "") === extension && rule.content_type === file.type)) return "The file extension and content type must match one of the allowed formats shown above.";
  if (file.name.length > 255) return "The file name must not exceed 255 characters.";
  return null;
}
export function safeTransferUrl(value: string): string {
  const url = new URL(value);
  if (url.username || url.password || (url.protocol !== "https:" && !(import.meta.env.DEV && url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)))) throw new Error("Unsafe storage URL");
  return url.href;
}
// A raw XHR deliberately bypasses the API client's Bearer token and interceptors.
export function putAttachment(file: File, upload: PresignData, signal: AbortSignal, progress: (percent: number) => void): Promise<void> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const finish = (error?: Error) => { signal.removeEventListener("abort", abort); error ? reject(error) : resolve(); };
    xhr.open("PUT", safeTransferUrl(upload.upload_url)); xhr.timeout = 120_000;
    for (const [name, value] of Object.entries(upload.signed_headers)) xhr.setRequestHeader(name, value);
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) progress(Math.round(event.loaded / event.total * 100)); };
    xhr.onload = () => finish(xhr.status >= 200 && xhr.status < 300 ? undefined : new Error("Storage upload failed"));
    xhr.onerror = () => finish(new Error("Storage connection failed")); xhr.ontimeout = () => finish(new Error("Storage upload timed out"));
    xhr.onabort = () => finish(new DOMException("Upload cancelled", "AbortError"));
    signal.addEventListener("abort", abort, { once: true }); xhr.send(file);
  });
}
