import { useRef } from 'react'

export function useDebounce() {
  const timers = useRef({})
  return (key, fn, delay = 500) => {
    clearTimeout(timers.current[key])
    timers.current[key] = setTimeout(fn, delay)
  }
}
