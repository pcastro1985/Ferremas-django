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
from decimal import Decimal, InvalidOperation 

# Configura un logger básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tienda
def tienda_view(request):
    productos_api_url = "https://apiferremas-production.up.railway.app/apiferremas/productos/todos"
    categorias_api_url = "https://apiferremas-production.up.railway.app/apiferremas/productos/categorias"
    sucursales_api_url = "https://apiferremas-production.up.railway.app/apiferremas/sucursales/todas/" 

    cambio_dolar = obtener_tipo_cambio()
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
                producto['precio_form'] = producto.get('valor', 0)
                 # Calcular precio en dólares para cada producto
                for producto in productos_data:
                    if producto.get('valor') and cambio_dolar:
                        producto['precio_usd'] = round(float(producto['valor']) / cambio_dolar, 2)
                    else:
                        producto['precio_usd'] = None
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
        'cambio_dolar': cambio_dolar, 
    }
    return render(request, 'web/tienda.html', context)

def pagina_contacto(request):
    """
    Vista para mostrar el formulario de contacto.
    """
    return render(request, 'web/contacto.html') 

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
            if not nombre_cliente: 
                nombre_cliente = request.user.username
            correo_cliente = request.user.email
            if not correo_cliente: 
                correo_cliente = f"{request.user.username}@ferremas-placeholder.com"

        # Preparar el cuerpo (payload) para la API
        payload = {
            "nombre_cliente": nombre_cliente,
            "correo_cliente": correo_cliente,
            "mensaje": mensaje_usuario
        }

        try:
            # Realizar la petición POST a la API
            headers = {'Content-Type': 'application/json'}
            response = requests.post(api_url_contacto, json=payload, headers=headers, timeout=10)

            # Verificar si la petición fue exitosa (código 2xx)
            response.raise_for_status() # Lanza una excepción para errores HTTP 4xx/5xx

            # Procesar la respuesta de la API 
            api_response_data = response.json()
            if api_response_data.get("status") == "ok":
                messages.success(request, api_response_data.get("mensaje", "¡Gracias por tu mensaje! Lo hemos recibido."))
            else:
                # Si la API devuelve un status que no es "ok" pero no es un error HTTP
                error_msg = api_response_data.get("mensaje", "Hubo un problema al registrar tu mensaje en el sistema externo.")
                messages.error(request, error_msg)

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

        except requests.exceptions.RequestException as e:
            # Errores de conexión, timeout, etc.
            messages.error(request, f'Hubo un problema de conexión al intentar enviar tu mensaje: {e}. Por favor, inténtalo más tarde.')

        except Exception as e:
            # Otros errores inesperados
            messages.error(request, f'Ocurrió un error inesperado: {e}. Por favor, inténtalo de nuevo.')

        return redirect('pagina_contacto') # Redirige de nuevo a la página de contacto

    # Si no es POST, redirigir a la página de contacto
    return redirect('pagina_contacto')


# VISTAS.
def inicio(request):
    context = {}
    return render(request, 'web/inicio.html', context)

@login_required 
def Carrito(request): 
    articulos_en_carrito = []
    total_carrito = Decimal('0.00')
    total_carrito_usd = Decimal('0.00')
    cambio_dolar = obtener_tipo_cambio()  # Obtener el tipo de cambio

    try:
        carrito_usuario, creado = carrito.objects.get_or_create(usuario=request.user)

        if not creado:
            articulos_en_carrito = carrito_usuario.productos.all()
            for art in articulos_en_carrito:
                total_carrito += art.precio
                # Calcular precio en dólares para cada artículo
                if cambio_dolar:
                    art.precio_usd = round(float(art.precio) / cambio_dolar, 2)
                    total_carrito_usd += Decimal(art.precio_usd)
                else:
                    art.precio_usd = None

    except Exception as e:
        logger.error(f"Error inesperado al obtener el carrito para {request.user.username}: {e}", exc_info=True)
        messages.error(request, "Ocurrió un error al cargar tu carrito. Inténtalo de nuevo.")

    context = {
        'articulos': articulos_en_carrito,
        'total': total_carrito,
        'total_usd': round(total_carrito_usd, 2) if cambio_dolar else None,
        'cambio_dolar': cambio_dolar,
    }
    return render(request, 'web/carrito.html', context)

def eliminar_carrito(request):
    if request.method == "POST":
        articulo.objects.all().delete()
        return redirect(request.META.get('HTTP_REFERER', 'tienda'))
    return redirect('tienda')


@login_required
def agregar_al_carrito(request):
    if request.method == "POST":
        nombre_articulo_str = request.POST.get('nombre_articulo')
        precio_str = request.POST.get('precio')
        # Opcional: id_articulo_api = request.POST.get('id_articulo') si quieres referenciar el producto de la API

        # --- Validación básica ---
        if not nombre_articulo_str or not precio_str:
            messages.error(request, "Faltan datos del producto para agregarlo al carrito.")
            return redirect(request.META.get('HTTP_REFERER', 'tienda')) # Volver a la tienda

        try:
            # Convertir precio a Decimal para asegurar que es un número válido
            # y para consistencia con el DecimalField del modelo
            precio_decimal = Decimal(precio_str)
            if precio_decimal <= 0: # No permitir precios cero o negativos
                messages.warning(request, "El precio del producto no es válido.")
                return redirect(request.META.get('HTTP_REFERER', 'tienda'))
        except (ValueError, TypeError, InvalidOperation):
            messages.error(request, "El precio del producto es inválido.")
            return redirect(request.META.get('HTTP_REFERER', 'tienda'))

        # --- Obtener o crear el carrito del usuario ---
        # Desempaquetar la tupla devuelta por get_or_create:
        carrito_obj, creado = carrito.objects.get_or_create(usuario=request.user)
        
        try:
            nuevo_articulo = articulo(
                nombre_articulo=nombre_articulo_str,
                precio=precio_decimal # Usar el precio validado y convertido a Decimal
            )
            nuevo_articulo.save()

            # --- Añadir el nuevo artículo al campo ManyToMany 'productos' del carrito ---
            carrito_obj.productos.add(nuevo_articulo)
            messages.success(request, f"'{nuevo_articulo.nombre_articulo}' fue agregado a tu carrito.")

        except Exception as e:
            logger.error(f"Error al crear o agregar artículo al carrito para {request.user.username}: {e}", exc_info=True)
            messages.error(request, "Ocurrió un error al agregar el producto al carrito.")

        # Redirigir a la página anterior (normalmente la tienda o el modal)
        return redirect(request.META.get('HTTP_REFERER', 'tienda')) # Ajusta el fallback si es necesario

    # Si no es POST, redirigir a la tienda (o a donde sea apropiado)
    return redirect('tienda')

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