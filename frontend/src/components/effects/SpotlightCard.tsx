import { useRef, type ReactNode } from 'react'

interface SpotlightCardProps {
  children: ReactNode
  className?: string
}

export function SpotlightCard({ children, className = '' }: SpotlightCardProps) {
  const ref = useRef<HTMLDivElement>(null)

  const handleMouseMove = (e: React.MouseEvent) => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    el.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`)
    el.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`)
  }

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      className={`spotlight-card group ${className}`}
    >
      <div className="relative z-10">{children}</div>
    </div>
  )
}
