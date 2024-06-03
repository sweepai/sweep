export default function PulsingLoader ({
  size = 8
}: {
  size: number
}) {
  return (
    <div className={`animate-pulse rounded-full h-${size} w-${size} bg-zinc-700 mr-2`}></div>
  )
}