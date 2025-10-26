"use client"

import { useState, useEffect, useCallback, useRef } from "react"

interface PerformanceMetrics {
  renderTime: number
  memoryUsage?: number
  fps?: number
  networkLatency?: number
}

interface UsePerformanceOptions {
  enableMemoryMonitoring?: boolean
  enableFPSMonitoring?: boolean
  enableNetworkMonitoring?: boolean
  sampleRate?: number
}

export function usePerformance(options: UsePerformanceOptions = {}) {
  const {
    enableMemoryMonitoring = false,
    enableFPSMonitoring = false,
    enableNetworkMonitoring = false,
    sampleRate = 1000
  } = options

  const [metrics, setMetrics] = useState<PerformanceMetrics>({
    renderTime: 0
  })
  
  const [isMonitoring, setIsMonitoring] = useState(false)
  const frameCountRef = useRef(0)
  const lastTimeRef = useRef(performance.now())
  const animationFrameRef = useRef<number>()

  const measureRenderTime = useCallback((fn: () => void) => {
    const start = performance.now()
    fn()
    const end = performance.now()
    const renderTime = end - start
    
    setMetrics(prev => ({ ...prev, renderTime }))
    return renderTime
  }, [])

  const measureAsync = useCallback(async <T>(fn: () => Promise<T>): Promise<T> => {
    const start = performance.now()
    const result = await fn()
    const end = performance.now()
    const renderTime = end - start
    
    setMetrics(prev => ({ ...prev, renderTime }))
    return result
  }, [])

  const measureNetworkLatency = useCallback(async (url: string): Promise<number> => {
    const start = performance.now()
    try {
      await fetch(url, { method: 'HEAD' })
      const end = performance.now()
      const latency = end - start
      
      setMetrics(prev => ({ ...prev, networkLatency: latency }))
      return latency
    } catch (error) {
      console.error('Network latency measurement failed:', error)
      return -1
    }
  }, [])

  const startMonitoring = useCallback(() => {
    if (isMonitoring) return
    
    setIsMonitoring(true)
    
    if (enableFPSMonitoring) {
      const measureFPS = () => {
        frameCountRef.current++
        const currentTime = performance.now()
        
        if (currentTime - lastTimeRef.current >= sampleRate) {
          const fps = Math.round((frameCountRef.current * 1000) / (currentTime - lastTimeRef.current))
          setMetrics(prev => ({ ...prev, fps }))
          
          frameCountRef.current = 0
          lastTimeRef.current = currentTime
        }
        
        animationFrameRef.current = requestAnimationFrame(measureFPS)
      }
      
      measureFPS()
    }
    
    if (enableMemoryMonitoring && 'memory' in performance) {
      const measureMemory = () => {
        const memory = (performance as any).memory
        if (memory) {
          const memoryUsage = memory.usedJSHeapSize / (1024 * 1024) // MB
          setMetrics(prev => ({ ...prev, memoryUsage }))
        }
      }
      
      const memoryInterval = setInterval(measureMemory, sampleRate)
      
      return () => {
        clearInterval(memoryInterval)
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current)
        }
      }
    }
    
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
    }
  }, [isMonitoring, enableFPSMonitoring, enableMemoryMonitoring, sampleRate])

  const stopMonitoring = useCallback(() => {
    setIsMonitoring(false)
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
    }
  }, [])

  useEffect(() => {
    const cleanup = startMonitoring()
    return cleanup
  }, [startMonitoring])

  useEffect(() => {
    return () => {
      stopMonitoring()
    }
  }, [stopMonitoring])

  return {
    metrics,
    isMonitoring,
    measureRenderTime,
    measureAsync,
    measureNetworkLatency,
    startMonitoring,
    stopMonitoring
  }
}

// 防抖Hook
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(handler)
    }
  }, [value, delay])

  return debouncedValue
}

// 节流Hook
export function useThrottle<T>(value: T, limit: number): T {
  const [throttledValue, setThrottledValue] = useState<T>(value)
  const lastRan = useRef<number>(Date.now())

  useEffect(() => {
    const handler = setTimeout(() => {
      if (Date.now() - lastRan.current >= limit) {
        setThrottledValue(value)
        lastRan.current = Date.now()
      }
    }, limit - (Date.now() - lastRan.current))

    return () => {
      clearTimeout(handler)
    }
  }, [value, limit])

  return throttledValue
}

// 优化状态更新Hook
export function useOptimisticUpdate<T>(
  initialValue: T,
  updateFn: (value: T) => Promise<T>
) {
  const [value, setValue] = useState<T>(initialValue)
  const [isUpdating, setIsUpdating] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const update = useCallback(async (newValue: T) => {
    // 乐观更新
    setValue(newValue)
    setIsUpdating(true)
    setError(null)

    try {
      const result = await updateFn(newValue)
      setValue(result)
    } catch (err) {
      setError(err as Error)
      // 回滚到之前的值
      setValue(initialValue)
    } finally {
      setIsUpdating(false)
    }
  }, [updateFn, initialValue])

  return {
    value,
    isUpdating,
    error,
    update
  }
}
