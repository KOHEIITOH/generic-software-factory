let authEpoch = 0;
export async function operatorApi(path: string, options: RequestInit = {}) {
  const epoch = authEpoch;
  const response = await fetch("/api/operator" + path, { ...options, credentials: "same-origin", headers: {
    "Content-Type": "application/json", "x-sf-operator": "1", ...options.headers } });
  if (response.status === 401 && epoch === authEpoch) window.dispatchEvent(new Event("sf-operator-expired"));
  return response;
}
// Deduplicate StrictMode's simultaneous exchange, but never cache a failed login forever.
let bootstrap: { token: string; promise: Promise<void> } | null = null;
export function exchangeToken(token: string) {
  if (bootstrap?.token === token) return bootstrap.promise;
  authEpoch++;
  const previous = bootstrap?.promise.catch(() => {});
  const promise = Promise.resolve(previous).then(() => operatorApi("/session", { method: "POST", headers: { Authorization: "Bearer " + token } }))
    .then(r => { if (!r.ok) throw new Error("操作リンクを確認してください。サーバー再起動後は新しいリンクが必要です。"); })
    .finally(() => { if (bootstrap?.promise === promise) bootstrap = null; });
  bootstrap = { token, promise };
  return promise;
}
export function exchange() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("operator");
  if (token) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    if (!/^[A-Za-z0-9_-]{32,128}$/.test(token)) return Promise.reject(new Error("操作リンクを確認してください。"));
    return exchangeToken(token);
  }
  return bootstrap?.promise || Promise.resolve();
}
export function linkToken(value: string) {
  let link: URL;
  try { link = new URL(value.trim()); } catch { throw new Error("ターミナルに表示された操作リンクを貼り付けてください。"); }
  if (link.origin !== window.location.origin || link.pathname !== "/" || link.search || link.username || link.password) throw new Error("起動したターミナルの、この画面と同じ接続先の操作リンクを貼り付けてください。");
  const token = new URLSearchParams(link.hash.slice(1)).get("operator");
  if (!token || !/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new Error("操作権限を含むリンクを貼り付けてください。");
  return token;
}
