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
    sucursales_api_url = "https://apiferremas-production.up.railway.app/apiferremas/sucursales/todas/" 

    productos_data = []
    categorias_data = []
    sucursales_data = [] 
    error_api_productos = None
    error_api_categorias = None
    error_api_sucursales = None 

    unique_id = request.session.session_key
    if not unique_id:
        request.session.create()
        unique_id = request.session.session_key

    try:
        # --- Obtener Productos ---
        logger.info(f"Intentando obtener productos de: {productos_api_url}")
        prod_response = requests.get(productos_api_url, timeout=10)
        if prod_response.ok:
            productos_data = prod_response.json()
            logger.info(f"Datos JSON de productos obtenidos. Número: {len(productos_data)}")
            for producto in productos_data:
                # producto['precio_display'] = producto.get('valor', "Consultar") # Usa 'valor' si existe
                producto['precio_form'] = producto.get('valor', 0) # Usa 'valor' si existe
                if not producto.get('descripcion'):
                    producto['descripcion'] = f"{producto.get('nombre', 'Producto')} - {producto.get('marca', '')}"
                if not producto.get('url_imagen'):
                    producto['url_imagen'] = 'https://placehold.co/600x400/transparent/F00'
        else:
            logger.error(f"Error al obtener productos. Código: {prod_response.status_code}")
            error_api_productos = f"No se pudieron cargar los productos (Error: {prod_response.status_code})."

        # --- Obtener Categorías ---
        logger.info(f"Intentando obtener categorías de: {categorias_api_url}")
        cat_response = requests.get(categorias_api_url, timeout=5)
        if cat_response.ok:
            categorias_data = cat_response.json()
            logger.info(f"Datos JSON de categorías obtenidos. Número: {len(categorias_data)}")
        else:
            logger.warning(f"Error al obtener categorías. Código: {cat_response.status_code}")
            error_api_categorias = f"No se pudieron cargar las categorías (Error: {cat_response.status_code})."

        # --- Obtener Sucursales ---
        logger.info(f"Intentando obtener sucursales de: {sucursales_api_url}")
        suc_response = requests.get(sucursales_api_url, timeout=5)
        if suc_response.ok:
            sucursales_data = suc_response.json()
            logger.info(f"Datos JSON de sucursales obtenidos. Número: {len(sucursales_data)}")
        else:
            logger.warning(f"Error al obtener sucursales. Código: {suc_response.status_code}")
            error_api_sucursales = f"No se pudieron cargar las sucursales (Error: {suc_response.status_code})."

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión al intentar acceder a las APIs: {e}", exc_info=True)
        if error_api_productos is None: error_api_productos = "Error de conexión al cargar productos."
        if error_api_categorias is None: error_api_categorias = "Error de conexión al cargar categorías."
        if error_api_sucursales is None: error_api_sucursales = "Error de conexión al cargar sucursales."
    except Exception as e:
        logger.error(f"Error inesperado procesando datos de API: {e}", exc_info=True)
        if error_api_productos is None: error_api_productos = "Ocurrió un error al procesar los productos."
        if error_api_categorias is None: error_api_categorias = "Ocurrió un error al procesar las categorías."
        if error_api_sucursales is None: error_api_sucursales = "Ocurrió un error al procesar las sucursales."

    context = {
        'productos': productos_data,
        'categorias': categorias_data,
        'sucursales': sucursales_data, 
        'unique_id': unique_id,
        'error_api_productos': error_api_productos,
        'error_api_categorias': error_api_categorias,
        'error_api_sucursales': error_api_sucursales, 
    }
    return render(request, 'web/tienda.html', context)

def pagina_contacto(request):
    """
    Vista para mostrar el formulario de contacto.
    """
    # Aquí podrías pasar un formulario de Django si lo usas,
    # pero para un textarea simple no es estrictamente necesario para el render inicial.
    return render(request, 'web/contacto.html') # Asegúrate que la ruta sea correcta

def procesar_contacto(request):
    if request.method == 'POST':
        mensaje_usuario = request.POST.get('mensaje')
        api_url_contacto = "https://apiferremas-production.up.railway.app/apiferremas/contacto/contacto"

        if not mensaje_usuario:
            messages.error(request, 'Por favor, escribe un mensaje antes de enviar.')
            return redirect('pagina_contacto')

        # Determinar nombre y correo del cliente
        nombre_cliente = "Cliente Anónimo"
        correo_cliente = "anonimo@ferremas.com" # Placeholder

        if request.user.is_authenticated:
            nombre_cliente = request.user.get_full_name()
            if not nombre_cliente: # Si get_full_name está vacío
                nombre_cliente = request.user.username
            correo_cliente = request.user.email
            if not correo_cliente: # Si el usuario no tiene email registrado
                correo_cliente = f"{request.user.username}@ferremas-placeholder.com"

        # Preparar el cuerpo (payload) para la API
        payload = {
            "nombre_cliente": nombre_cliente,
            "correo_cliente": correo_cliente,
            "mensaje": mensaje_usuario
        }

        try:
            # Realizar la petición POST a la API
            # Es buena idea añadir headers y un timeout
            headers = {'Content-Type': 'application/json'}
            response = requests.post(api_url_contacto, json=payload, headers=headers, timeout=10)

            # Verificar si la petición fue exitosa (código 2xx)
            response.raise_for_status() # Lanza una excepción para errores HTTP 4xx/5xx

            # Procesar la respuesta de la API (opcional, pero bueno para confirmar)
            api_response_data = response.json()
            if api_response_data.get("status") == "ok":
                messages.success(request, api_response_data.get("mensaje", "¡Gracias por tu mensaje! Lo hemos recibido."))
            else:
                # Si la API devuelve un status que no es "ok" pero no es un error HTTP
                error_msg = api_response_data.get("mensaje", "Hubo un problema al registrar tu mensaje en el sistema externo.")
                messages.error(request, error_msg)
                # Podrías querer loggear api_response_data aquí para depuración

        except requests.exceptions.HTTPError as e:
            # Errores HTTP devueltos por la API (4xx, 5xx)
            error_detail = f"Error de la API ({e.response.status_code})"
            try:
                # Intenta obtener más detalles del cuerpo de la respuesta de error de la API
                api_error_data = e.response.json()
                error_detail += f": {api_error_data.get('mensaje') or api_error_data.get('detail') or e.response.text}"
            except ValueError: # Si la respuesta de error no es JSON
                error_detail += f": {e.response.text[:200]}" # Muestra parte del texto
            messages.error(request, f'Hubo un error al enviar tu mensaje al sistema. {error_detail}')
            # logger.error(f"Error HTTP al llamar a API de contacto: {e.response.status_code} - {e.response.text}")

        except requests.exceptions.RequestException as e:
            # Errores de conexión, timeout, etc.
            messages.error(request, f'Hubo un problema de conexión al intentar enviar tu mensaje: {e}. Por favor, inténtalo más tarde.')
            # logger.error(f"Error de conexión al llamar a API de contacto: {e}")

        except Exception as e:
            # Otros errores inesperados
            messages.error(request, f'Ocurrió un error inesperado: {e}. Por favor, inténtalo de nuevo.')
            # logger.error(f"Error inesperado en procesar_contacto: {e}", exc_info=True)

        return redirect('pagina_contacto') # Redirige de nuevo a la página de contacto

    # Si no es POST, redirigir a la página de contacto
    return redirect('pagina_contacto')


# VISTAS.
def inicio(request):
    context = {}
    return render(request, 'web/inicio.html', context)

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
    

from django.core.cache import cache

def obtener_tipo_cambio():
    rate = cache.get('usd_clp_rate')
    if not rate:
        try:
            response = requests.get("https://apiferremas-production.up.railway.app/apiferremas/currency/exchange-rate", timeout=5)
            if response.ok:
                rate = response.json().get('rate', 0)
                cache.set('usd_clp_rate', rate, timeout=3600)  # Cache por 1 hora
        except requests.exceptions.RequestException:
            rate = 0
    return rate