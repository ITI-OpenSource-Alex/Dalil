export function isExamFocusPath(pathname: string): boolean {
  if (!pathname) return false;
  const normalized =
    pathname.length > 1 && pathname.endsWith("/")
      ? pathname.slice(0, -1)
      : pathname;
  return normalized === "/exam/shell";
}
