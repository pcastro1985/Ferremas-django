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
    productos_api_url = "https://apiferremas-production.up.railway.app/apiferremas/productos/todos"
    categorias_api_url = "https://apiferremas-production.up.railway.app/apiferremas/productos/categorias" 
    productos_data = [] # Inicializa como lista vacía por si falla la API
    categorias_data = []
    error_api_productos = None
    error_api_categorias = None

    # Genera un unique_id para el carrito si es necesario (esto depende de tu lógica de carrito)
    # Ejemplo: podrías usar la sesión del usuario o generar uno si no existe
    unique_id = request.session.session_key
    if not unique_id:
        request.session.create()
        unique_id = request.session.session_key

    try:
        # --- Obtener Productos ---
        logger.info(f"Intentando obtener productos de: {productos_api_url}")
        prod_response = requests.get(productos_api_url, timeout=10)
        # Verifica si la respuesta de productos fue exitosa ANTES de intentar parsear JSON
        if prod_response.ok:
            productos_data = prod_response.json()
            logger.info(f"Datos JSON de productos obtenidos. Número: {len(productos_data)}")
            # --- Procesamiento de productos (precio, imagen, etc.) ---
            for producto in productos_data:
                producto['precio_display'] = "Consultar" # Precio por defecto
                producto['precio_form'] = 0
                if not producto.get('descripcion'):
                    producto['descripcion'] = f"{producto.get('nombre', 'Producto')} - {producto.get('marca', '')}"
                if not producto.get('url_imagen'):
                    producto['url_imagen'] = 'https://via.placeholder.com/200x200.png?text=Sin+Imagen'
        else:
            # Si la API de productos falla, registra el error y asigna mensaje
            logger.error(f"Error al obtener productos. Código: {prod_response.status_code}, Respuesta: {prod_response.text[:200]}")
            error_api_productos = f"No se pudieron cargar los productos (Error: {prod_response.status_code})."
            # Opcional: podrías lanzar una excepción si fallar al cargar productos debe detener todo
            # prod_response.raise_for_status()

        # --- Obtener Categorías (Intentar incluso si fallaron los productos) ---
        logger.info(f"Intentando obtener categorías de: {categorias_api_url}")
        cat_response = requests.get(categorias_api_url, timeout=5) # Timeout más corto para categorías?
        if cat_response.ok:
            categorias_data = cat_response.json()
            logger.info(f"Datos JSON de categorías obtenidos. Número: {len(categorias_data)}")
        else:
            # Si la API de categorías falla, solo registra y asigna mensaje de error
            logger.warning(f"Error al obtener categorías. Código: {cat_response.status_code}, Respuesta: {cat_response.text[:200]}")
            error_api_categorias = f"No se pudieron cargar las categorías (Error: {cat_response.status_code})."
            # No lanzamos excepción aquí, para que la página cargue aunque falten categorías

    except requests.exceptions.RequestException as e:
        # Error de conexión (afecta a la petición que falló)
        logger.error(f"Error de conexión al intentar acceder a las APIs: {e}", exc_info=True)
        # Asigna errores si aún no tienen uno por respuesta no-OK
        if error_api_productos is None:
             error_api_productos = "Error de conexión al cargar productos."
        if error_api_categorias is None:
             error_api_categorias = "Error de conexión al cargar categorías."
    except Exception as e:
        # Otros errores (ej. JSON inválido, error inesperado)
        logger.error(f"Error inesperado procesando datos de API: {e}", exc_info=True)
        # Asigna errores genéricos si no hay uno específico
        if error_api_productos is None:
             error_api_productos = "Ocurrió un error al procesar los productos."
        if error_api_categorias is None:
             error_api_categorias = "Ocurrió un error al procesar las categorías."


    context = {
        'productos': productos_data,
        'categorias': categorias_data, # <--- Pasa las categorías al contexto
        'unique_id': unique_id,
        'error_api_productos': error_api_productos, # Pasa errores específicos
        'error_api_categorias': error_api_categorias,
    }
    logger.info(f"Renderizando plantilla 'web/tienda.html'. Productos: {len(productos_data)}, Categorías: {len(categorias_data)}")
    return render(request, 'web/tienda.html', context)

# VISTAS.
def inicio(request):
    context = {}
    return render(request, 'web/inicio.html', context)

# def tienda(request):
#     return render(request, 'web/tienda.html')

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