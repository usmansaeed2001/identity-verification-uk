import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'

import { api, fieldError } from '../api/client'
import { keys } from '../api/hooks'
import type { Me } from '../api/types'
import { Layout } from '../components/Layout'
import { Alert, Button, Card, Field, PageLoader } from '../components/ui'
import { passwordSchema } from '../lib/validation'

function AuthPage({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <Layout>
      <Card className="mx-auto max-w-md">
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {intro && <div className="mt-2 text-slate-600">{intro}</div>}
        <div className="mt-6">{children}</div>
      </Card>
    </Layout>
  )
}

const credentials = z.object({
  email: z.email('Enter an email address, like name@example.com.'),
  password: z.string().min(1, 'Enter your password.'),
})
type Credentials = z.infer<typeof credentials>

function useSignedIn() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return (me: Me) => {
    queryClient.setQueryData(keys.me, me)
    navigate(me.is_staff ? '/staff' : '/apply', { replace: true })
  }
}

export function LoginPage() {
  const signedIn = useSignedIn()
  const form = useForm<Credentials>({ resolver: zodResolver(credentials) })
  const login = useMutation({
    mutationFn: (body: Credentials) => api<Me>('/api/auth/login', { method: 'POST', body }),
    onSuccess: signedIn,
  })
  const { errors } = form.formState
  return (
    <AuthPage title="Sign in" intro="Carry on with your driver application.">
      <form noValidate onSubmit={form.handleSubmit((v) => login.mutate(v))} className="space-y-5">
        {login.error && <Alert tone="error">{login.error.message}</Alert>}
        <Field label="Email address" type="email" autoComplete="email" error={errors.email?.message} {...form.register('email')} />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...form.register('password')}
        />
        <Button type="submit" block loading={login.isPending}>
          Sign in
        </Button>
      </form>
      <div className="mt-6 flex flex-col gap-3 text-sm sm:flex-row sm:justify-between">
        <Link to="/register" className="font-semibold text-brand-700 underline">
          New driver? Create an account
        </Link>
        <Link to="/forgot-password" className="text-brand-700 underline">
          Forgotten your password?
        </Link>
      </div>
    </AuthPage>
  )
}

const registration = z.object({ email: credentials.shape.email, password: passwordSchema })

export function RegisterPage() {
  const signedIn = useSignedIn()
  const form = useForm<Credentials>({ resolver: zodResolver(registration) })
  const register = useMutation({
    mutationFn: (body: Credentials) => api<Me>('/api/auth/register', { method: 'POST', body }),
    onSuccess: signedIn,
  })
  const { errors } = form.formState
  return (
    <AuthPage
      title="Become a driver"
      intro="Create an account to start your application. It takes about 10 minutes and you can stop and come back."
    >
      <form noValidate onSubmit={form.handleSubmit((v) => register.mutate(v))} className="space-y-5">
        {register.error && !fieldError(register.error, 'password') && <Alert tone="error">{register.error.message}</Alert>}
        <Field label="Email address" type="email" autoComplete="email" error={errors.email?.message} {...form.register('email')} />
        <Field
          label="Create a password"
          hint="At least 10 characters. Avoid common words."
          type="password"
          autoComplete="new-password"
          error={errors.password?.message ?? fieldError(register.error, 'password')}
          {...form.register('password')}
        />
        <Button type="submit" block loading={register.isPending}>
          Create account
        </Button>
      </form>
      <p className="mt-6 text-sm">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-brand-700 underline">
          Sign in
        </Link>
      </p>
    </AuthPage>
  )
}

export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const queryClient = useQueryClient()
  const verify = useMutation({
    mutationFn: (token: string) => api('/api/auth/verify-email', { method: 'POST', body: { token } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.me }),
  })
  const sent = useRef(false)
  useEffect(() => {
    if (sent.current) return
    sent.current = true
    verify.mutate(params.get('token') ?? '')
  }, [params, verify])

  return (
    <AuthPage title="Confirm your email">
      {verify.isPending && <PageLoader />}
      {verify.isSuccess && (
        <div className="space-y-5">
          <Alert tone="success">Your email address is confirmed.</Alert>
          <Link to="/" className="inline-flex min-h-12 w-full items-center justify-center rounded-xl bg-brand-700 font-semibold text-white">
            Carry on
          </Link>
        </div>
      )}
      {verify.isError && <Alert tone="error">{verify.error.message}</Alert>}
    </AuthPage>
  )
}

export function ForgotPasswordPage() {
  const form = useForm<{ email: string }>({ resolver: zodResolver(z.object({ email: credentials.shape.email })) })
  const reset = useMutation({
    mutationFn: (body: { email: string }) => api('/api/auth/password-reset', { method: 'POST', body }),
  })
  return (
    <AuthPage title="Reset your password" intro="We'll email you a link to choose a new password.">
      {reset.isSuccess ? (
        <Alert tone="success" title="Check your email">
          If there's an account for that address, the link is on its way. It works once.
        </Alert>
      ) : (
        <form noValidate onSubmit={form.handleSubmit((v) => reset.mutate(v))} className="space-y-5">
          {reset.error && <Alert tone="error">{reset.error.message}</Alert>}
          <Field
            label="Email address"
            type="email"
            autoComplete="email"
            error={form.formState.errors.email?.message}
            {...form.register('email')}
          />
          <Button type="submit" block loading={reset.isPending}>
            Send link
          </Button>
        </form>
      )}
    </AuthPage>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const form = useForm<{ password: string }>({ resolver: zodResolver(z.object({ password: passwordSchema })) })
  const confirm = useMutation({
    mutationFn: (password: string) =>
      api('/api/auth/password-reset/confirm', {
        method: 'POST',
        body: { uid: params.get('uid'), token: params.get('token'), password },
      }),
  })
  return (
    <AuthPage title="Choose a new password">
      {confirm.isSuccess ? (
        <div className="space-y-5">
          <Alert tone="success">Your password has been changed.</Alert>
          <Link to="/login" className="inline-flex min-h-12 w-full items-center justify-center rounded-xl bg-brand-700 font-semibold text-white">
            Sign in
          </Link>
        </div>
      ) : (
        <form noValidate onSubmit={form.handleSubmit((v) => confirm.mutate(v.password))} className="space-y-5">
          {confirm.error && !fieldError(confirm.error, 'password') && <Alert tone="error">{confirm.error.message}</Alert>}
          <Field
            label="New password"
            hint="At least 10 characters."
            type="password"
            autoComplete="new-password"
            error={form.formState.errors.password?.message ?? fieldError(confirm.error, 'password')}
            {...form.register('password')}
          />
          <Button type="submit" block loading={confirm.isPending}>
            Save password
          </Button>
        </form>
      )}
    </AuthPage>
  )
}
