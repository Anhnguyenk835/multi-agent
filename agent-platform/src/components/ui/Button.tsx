import type { ButtonHTMLAttributes } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md'
  block?: boolean
}

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean
  label: string
}

export function Button({
  className,
  variant = 'primary',
  size = 'md',
  block = false,
  type = 'button',
  ...props
}: ButtonProps) {
  const variantClass = {
    primary: 'bg-blue-600 text-white shadow-sm hover:bg-blue-700',
    secondary: 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:text-slate-950',
    ghost: 'bg-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-950',
  }[variant]

  return (
    <button
      type={type}
      className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-transparent px-3 text-xs font-semibold whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-blue-500/15 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 ${variantClass} ${size === 'sm' ? 'min-h-8 px-2.5 text-[11px]' : ''} ${block ? 'w-full' : ''} ${className ?? ''}`}
      {...props}
    />
  )
}

export function IconButton({
  active = false,
  className,
  label,
  title = label,
  type = 'button',
  ...props
}: IconButtonProps) {
  return (
    <button
      type={type}
      className={`grid size-8 shrink-0 place-items-center rounded-md border-0 bg-transparent text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-blue-500/15 ${active ? 'bg-blue-50 text-blue-600' : ''} ${className ?? ''}`}
      aria-label={label}
      title={title}
      {...props}
    />
  )
}
