import { useEffect, useRef, type ReactNode } from 'react'

interface FadeInProps {
  children: ReactNode
  className?: string
  delay?: number
  direction?: 'up' | 'down' | 'left' | 'right' | 'none'
  duration?: number
}

export function FadeIn({ children, className = '', delay = 0, direction = 'up', duration = 500 }: FadeInProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.style.opacity = '1'
          el.style.transform = 'translate(0, 0)'
          observer.unobserve(el)
        }
      },
      { threshold: 0.1 }
    )

    el.style.opacity = '0'
    el.style.transition = `opacity ${duration}ms ease ${delay}ms, transform ${duration}ms ease ${delay}ms`

    const transforms: Record<string, string> = {
      up: 'translateY(20px)',
      down: 'translateY(-20px)',
      left: 'translateX(20px)',
      right: 'translateX(-20px)',
      none: 'none',
    }
    el.style.transform = transforms[direction]

    observer.observe(el)
    return () => observer.disconnect()
  }, [delay, direction, duration])

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  )
}
