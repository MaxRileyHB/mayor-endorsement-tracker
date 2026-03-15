/* Reusable skeleton components */

function Pulse({ className }) {
  return <div className={`animate-pulse bg-gray-200 rounded ${className}`} />
}

export function SkeletonCard() {
  return (
    <div className="bg-white border border-gray-100 rounded-lg p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Pulse className="w-4 h-4 rounded shrink-0" />
        <Pulse className="h-4 flex-1" />
        <Pulse className="h-4 w-8 shrink-0" />
      </div>
      <Pulse className="h-3 w-3/4 ml-6" />
      <Pulse className="h-3 w-1/2 ml-6" />
      <div className="flex gap-1 ml-6 mt-1">
        <Pulse className="h-4 w-16" />
        <Pulse className="h-4 w-12" />
      </div>
    </div>
  )
}

export function SkeletonKanban() {
  const cols = [4, 2, 3, 1, 5, 2]
  return (
    <div className="flex gap-3 overflow-x-auto pb-4 h-full">
      {cols.map((count, i) => (
        <div key={i} className="flex-none w-56">
          <div className="flex items-center gap-2 mb-2 px-1">
            <Pulse className="h-5 w-24 rounded-full" />
            <Pulse className="h-4 w-4" />
          </div>
          <div className="flex flex-col gap-2">
            {Array.from({ length: count }).map((_, j) => (
              <SkeletonCard key={j} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function SkeletonTableRows({ count = 15 }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <tr key={i} className={`border-t border-gray-100 ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}`}>
          <td className="p-2 w-8"><Pulse className="w-4 h-4 rounded" /></td>
          <td className="p-2"><Pulse className="h-4 w-28" /></td>
          <td className="p-2"><Pulse className="h-4 w-24" /></td>
          <td className="p-2"><Pulse className="h-4 w-20" /></td>
          <td className="p-2"><Pulse className="h-4 w-10" /></td>
          <td className="p-2"><Pulse className="h-5 w-6 rounded-full" /></td>
          <td className="p-2"><Pulse className="h-5 w-20 rounded-full" /></td>
          <td className="p-2"><Pulse className="h-4 w-12" /></td>
          <td className="p-2"><Pulse className="h-4 w-16" /></td>
        </tr>
      ))}
    </>
  )
}

export function SkeletonDraftCard() {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100">
        <Pulse className="w-4 h-4 rounded shrink-0" />
        <div className="flex-1 space-y-1.5">
          <div className="flex gap-2">
            <Pulse className="h-4 w-24" />
            <Pulse className="h-4 w-8" />
            <Pulse className="h-4 w-16" />
          </div>
          <Pulse className="h-3 w-40" />
        </div>
        <div className="flex gap-2 shrink-0">
          <Pulse className="h-7 w-16 rounded" />
          <Pulse className="h-7 w-14 rounded" />
          <Pulse className="h-7 w-20 rounded" />
        </div>
      </div>
      <div className="px-4 py-2 border-b border-gray-100 bg-gray-50">
        <Pulse className="h-3 w-3/4" />
      </div>
      <div className="px-4 py-3 space-y-2">
        <Pulse className="h-3 w-full" />
        <Pulse className="h-3 w-5/6" />
        <Pulse className="h-3 w-4/5" />
        <Pulse className="h-3 w-full" />
        <Pulse className="h-3 w-2/3" />
      </div>
    </div>
  )
}

export function SkeletonSection({ lines = 3 }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Pulse key={i} className={`h-3 ${i % 3 === 2 ? 'w-2/3' : i % 3 === 1 ? 'w-5/6' : 'w-full'}`} />
      ))}
    </div>
  )
}
