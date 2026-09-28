import type { AttachmentConfig, PresignData, PresignRequest } from "./types";

type AttachmentCheck = { error: string; contentType?: never } | { error: null; contentType: PresignRequest["content_type"] };
export function resolveAttachment(file: File, config: AttachmentConfig): AttachmentCheck {
  if (file.size < 1 || file.size > config.max_size_bytes) return { error: "Choose a non-empty file no larger than 10 MiB." };
  if (file.name.length > 255) return { error: "The file name must not exceed 255 characters." };
  const extension = file.name.toLowerCase().split(".").pop();
  const rule = config.allowed_types.find((item) => file.name.includes(".") && item.extension.replace(/^\./, "").toLowerCase() === extension);
  // Browsers may leave .log MIME blank. Only API-12's allowlist may supply it;
  // a non-empty, mismatched browser MIME must never be silently replaced.
  const contentType = file.type || rule?.content_type;
  if (!rule || rule.content_type !== contentType || (contentType !== "image/png" && contentType !== "image/jpeg" && contentType !== "application/pdf" && contentType !== "text/plain")) {
    return { error: "The file extension and content type must match one of the allowed formats shown above." };
  }
  return { error: null, contentType };
}
export function validateAttachment(file: File, config: AttachmentConfig): string | null {
  return resolveAttachment(file, config).error;
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
