from django.urls import path

from onboarding import views

urlpatterns = [
    path("application", views.ApplicationView.as_view()),
    path("profile", views.ProfileView.as_view()),
    path("consent", views.ConsentView.as_view()),
    path("identity/document", views.DocumentView.as_view()),
    path("identity/selfie", views.SelfieView.as_view()),
    path("right-to-work", views.RightToWorkView.as_view()),
    path("licence", views.LicenceView.as_view()),
    path("licence/dqc", views.DqcCardView.as_view()),
    path("submit", views.SubmitView.as_view()),
]
