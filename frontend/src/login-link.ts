/** The login link from the code email: <path>#login_id=<araucaria id>&login_code=<code>. */
export interface LoginLink {
  identifier: string;
  code: string;
}

/** Reads a login link from the URL fragment and removes it from the address bar,
 * so the code doesn't stay in history, bookmarks or copied links. */
export function consumeLoginLink(): LoginLink | null {
  const hash = window.location.hash.replace(/^#/, '');
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const identifier = params.get('login_id');
  const code = params.get('login_code');
  if (!identifier || !code) return null;
  history.replaceState(history.state, '', window.location.pathname + window.location.search);
  return { identifier, code };
}
