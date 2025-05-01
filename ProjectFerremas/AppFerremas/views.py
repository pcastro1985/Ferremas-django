from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.db import IntegrityError
from django.contrib.auth.models import User
from django.contrib import messages
# FROMS CARRITO.
from .models import articulo, carrito
# FROMS TRANSBANK
from django.http import JsonResponse,HttpResponse
from transbank.webpay.webpay_plus.transaction import Transaction, WebpayOptions
import hashlib
from django.conf import settings
from transbank.common.integration_type import IntegrationType
from django.urls import reverse

# VISTAS.
def inicio(request):
    context = {}
    return render(request, 'web/inicio.html', context)

def tienda(request):
    return render(request, 'web/tienda.html')

def Carrito(request):
    articulo = articulo.objects.all()
    total = sum(float(articulo.precio) for articulo in articulo)
    print("Artículos:", articulo)
    print("Total:", total)
    return render(request, 'web/carrito.html', {'articulos': articulo, 'total': total})

def eliminar_carrito(request):
    if request.method == "POST":
        articulo.objects.all().delete()
        return redirect(request.META.get('HTTP_REFERER', 'tienda'))
    return redirect('tienda')


@login_required
def agregar_al_carrito(request):
    if request.method == "POST":
        nombre_articulo = request.POST.get('nombre_articulo')
        precio = request.POST.get('precio')
        carrito_A = carrito.objects.get_or_create(usuario=request.user)
        nuevo_articulo = articulo(nombre_articulo=nombre_articulo, precio=precio)
        nuevo_articulo.save()
        carrito_A.productos.add(nuevo_articulo)
        return redirect(request.META.get('HTTP_REFERER', 'web/tienda.html'))
    return redirect('web/tienda.html')

def register(request):
    if request.method == 'GET':
        return render(request, 'registration/register.html', {'form': UserCreationForm()})
    else:
        if request.POST['password1'] == request.POST['password2']:
            try:
                user = User.objects.create_user(
                    username=request.POST['username'],
                    password=request.POST['password1']
                )
                user.save()
                auth_login(request, user)  # Autenticar al usuario después de registrarse
                messages.success(request, '¡Te has registrado correctamente!')
                return redirect('inicio')
            except IntegrityError:
                return render(request, 'registration/register.html', {
                    'form': UserCreationForm(),
                    'error': 'El usuario ya existe'
                })
        return render(request, 'registration/register.html', {
            'form': UserCreationForm(),
            'error': 'Las contraseñas no coinciden'
        })


# TRANSBANK

def iniciar_pago(request):
    if request.method == "POST":
        carrito_A, creado = carrito.objects.get_or_create(usuario=request.user)
        articulos = carrito_A.productos.all()
        total = sum(articulo.precio for articulo in articulos)
        
        if total > 0:
            session_key = request.session.session_key
            buy_order = hashlib.md5(session_key.encode()).hexdigest()[:26]
            session_id = f"sesion_{session_key}"
            amount = total
            return_url = request.build_absolute_uri(reverse('confirmar_pago'))

            tx = Transaction(WebpayOptions(settings.TRANBANK_COMMERCE_CODE, settings.TRANBANK_API_KEY, IntegrationType.TEST))
            try:
                response = tx.create(buy_order, session_id, amount, return_url)
                if response:
                    return redirect(response['url'] + "?token_ws=" + response['token'])
                else:
                    return HttpResponse("No se recibió respuesta de Transbank.")
            except Exception as e:
                return HttpResponse(f"Error interno: {str(e)}")
        else:
            return HttpResponse("El carrito está vacío.")
    else:
        return HttpResponse("Método no permitido.", status=405)

def confirmar_pago(request):
    token_ws = request.GET.get('token_ws')
    if not token_ws:
        return HttpResponse("Token no proporcionado.")

    try:
        tx = Transaction(WebpayOptions(settings.TRANBANK_COMMERCE_CODE, settings.TRANBANK_API_KEY, IntegrationType.TEST))
        response = tx.commit(token_ws)
        if response and response['status'] == 'AUTHORIZED':

            # Obtener el carrito de la sesión
            carrito = request.session.get('carrito', {})
            
            for producto_id, cantidad in carrito.items():
                producto = articulo.objects.get(id_articulo=producto_id)
                print(f"Producto: {producto.nombre_articulo}, Cantidad: {cantidad}")
            
         

            return render(request, 'web/confirmacion_pago.html', {'response': response})
        else:
            return HttpResponse("No se recibió respuesta de Transbank.")
    except Exception as e:
        return HttpResponse(f"Error interno: {str(e)}")