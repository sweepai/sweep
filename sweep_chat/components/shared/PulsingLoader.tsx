export default function PulsingLoader ({
  size = 2
}: {
  size: number
}) {
  return (
    <div className={`animate-pulse rounded-full bg-zinc-700 mr-2 p-4`} style={{ padding: `${size}rem` }}></div>
  )
}

