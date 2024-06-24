import { FaThumbsUp, FaThumbsDown } from 'react-icons/fa'
import { useState } from 'react'
import { Message } from '@/lib/types'
import { posthog } from '@/lib/posthog'
import { toast } from '@/components/ui/use-toast'

export default function FeedbackBlock({
  message,
  index,
}: {
  message: Message
  index: number
}) {
  const [isLiked, setIsLiked] = useState(false)
  const [isDisliked, setIsDisliked] = useState(false)
  return (
    <div className="flex justify-end my-2">
      <FaThumbsUp
        className={`inline-block text-lg ${
          isLiked
            ? 'text-green-500 cursor-not-allowed'
            : 'text-zinc-400 hover:cursor-pointer hover:text-zinc-200 hover:drop-shadow-md'
        }`}
        onClick={() => {
          if (isLiked) {
            return
          }
          posthog.capture('message liked', {
            message: message,
            index: index,
          })
          toast({
            title: 'We received your like',
            description:
              'Thank you for your feedback! If you would like to share any highlights, feel free to shoot us a message on Slack!',
            variant: 'default',
            duration: 2000,
          })
          setIsLiked(true)
          setIsDisliked(false)
        }}
      />
      <FaThumbsDown
        className={`inline-block ml-3 text-lg ${
          isDisliked
            ? 'text-red-500 cursor-not-allowed'
            : 'text-zinc-400 hover:cursor-pointer hover:text-zinc-200 hover:drop-shadow-md'
        }`}
        onClick={() => {
          if (isDisliked) {
            return
          }
          posthog.capture('message disliked', {
            message: message,
            index: index,
          })
          toast({
            title: 'We received your dislike',
            description:
              'Thank you for your feedback! If you would like to report any persistent issues, feel free to shoot us a message on Slack!',
            variant: 'default',
            duration: 2000,
          })
          setIsDisliked(true)
          setIsLiked(false)
        }}
      />
    </div>
  )
}