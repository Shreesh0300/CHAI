import { ArrowUp, ArrowUpRight, Check, MessageCircle, Sparkles } from 'lucide-react'

const workstreams = [
  { name: 'Positioning', status: 'Ready' },
  { name: 'Content', status: 'Drafted' },
  { name: 'Measurement', status: 'In review' },
]

export function CoverWorkspacePreview() {
  return (
    <figure
      id="workspace-showcase"
      aria-labelledby="workspace-preview-caption"
      className="chai-preview rgb-border relative mx-auto w-full max-w-[700px] rounded-[1.7rem] border border-white/10 p-1.5 shadow-[0_32px_110px_rgba(0,0,0,0.5)]"
    >
      <figcaption id="workspace-preview-caption" className="sr-only">
        CHAI workspace preview showing a completed launch plan beside its follow-up chat.
      </figcaption>

      <div className="chai-preview__surface overflow-hidden rounded-[1.3rem] border border-white/10">
        <header className="chai-preview__topbar flex items-center justify-between gap-3 px-3.5 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="chai-preview__icon grid size-8 shrink-0 place-items-center rounded-xl">
              <Sparkles aria-hidden="true" className="size-4" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-[11px] font-semibold tracking-wide">CHAI workspace</p>
              <p className="chai-preview__muted mt-0.5 truncate text-[9px]">Launch planning · just now</p>
            </div>
          </div>
          <span className="chai-preview__status inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[9px] font-medium">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-emerald-300" />
            3 agents working
          </span>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_232px]">
          <section aria-label="Completed work preview" className="min-w-0 p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="chai-preview__muted text-[9px] font-semibold uppercase tracking-[0.16em]">
                Response canvas
              </p>
              <span className="chai-preview__status inline-flex items-center gap-1 rounded-full px-2 py-1 text-[8px] font-medium uppercase tracking-[0.1em]">
                <Check aria-hidden="true" className="size-2.5" />
                Work complete
              </span>
            </div>

            <h2 className="mt-4 max-w-[420px] text-balance text-lg font-semibold leading-tight tracking-[-0.035em] sm:text-[1.35rem]">
              A launch plan with room to move
            </h2>
            <p className="chai-preview__muted mt-2 max-w-[460px] text-[10px] leading-[1.7] sm:text-[11px]">
              Three focused tracks bring the story, content, and measurement plan into one clear view.
            </p>

            <div className="mt-5 grid grid-cols-3 gap-2">
              {workstreams.map((workstream, index) => (
                <div
                  key={workstream.name}
                  className="chai-preview__panel min-w-0 rounded-xl border border-white/5 px-2.5 py-2.5 sm:px-3"
                >
                  <span className="chai-preview__muted block text-[8px] font-medium uppercase tracking-[0.12em]">
                    0{index + 1}
                  </span>
                  <p className="mt-2 truncate text-[9px] font-medium sm:text-[10px]">{workstream.name}</p>
                  <p className="chai-preview__muted mt-1 truncate text-[8px]">{workstream.status}</p>
                </div>
              ))}
            </div>

            <div className="mt-5">
              <div className="flex items-center justify-between gap-3 text-[9px]">
                <span className="chai-preview__muted">Agent coordination</span>
                <span className="font-medium">3 of 3 tracks</span>
              </div>
              <div
                role="img"
                aria-label="All three workstreams are coordinated"
                className="chai-preview__progress-track mt-2 h-1.5 overflow-hidden rounded-full"
              >
                <span className="chai-preview__progress-fill block h-full w-[88%] rounded-full" />
              </div>
            </div>

            <div className="chai-preview__panel mt-5 flex items-center gap-3 rounded-xl border border-white/5 px-3 py-2.5">
              <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-white/5 text-[#b6a8ff]">
                <ArrowUpRight aria-hidden="true" className="size-3.5" />
              </span>
              <div className="min-w-0">
                <p className="chai-preview__muted text-[8px] font-semibold uppercase tracking-[0.12em]">
                  Suggested next step
                </p>
                <p className="mt-1 truncate text-[9px] font-medium">Review the launch timeline</p>
              </div>
            </div>
          </section>

          <aside className="chai-preview__chat min-w-0 border-t border-white/10 p-4 sm:p-5 md:border-l md:border-t-0">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <MessageCircle aria-hidden="true" className="size-3.5 text-[#b6a8ff]" />
                <h3 className="text-[10px] font-semibold">Follow-up chat</h3>
              </div>
              <span aria-hidden="true" className="chai-preview__muted text-[8px]">•••</span>
            </div>

            <div className="mt-5 flex flex-col gap-3">
              <div className="chai-preview__user-bubble ml-auto max-w-[92%] rounded-[1rem] rounded-br-sm px-3 py-2.5 text-[9px] leading-[1.6]">
                Can you map out a launch week for us?
              </div>
              <div className="chai-preview__assistant-bubble max-w-[96%] rounded-[1rem] rounded-bl-sm border border-white/5 px-3 py-2.5 text-[9px] leading-[1.65]">
                <div className="mb-2 flex items-center gap-1.5 text-[8px] font-semibold">
                  <Sparkles aria-hidden="true" className="size-3 text-[#b6a8ff]" />
                  CHAI
                </div>
                I organized the plan into three tracks. Want to expand one?
              </div>
              <div className="chai-preview__muted flex items-center gap-1.5 text-[8px]">
                <span aria-hidden="true" className="chai-preview__pulse size-1.5 rounded-full bg-[#9d8aff]" />
                Ready for your next step
              </div>
            </div>

            <div className="chai-preview__composer mt-5 flex min-h-9 items-center justify-between gap-2 rounded-xl px-2.5 py-1.5">
              <span className="chai-preview__muted truncate text-[8px]">Ask for a refinement...</span>
              <span className="chai-preview__send grid size-6 shrink-0 place-items-center rounded-lg">
                <ArrowUp aria-hidden="true" className="size-3" />
              </span>
            </div>
          </aside>
        </div>
      </div>
    </figure>
  )
}
