import { forwardRef, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react'

const cx = (...classes: (string | false | null | undefined)[]) => classes.filter(Boolean).join(' ')

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  loading?: boolean
  block?: boolean
}

export function Button({ variant = 'primary', loading, block, className, children, disabled, ...rest }: ButtonProps) {
  const styles = {
    primary: 'bg-brand-700 text-white hover:bg-brand-800 disabled:bg-slate-300',
    secondary: 'bg-white text-brand-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400',
    danger: 'bg-red-700 text-white hover:bg-red-800 disabled:bg-slate-300',
    ghost: 'text-brand-700 hover:bg-brand-50 disabled:text-slate-400',
  }[variant]
  return (
    <button
      type="button"
      className={cx(
        'inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-5 text-base font-semibold transition-colors disabled:cursor-not-allowed',
        styles,
        block && 'w-full',
        className,
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <Spinner className="size-5" />}
      {children}
    </button>
  )
}

export function Spinner({ className = 'size-6' }: { className?: string }) {
  return (
    <svg className={cx('animate-spin', className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: ReactNode; error?: string }

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field({ label, hint, error, className, ...rest }, ref) {
  const id = useId()
  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font-semibold text-slate-800">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-sm text-slate-600">
          {hint}
        </p>
      )}
      <input
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={cx(hint ? `${id}-hint` : null, error ? `${id}-error` : null) || undefined}
        className={cx(
          'mt-2 block min-h-12 w-full rounded-xl border bg-white px-4 text-base shadow-sm placeholder:text-slate-400',
          error ? 'border-red-600' : 'border-slate-300 focus:border-brand-500',
        )}
        {...rest}
      />
      {error && (
        <p id={`${id}-error`} className="mt-2 text-sm font-medium text-red-700">
          {error}
        </p>
      )}
    </div>
  )
})

export function Alert({ tone = 'info', title, children }: { tone?: 'info' | 'error' | 'success' | 'warning'; title?: string; children?: ReactNode }) {
  const styles = {
    info: 'border-brand-500 bg-brand-50 text-brand-900',
    error: 'border-red-600 bg-red-50 text-red-900',
    success: 'border-emerald-600 bg-emerald-50 text-emerald-900',
    warning: 'border-amber-500 bg-amber-50 text-amber-900',
  }[tone]
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={cx('rounded-xl border-l-4 px-4 py-3 text-sm', styles)}>
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={cx(title && 'mt-1')}>{children}</div>}
    </div>
  )
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:p-8', className)}>{children}</div>
}

export function Badge({ tone = 'slate', children }: { tone?: 'slate' | 'green' | 'red' | 'amber' | 'blue' | 'purple'; children: ReactNode }) {
  const styles = {
    slate: 'bg-slate-100 text-slate-700',
    green: 'bg-emerald-100 text-emerald-800',
    red: 'bg-red-100 text-red-800',
    amber: 'bg-amber-100 text-amber-900',
    blue: 'bg-brand-100 text-brand-800',
    purple: 'bg-violet-100 text-violet-800',
  }[tone]
  return <span className={cx('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold', styles)}>{children}</span>
}

export function PageLoader() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center text-brand-700" role="status" aria-label="Loading">
      <Spinner className="size-8" />
    </div>
  )
}

export { cx }
