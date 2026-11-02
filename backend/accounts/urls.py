from django.urls import path

from accounts import views

urlpatterns = [
    path("csrf", views.CsrfView.as_view()),
    path("me", views.MeView.as_view()),
    path("register", views.RegisterView.as_view()),
    path("login", views.LoginView.as_view()),
    path("logout", views.LogoutView.as_view()),
    path("verify-email", views.VerifyEmailView.as_view()),
    path("verify-email/resend", views.ResendVerificationView.as_view()),
    path("password-reset", views.PasswordResetView.as_view()),
    path("password-reset/confirm", views.PasswordResetConfirmView.as_view()),
]
