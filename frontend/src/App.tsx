import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'

import { useMe } from './api/hooks'
import { Layout } from './components/Layout'
import { Alert, PageLoader } from './components/ui'
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from './pages/auth'
import { ApplyIndex, StatusPage } from './pages/driver/shell'
import {
  ConsentStep,
  DocumentStep,
  LicenceStep,
  ProfileStep,
  ReviewStep,
  RightToWorkStep,
  SelfieStep,
} from './pages/driver/steps'
import { StaffDetailPage } from './pages/staff/detail'
import { StaffListPage } from './pages/staff/list'

/** Sends people to sign in, and keeps drivers and reviewers in their own areas. */
function Guard({ role, children }: { role: 'driver' | 'reviewer'; children: ReactNode }) {
  const { data: me, isLoading, error } = useMe()
  const location = useLocation()
  if (isLoading) return <Layout><PageLoader /></Layout>
  if (error) return <Layout><Alert tone="error">{error.message}</Alert></Layout>
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (role === 'reviewer' && !me.is_reviewer) return <Navigate to={me.is_staff ? '/login' : '/apply'} replace />
  if (role === 'driver' && me.is_staff) return <Navigate to="/staff" replace />
  return <>{children}</>
}

function Home() {
  const { data: me, isLoading } = useMe()
  if (isLoading) return <Layout><PageLoader /></Layout>
  if (!me) return <Navigate to="/login" replace />
  return <Navigate to={me.is_staff ? '/staff' : '/apply'} replace />
}

const driver = (page: ReactNode) => <Guard role="driver">{page}</Guard>
const reviewer = (page: ReactNode) => <Guard role="reviewer">{page}</Guard>

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route path="/apply" element={driver(<ApplyIndex />)} />
      <Route path="/apply/profile" element={driver(<ProfileStep />)} />
      <Route path="/apply/consent" element={driver(<ConsentStep />)} />
      <Route path="/apply/document" element={driver(<DocumentStep />)} />
      <Route path="/apply/selfie" element={driver(<SelfieStep />)} />
      <Route path="/apply/right_to_work" element={driver(<RightToWorkStep />)} />
      <Route path="/apply/licence" element={driver(<LicenceStep />)} />
      <Route path="/apply/review" element={driver(<ReviewStep />)} />
      <Route path="/apply/status" element={driver(<StatusPage />)} />

      <Route path="/staff" element={reviewer(<StaffListPage />)} />
      <Route path="/staff/applications/:id" element={reviewer(<StaffDetailPage />)} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
