from django.db import models
from django.contrib.auth.models import User
# Create your models here.

class carrito(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    productos = models.ManyToManyField('articulo', related_name='carrito', blank=True)
    def __str__(self):
        return f"Carrito de compras: {self.usuario.username}"
    
class articulo(models.Model):
    id = models.AutoField(primary_key=True)
    nombre_articulo = models.CharField(max_length=200, blank=False, null=False)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        return self.nombre_articulo