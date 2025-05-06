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
import requests
from django.conf import settings
import logging 

# Configura un logger básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tienda
def tienda_view(request):
    api_url = "https://apiferremas-production.up.railway.app/apiferremas/productos/todos"
    productos_data = [] # Inicializa como lista vacía por si falla la API
    error_api = None    # Para guardar un mensaje de error

    # Genera un unique_id para el carrito si es necesario (esto depende de tu lógica de carrito)
    # Ejemplo: podrías usar la sesión del usuario o generar uno si no existe
    unique_id = request.session.session_key
    if not unique_id:
        request.session.create()
        unique_id = request.session.session_key

    try:
        response = requests.get(api_url, timeout=10) # Agrega un timeout
        response.raise_for_status() # Lanza una excepción para errores HTTP (4xx o 5xx)
        productos_data = response.json()
        logger.info(f"Se obtuvieron {len(productos_data)} productos de la API.")

        # --- ¡IMPORTANTE! MANEJO DE DATOS FALTANTES ---
        # La API no devuelve precio. Debes decidir cómo manejarlo.
        # Opciones:
        # 1. ¿Hay otra API para obtener precios?
        # 2. ¿Tienes los precios en tu base de datos local y los combinas?
        # 3. Poner un precio por defecto o mensaje "Consultar precio".
        # Aquí agregaremos un precio de ejemplo y una descripción por defecto para ilustrar.
        # DEBES AJUSTAR ESTO A TU LÓGICA REAL.
        for producto in productos_data:
            if not producto.get('valor'):
                producto['valor'] = 0 # Valor para el form (o dejar vacío si no se agrega al carrito sin precio)
            if not producto.get('descripcion'): # Si la descripción viene vacía
                 producto['descripcion'] = f"{producto.get('nombre', 'Producto')} - {producto.get('marca', '')}"
            if not producto.get('url_imagen'): # Si la URL de la imagen es null
                # Usa una imagen placeholder local o de internet
                producto['url_imagen'] = 'https://placehold.co/600x400?text=Imagen+No+Disponible' # Ejemplo de placeholder

    except requests.exceptions.RequestException as e:
        logger.error(f"Error al conectar con la API de productos: {e}")
        error_api = "No se pudieron cargar los productos en este momento. Inténtalo más tarde."
        # Puedes decidir si mostrar la página vacía o una página de error específica.

    context = {
        'productos': productos_data,
        'unique_id': unique_id, # Pasa el unique_id al template
        'error_api': error_api, # Pasa el mensaje de error (si existe)
    }
    return render(request, 'web/tienda.html', context) 

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