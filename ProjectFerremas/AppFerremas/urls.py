from django.urls import path
from . import views
from django.contrib.auth.views import LoginView, LogoutView

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('registro', views.register, name='register'),
    path('carrito', views.Carrito, name='carrito'),
    path('agregar_al_carrito', views.agregar_al_carrito, name='agregar_al_carrito'),
    path('eliminar', views.eliminar_carrito, name='eliminar_carrito'),
    path('tienda/', views.tienda_view, name='tienda'),
    path('pagos/confirmar/', views.confirmar_pago, name='confirmar_pago'),
    path('pagos/iniciar/', views.iniciar_pago, name='iniciar_pago'),
    path('productos/', views.tienda_view, name='lista_productos'),
    path('contacto/', views.pagina_contacto, name='pagina_contacto'),
    path('procesar-contacto/', views.procesar_contacto, name='procesar_contacto'),
] 