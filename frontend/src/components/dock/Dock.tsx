import { Children, cloneElement, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  motion,
  AnimatePresence,
  useMotionValue,
  useSpring,
  useTransform,
  type MotionValue,
} from 'framer-motion'

import './Dock.css'

interface SpringOptions {
  mass?: number
  stiffness?: number
  damping?: number
}

export interface DockItemData {
  key?: string
  icon: ReactNode
  label: string
  onClick?: () => void
  className?: string
}

const DOCK_SPRING: SpringOptions = { mass: 0.1, stiffness: 150, damping: 12 }

interface DockItemProps {
  children: ReactNode
  className?: string
  onClick?: () => void
  mouseX: MotionValue<number>
  spring: SpringOptions
  distance: number
  magnification: number
  baseItemSize: number
  label: string
}

function DockItem({
  children,
  className = '',
  onClick,
  mouseX,
  spring,
  distance,
  magnification,
  baseItemSize,
  label,
}: DockItemProps) {
  const ref = useRef<HTMLDivElement>(null)
  const isHovered = useMotionValue(0)

  const mouseDistance = useTransform(mouseX, val => {
    const rect = ref.current?.getBoundingClientRect() ?? { x: 0, width: baseItemSize }
    return val - rect.x - baseItemSize / 2
  })

  const targetSize = useTransform(mouseDistance, [-distance, 0, distance], [baseItemSize, magnification, baseItemSize])
  const size = useSpring(targetSize, spring)

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onClick?.()
    }
  }

  return (
    <motion.div
      ref={ref}
      style={{ width: size, height: size }}
      onHoverStart={() => isHovered.set(1)}
      onHoverEnd={() => isHovered.set(0)}
      onFocus={() => isHovered.set(1)}
      onBlur={() => isHovered.set(0)}
      onClick={onClick}
      className={`dock-item ${className}`}
      tabIndex={0}
      role="button"
      aria-haspopup="true"
      aria-label={label}
      onKeyDown={handleKeyDown}
    >
      {Children.map(children, child => cloneElement(child as React.ReactElement, { isHovered }))}
    </motion.div>
  )
}

function DockLabel({
  children,
  className = '',
  isHovered,
}: {
  children: ReactNode
  className?: string
  isHovered: MotionValue<number>
}) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const unsubscribe = isHovered.on('change', latest => {
      setIsVisible(latest === 1)
    })
    return () => unsubscribe()
  }, [isHovered])

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: 0 }}
          animate={{ opacity: 1, y: -10 }}
          exit={{ opacity: 0, y: 0 }}
          transition={{ duration: 0.2 }}
          className={`dock-label ${className}`}
          role="tooltip"
          style={{ x: '-50%' }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function DockIcon({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`dock-icon ${className}`}>{children}</div>
}

interface DockProps {
  items: DockItemData[]
  className?: string
  spring?: SpringOptions
  magnification?: number
  distance?: number
  panelHeight?: number
  dockHeight?: number
  baseItemSize?: number
}

export default function Dock({
  items,
  className = '',
  spring = DOCK_SPRING,
  magnification = 60,
  distance = 200,
  panelHeight = 52,
  dockHeight = 64,
  baseItemSize = 44,
}: DockProps) {
  const mouseX = useMotionValue(Infinity)
  const isHovered = useMotionValue(0)

  const maxHeight = useMemo(
    () => Math.max(dockHeight, magnification + magnification / 2 + 4),
    [magnification, dockHeight]
  )
  const heightRow = useTransform(isHovered, [0, 1], [panelHeight, maxHeight])
  const height = useSpring(heightRow, spring)

  return (
    <motion.div style={{ height, scrollbarWidth: 'none' }} className="dock-outer">
      <motion.div
        onMouseMove={({ pageX }) => {
          isHovered.set(1)
          mouseX.set(pageX)
        }}
        onMouseLeave={() => {
          isHovered.set(0)
          mouseX.set(Infinity)
        }}
        className={`dock-panel ${className}`}
        style={{ height: panelHeight }}
        role="toolbar"
        aria-label="Application dock"
      >
        {items.map((item, index) => (
          <DockItem
            key={item.key ?? index}
            onClick={item.onClick}
            className={item.className}
            mouseX={mouseX}
            spring={spring}
            distance={distance}
            magnification={magnification}
            baseItemSize={baseItemSize}
            label={item.label}
          >
            <DockIcon>{item.icon}</DockIcon>
            <DockLabel isHovered={isHovered}>{item.label}</DockLabel>
          </DockItem>
        ))}
      </motion.div>
    </motion.div>
  )
}