export function logInfo(scope: string, msg: string, extra?: any) {
  const t = new Date().toISOString();
  if (extra !== undefined) {
    console.log(`[${t}] [INFO] [${scope}] ${msg}`, extra);
  } else {
    console.log(`[${t}] [INFO] [${scope}] ${msg}`);
  }
}

export function logWarn(scope: string, msg: string, extra?: any) {
  const t = new Date().toISOString();
  console.warn(`[${t}] [WARN] [${scope}] ${msg}`, extra ?? "");
}

export function logError(scope: string, msg: string, extra?: any) {
  const t = new Date().toISOString();
  console.error(`[${t}] [ERROR] [${scope}] ${msg}`, extra ?? "");
}
