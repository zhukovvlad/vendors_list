import * as React from "react"

const MOBILE_BREAKPOINT = 768

function getIsMobile() {
  return window.innerWidth < MOBILE_BREAKPOINT
}

/**
 * Возвращает `true`, если ширина окна меньше мобильного брейкпоинта (768px).
 * Инициализируется синхронно из текущей ширины и подписывается на изменения
 * media query, обновляя состояние при пересечении порога.
 */
export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean>(() => getIsMobile())

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const onChange = () => {
      setIsMobile(getIsMobile())
    }
    mql.addEventListener("change", onChange)
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return isMobile
}
