import { PrValidationStatus } from '@/lib/types'
import { FaCheck, FaTimes, FaTimesCircle, FaCircle } from 'react-icons/fa'
import AutoScrollArea from '@/components/ui/autoscroll'
import { Button } from '@/components/ui/button'

const PrValidationStatusDisplay = ({
  status,
}: {
  status: PrValidationStatus
}) => {
  // TODO: make these collapsible

  return (
    <div className="flex justify-start">
      <div className="rounded-xl bg-zinc-800 w-full">
        <h2 className="font-bold text-sm">
          {status.status === 'success' ? (
            <FaCheck
              className="text-green-500 inline mr-2 text-sm"
              style={{ marginTop: -2 }}
            />
          ) : status.status === 'failure' ? (
            <FaTimes
              className="text-red-500 inline mr-2 text-sm"
              style={{ marginTop: -2 }}
            />
          ) : status.status === 'cancelled' ? (
            <FaTimesCircle
              className="text-zinc-500 inline mr-2 text-sm"
              style={{ marginTop: -2 }}
            />
          ) : (
            <FaCircle
              className={
                {
                  pending: 'text-zinc-500',
                  running: 'text-yellow-500',
                }[status.status] + ' inline mr-2 text-sm'
              }
              style={{ marginTop: -2 }}
            />
          )}
          {status.message} - {status.containerName}
        </h2>
        {status.stdout && (
          <AutoScrollArea className="max-h-[500px] overflow-y-auto mt-4">
            <pre className="whitespace-pre-wrap text-sm bg-zinc-900 p-4 rounded-lg">
              {status.stdout}
            </pre>
          </AutoScrollArea>
        )}
      </div>
    </div>
  )
}

export default function PrValidationStatusesDisplay({
  statuses,
  fixPrValidationErrors = () => {},
}: {
  statuses: PrValidationStatus[]
  fixPrValidationErrors: any
}) {
  return (
    <div className="flex justify-start mb-4">
      <div className="rounded-xl p-4 bg-zinc-800 w-[80%] space-y-4">
        {statuses.length == 0 ? (
          <p className="text-zinc-500 font-bold">
            I&apos;m monitoring the CI/CD pipeline to validate this PR. This may
            take a few minutes.
          </p>
        ) : (
          <>
            {statuses.map((status, index) => (
              <PrValidationStatusDisplay key={index} status={status} />
            ))}
            {statuses.some((status) => status.status == 'failure') ? (
              <>
                <p className="text-red-500 font-bold">
                  Some tests have failed.
                </p>
                <Button variant="primary" onClick={fixPrValidationErrors}>
                  Fix errors
                </Button>
              </>
            ) : statuses.some(
                (status) =>
                  status.status == 'pending' || status.status == 'running'
              ) ? (
              <p className="text-yellow-500 font-bold">
                Some tests are still running. Currently checking every 10s.
              </p>
            ) : (
              <p className="text-green-500 font-bold">All tests have passed.</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}