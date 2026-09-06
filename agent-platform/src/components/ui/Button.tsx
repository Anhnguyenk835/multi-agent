import type { ButtonHTMLAttributes } from 'react'
import { classNames } from '../../lib/classNames'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md'
  block?: boolean
}

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean
  label: string
}

export function Button({ className, variant = 'primary', size = 'md', block = false, type = 'button', ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={classNames('ui-button', `ui-button--${variant}`, size === 'sm' && 'ui-button--sm', block && 'ui-button--block', className)}
      {...props}
    />
  )
}

export function IconButton({ active = false, className, label, title = label, type = 'button', ...props }: IconButtonProps) {
  return (
    <button
      type={type}
      className={classNames('ui-icon-button', active && 'ui-icon-button--active', className)}
      aria-label={label}
      title={title}
      {...props}
    />
  )
}
