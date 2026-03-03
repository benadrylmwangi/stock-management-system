from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('home/', views.home, name='home'),
    path('pricing/', views.pricing, name='pricing'),
    path('sales/', views.sales, name='sales'),
    path('stock/', views.stock, name='stock'),
    path('aboutus/', views.aboutus, name='aboutus'),
    path('resources/', views.resources, name='resources'),
    path('features/', views.features, name='features'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
