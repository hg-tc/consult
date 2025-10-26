"use client"

import { useState, useEffect, useRef, ReactNode } from "react"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

interface LazyLoadProps {
  children: ReactNode
  fallback?: ReactNode
  threshold?: number
  rootMargin?: string
  className?: string
}

export function LazyLoad({
  children,
  fallback = <Spinner className="w-8 h-8 text-primary" />,
  threshold = 0.1,
  rootMargin = "50px",
  className
}: LazyLoadProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [isLoaded, setIsLoaded] = useState(false)
  const elementRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = elementRef.current
    if (!element) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isLoaded) {
          setIsVisible(true)
          setIsLoaded(true)
          observer.disconnect()
        }
      },
      {
        threshold,
        rootMargin
      }
    )

    observer.observe(element)

    return () => {
      observer.disconnect()
    }
  }, [threshold, rootMargin, isLoaded])

  return (
    <div ref={elementRef} className={className}>
      {isVisible ? children : fallback}
    </div>
  )
}

interface LazyImageProps {
  src: string
  alt: string
  className?: string
  placeholder?: string
  onLoad?: () => void
  onError?: () => void
}

export function LazyImage({
  src,
  alt,
  className,
  placeholder = "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjNmNGY2Ii8+PC9zdmc+",
  onLoad,
  onError
}: LazyImageProps) {
  const [isLoaded, setIsLoaded] = useState(false)
  const [hasError, setHasError] = useState(false)

  const handleLoad = () => {
    setIsLoaded(true)
    onLoad?.()
  }

  const handleError = () => {
    setHasError(true)
    onError?.()
  }

  return (
    <LazyLoad
      fallback={
        <div className={cn("bg-muted animate-pulse", className)}>
          <div className="w-full h-full flex items-center justify-center">
            <Spinner className="w-6 h-6 text-muted-foreground" />
          </div>
        </div>
      }
    >
      <img
        src={hasError ? placeholder : src}
        alt={alt}
        className={cn(
          "transition-opacity duration-300",
          isLoaded ? "opacity-100" : "opacity-0",
          className
        )}
        onLoad={handleLoad}
        onError={handleError}
      />
    </LazyLoad>
  )
}

interface LazyComponentProps {
  component: () => Promise<{ default: React.ComponentType<any> }>
  fallback?: ReactNode
  props?: any
}

export function LazyComponent({
  component,
  fallback = <Spinner className="w-8 h-8 text-primary" />,
  props = {}
}: LazyComponentProps) {
  const [Component, setComponent] = useState<React.ComponentType<any> | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    component()
      .then((module) => {
        setComponent(() => module.default)
        setIsLoading(false)
      })
      .catch((error) => {
        console.error("Failed to load component:", error)
        setIsLoading(false)
      })
  }, [component])

  if (isLoading || !Component) {
    return <>{fallback}</>
  }

  return <Component {...props} />
}
