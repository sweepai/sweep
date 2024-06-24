'use client'
import { usePostHog } from 'posthog-js/react'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from './ui/card'
import { Label } from './ui/label'
import { Button } from './ui/button'
import { Textarea } from './ui/textarea'
import { useEffect, useState } from 'react'

export default function Feedback({
  onClose,
}: {
  onClose: (didSubmit: boolean) => void
}) {
  const posthog = usePostHog()
  const [feedback, setFeedback] = useState('')
  const surveyID = process.env.NEXT_PUBLIC_SURVEY_ID

  useEffect(() => {
    posthog.capture('survey shown', {
      $survey_id: surveyID, // required
    })
  }, [posthog, surveyID])

  const handleSurveyDismissed = (e: any) => {
    e.preventDefault()
    posthog.capture('survey dismissed', {
      $survey_id: surveyID,
    })
    localStorage.setItem(`hasInteractedWithSurvey_${surveyID}`, 'true')
    onClose(false)
  }

  const handleFeedbackSubmit = (e: any) => {
    e.preventDefault()
    console.log(feedback)
    posthog.capture('survey sent', {
      $survey_id: surveyID,
      $survey_response: feedback,
    })
    localStorage.setItem(`hasInteractedWithSurvey_${surveyID}`, 'true')
    onClose(true)
  }

  return (
    <Card className="w-[500px] fixed right-4 bottom-4 z-10 shadow-lg shadow-zinc-900">
      <CardHeader>
        <CardTitle>Give us Feedback</CardTitle>
        <CardDescription>
          Sweep Search is new so we&apos;re actively trying to improve it for
          developers like you.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form>
          <div className="grid w-full items-center gap-4">
            <div className="flex flex-col space-y-1.5">
              <Label htmlFor="feedback">
                How can we improve Sweep Search for you?
              </Label>
              <Textarea
                id="feedback"
                value={feedback}
                onChange={(e) => setFeedback(e.target.value!)}
                placeholder="E.g. I would like to upload images to Sweep Search."
              />
            </div>
          </div>
        </form>
      </CardContent>
      <CardFooter className="flex justify-between">
        <Button variant="outline" onClick={handleSurveyDismissed}>
          Cancel
        </Button>
        <Button onClick={handleFeedbackSubmit}>Submit</Button>
      </CardFooter>
    </Card>
  )
}
