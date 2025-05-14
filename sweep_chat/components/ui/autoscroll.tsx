import { useEffect, useRef } from 'react'

import { ScrollArea } from '@/components/ui/scroll-area'

export default function AutoScrollArea({
  children,
  className = '',
  threshold = Infinity,
}: {
  children: React.ReactNode
  className?: string
  threshold?: number
}) {
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (scrollAreaRef.current && scrollAreaRef.current.scrollHeight > 0) {
      const { scrollTop, scrollHeight, clientHeight } = scrollAreaRef.current
      if (scrollHeight - scrollTop - clientHeight < threshold) {
        scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight
      }
    }
  }, [children])
  return (
    <ScrollArea ref={scrollAreaRef} className={className}>
      {children}
    </ScrollArea>
  )
}

