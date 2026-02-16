from decimal import Decimal
from django.db import models, transaction
from django.db.models import Sum

class Pedido(models.Model):
    # ... (campos anteriores como fecha_pedido, descripcion, etc.) ...
    fecha_pedido = models.DateField(help_text="Fecha en la que se realizó el pedido.")
    descripcion = models.CharField(max_length=255, help_text="Descripción breve del pedido.")
    coste_envio_agrupado = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    gastos_aduana = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # NUEVOS CAMPOS
    tasa_cambio_eur_jpy = models.DecimalField(
        max_digits=10, 
        decimal_places=4, 
        help_text="Tasa de cambio: 1 Euro = X Yenes. Ej: 165.4321"
    )
    tasa_iva = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.21, 
        help_text="Tasa de IVA a aplicar. Ej: 0.21 para un 21%."
    )

    @transaction.atomic
    def _distribuir_coste(self, coste_total_pedido, campo_articulo_destino):
        """
        Función genérica para distribuir un coste total del pedido
        entre sus artículos de forma proporcional a su 'coste_euro'.

        OPTIMIZACIÓN: Envuelto en @transaction.atomic para garantizar
        que todos los artículos se actualicen o ninguno (rollback automático en caso de error).
        """
        articulos_a_actualizar = []
        articulos = self.articulos.all()

        if coste_total_pedido > 0 and articulos.exists():
            total_coste_base = articulos.aggregate(total=Sum('coste_euro'))['total'] or Decimal('0.00')

            if total_coste_base > 0:
                for articulo in articulos:
                    proporcion = articulo.coste_euro / total_coste_base
                    coste_calculado = coste_total_pedido * proporcion
                    # setattr() nos permite asignar el valor a un campo usando su nombre como string
                    setattr(articulo, campo_articulo_destino, coste_calculado)
                    articulos_a_actualizar.append(articulo)

                if articulos_a_actualizar:
                    Articulo.objects.bulk_update(articulos_a_actualizar, [campo_articulo_destino])
                    return True # Indica que la operación fue exitosa
        return False # Indica que no se hizo nada

    # --- FUNCIONES PÚBLICAS ACTUALIZADAS ---
    def distribuir_gastos_aduana(self):
        """Distribuye los gastos de aduana."""
        return self._distribuir_coste(self.gastos_aduana, 'aduana_imputada')

    def distribuir_coste_envio(self):
        """Distribuye el coste de envío agrupado."""
        return self._distribuir_coste(self.coste_envio_agrupado, 'coste_envio_individual')

    def __str__(self):
        return f"{self.descripcion}"

    class Meta:
        ordering = ['-fecha_pedido']
        indexes = [
            # Índice para ordering y filtros por fecha
            models.Index(fields=['-fecha_pedido'], name='idx_pedido_fecha'),
            # Índice para búsquedas por descripción (usado en search_fields de Articulo)
            models.Index(fields=['descripcion'], name='idx_pedido_desc'),
        ]


class Marca(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre

    class Meta:
        ordering = ['nombre']


class Articulo(models.Model):

    class TipoArticulo(models.TextChoices):
        BODY = 'BODY', 'Body'
        LENTE = 'LENTE', 'Lente'
        COMPLETA = 'COMPLETA', 'Completa'
        OTROS = 'OTROS', 'Otros'

    class EstadoArticulo(models.TextChoices):
        VENDIDO = 'VENDIDO', 'Vendido'
        COLECCION = 'COLECCION', 'Colección'
        DESECHADO = 'DESECHADO', 'Desechado'

    pedido = models.ForeignKey(Pedido, related_name='articulos', on_delete=models.CASCADE)
    nombre = models.CharField(max_length=200)
    tipo_articulo = models.CharField(max_length=10, choices=TipoArticulo.choices, default=TipoArticulo.OTROS,)
    id_buyee = models.CharField(max_length=100, blank=True, null=True, unique=True)
    coste_euro = models.DecimalField(max_digits=10, decimal_places=2)
    coste_envio_individual = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, default=0.00)
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True)
    coste_yen = models.IntegerField(editable=False, blank=True, null=True, help_text="Calculado automáticamente desde el coste en EUR y la tasa de cambio del pedido.")
    iva = models.DecimalField(max_digits=10, decimal_places=2, editable=False, blank=True, null=True,help_text="IVA calculado automáticamente.")
    aduana_imputada = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    venta_objetiva = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    coste_envio_nacional = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    estado = models.CharField(max_length=10, choices=EstadoArticulo.choices, default=EstadoArticulo.COLECCION,help_text="El estado actual del artículo.")

    # --- SOBRESCRIBIMOS EL MÉTODO SAVE PARA LOS CÁLCULOS ---
    def save(self, *args, **kwargs):
        # 1. Calcular el IVA
        if self.pedido.tasa_iva and self.coste_euro:
            self.iva = self.coste_euro * self.pedido.tasa_iva
        
        # 2. Calcular el coste en Yenes
        if self.pedido.tasa_cambio_eur_jpy and self.coste_euro:
            self.coste_yen = round(self.coste_euro * self.pedido.tasa_cambio_eur_jpy)

        # 3. Llamar al método save original para guardar el objeto
        super().save(*args, **kwargs)

    @property
    def coste_adquisicion_total(self):
        iva = self.iva or Decimal('0.00')
        return self.coste_euro + iva + self.coste_envio_individual + self.aduana_imputada + self.coste_envio_nacional

    @property
    def beneficio(self):
        if self.precio_venta is not None:
            coste_total = self.coste_adquisicion_total
            return self.precio_venta - coste_total - self.coste_envio_nacional
        return None

    def __str__(self):
        return self.nombre

    class Meta:
        ordering = ['nombre']
        indexes = [
            # Índice para ordering y búsquedas por nombre
            models.Index(fields=['nombre'], name='idx_articulo_nombre'),
            # Índice para filtros por tipo de artículo
            models.Index(fields=['tipo_articulo'], name='idx_articulo_tipo'),
            # Índice para filtros por estado
            models.Index(fields=['estado'], name='idx_articulo_estado'),
            # Índice compuesto para queries comunes: artículos de un pedido por estado
            models.Index(fields=['pedido', 'estado'], name='idx_articulo_pedido_estado'),
            # Índice para ordenar por precio de venta
            models.Index(fields=['precio_venta'], name='idx_articulo_precio_venta'),
            # Índice para búsquedas por id_buyee (aunque ya es único, ayuda en búsquedas)
            models.Index(fields=['id_buyee'], name='idx_articulo_id_buyee'),
        ]