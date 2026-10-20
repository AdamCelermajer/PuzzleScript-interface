import { usePins } from '../api/hooks'
import { PinList } from '../components/Pins'
import { ErrorBox, Loading, PageHeader } from '../components/ui'

/** Every pin across runs, newest first. */
export function PinnedView() {
  const pins = usePins()
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-4">
      <PageHeader title="Pinned" subtitle="Moments you kept from run timelines, with your notes. Pin with ☆ on any agent timeline event." />
      {pins.isLoading ? <Loading label="Reading pins…" /> : pins.error ? <ErrorBox error={pins.error} retry={() => pins.refetch()} /> : <PinList pins={pins.data ?? []} showRun />}
    </div>
  )
}
