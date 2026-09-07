export default function BrandMark({ className = '' }: { className?: string }) {
  return (
    <span
      className={`relative block size-[34px] shrink-0 rounded-lg bg-blue-600 ${className}`.trim()}
      aria-hidden="true"
    >
      <span className="absolute top-2 left-[7px] size-[5px] rounded-full border-[1.5px] border-white" />
      <span className="absolute top-2 right-[7px] size-[5px] rounded-full border-[1.5px] border-white" />
      <span className="absolute bottom-[7px] left-3.5 size-[5px] rounded-full border-[1.5px] border-white" />
      <i className="absolute top-[11px] left-[11px] h-px w-3 bg-white/80" />
      <i className="absolute top-[13px] left-2.5 h-px w-3 origin-left rotate-[57deg] bg-white/80" />
    </span>
  )
}
