/** Обёртка над import.meta.env.DEV — мокабельна в тестах (vi.mock). */
export function isDevBuild(): boolean {
  return import.meta.env.DEV
}
