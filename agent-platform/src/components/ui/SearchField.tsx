import { Search } from 'lucide-react'
import type { InputHTMLAttributes } from 'react'

type SearchFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  className?: string
  label?: string
  shortcut?: string
}

export default function SearchField({ className = '', label = 'Search', shortcut, ...props }: SearchFieldProps) {
  return (
    <label className={`ui-search-field ${className}`.trim()}>
      <Search size={16} />
      <input aria-label={label} {...props} />
      {shortcut && <kbd>{shortcut}</kbd>}
    </label>
  )
}
