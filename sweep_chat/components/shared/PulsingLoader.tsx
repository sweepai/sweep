export default function PulsingLoader({
  size = 2,
  message,
}: {
  size: number
  message?: string
}) {
  return (
    <div
      className={`animate-pulse rounded-full bg-zinc-700 mr-2 p-4`}
      style={{ padding: `${size}rem` }}
    >
      {message ? message : ''}
    </div>
  )
}
