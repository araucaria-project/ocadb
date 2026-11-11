/** Per-browser memory of how each identifier last signed in (only a UI hint, nothing secret). */

export type LoginMethod = 'password' | 'code';

const LAST_IDENTIFIER_KEY = 'ocadb_last_identifier';
const LOGIN_METHODS_KEY = 'ocadb_login_methods';

export function readStorage(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

export function writeStorage(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch {}
}

function loadMethods(): Record<string, LoginMethod> {
  try { return JSON.parse(readStorage(LOGIN_METHODS_KEY) ?? '{}'); } catch { return {}; }
}

/** Code unless this browser last signed in this identifier with a password. */
export function preferredLoginMethod(identifier: string): LoginMethod {
  return loadMethods()[identifier.trim().toLowerCase()] ?? 'code';
}

/** Remembers the method for each identifier (e.g. both the typed email and the Araucaria ID). */
export function rememberLoginMethod(identifiers: (string | null | undefined)[], method: LoginMethod) {
  const methods = loadMethods();
  for (const id of identifiers) {
    if (id?.trim()) methods[id.trim().toLowerCase()] = method;
  }
  writeStorage(LOGIN_METHODS_KEY, JSON.stringify(methods));
}

export function lastIdentifier(): string | null {
  return readStorage(LAST_IDENTIFIER_KEY);
}

export function setLastIdentifier(identifier: string) {
  writeStorage(LAST_IDENTIFIER_KEY, identifier.trim());
}
