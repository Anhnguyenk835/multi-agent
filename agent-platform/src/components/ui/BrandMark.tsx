export default function BrandMark({ className = '' }: { className?: string }) {
  return (
    <span className={`ui-brand-mark ${className}`.trim()} aria-hidden="true">
      <span />
      <span />
      <span />
      <i />
      <i />
    </span>
  )
}
