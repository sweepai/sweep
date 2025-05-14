import { Dispatch, SetStateAction } from 'react'

// Set isLoading to true, then set it to false on exit, always
export const withLoading = async (
    setIsLoading: Dispatch<SetStateAction<boolean>>,
    callback: (() => void) | (() => Promise<void>),
    onError: (error: Error) => void = () => {}
) => {
  setIsLoading(true)
  try {
    const result = callback()
    if (result instanceof Promise) {
      await result
    }
  } catch (error) {
    onError?.(error as Error)
    throw error
  } finally {
    setIsLoading(false)
  }
}
