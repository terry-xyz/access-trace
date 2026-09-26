const CREDENTIAL_DIRECTORIES = new Set([
  ".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker",
]);
const CREDENTIAL_FILES = new Set([".npmrc", ".pypirc", ".netrc", ".envrc"]);
const PRIVATE_KEY_EXTENSIONS = /\.(?:key|pem|p12|pfx)$/i;
const CREDENTIAL_NAME = /(?:^|[-_.])(?:credentials?|secrets?|tokens?|access[-_.]?tokens?|service[-_.]?accounts?)(?:[-_.]|$)/i;
const CREDENTIAL_DATA_EXTENSIONS = /\.(?:json|ya?ml|toml|ini|cfg|txt|properties)$/i;

/** Avoid reading and submitting files whose path strongly indicates stored credentials. */
export function isSensitiveSourcePath(path) {
  if (typeof path !== "string") return false;
  const parts = path.toLowerCase().split("/");
  if (parts.slice(0, -1).some((part) => CREDENTIAL_DIRECTORIES.has(part))) return true;
  const name = parts.at(-1);
  return name === ".env"
    || name.startsWith(".env.")
    || CREDENTIAL_FILES.has(name)
    || /^id_(?:rsa|dsa|ecdsa|ed25519)(?:\.|$)/.test(name)
    || PRIVATE_KEY_EXTENSIONS.test(name)
    || (CREDENTIAL_NAME.test(name) && (CREDENTIAL_DATA_EXTENSIONS.test(name) || !name.includes(".")));
}

export function filterSensitiveFiles(entries) {
  const safeEntries = entries.filter((entry) => !isSensitiveSourcePath(entry.path));
  return { entries: safeEntries, skippedCount: entries.length - safeEntries.length };
}
