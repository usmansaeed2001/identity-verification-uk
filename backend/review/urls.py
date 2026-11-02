from django.urls import path

from review import views

urlpatterns = [
    path("applications", views.ApplicationListView.as_view()),
    path("applications/<uuid:pk>", views.ApplicationDetailView.as_view()),
    path("applications/<uuid:pk>/evidence/<uuid:evidence_id>", views.EvidenceView.as_view()),
    path("applications/<uuid:pk>/review", views.ReviewDecisionView.as_view()),
    path("applications/<uuid:pk>/request-action", views.RequestActionView.as_view()),
]
