# core/admin.py

from django.contrib import admin
from .models import Pedido, Articulo, Marca
from django.urls import reverse
from django.utils.html import format_html
from django.db.models import F, Sum, Value, DecimalField, Case, When
from django.db.models.functions import Coalesce


# --- ACCIONES DE ADMIN ---
@admin.action(description="1. Distribuir gastos de aduana")
def distribuir_aduana_action(modeladmin, request, queryset):
    for pedido in queryset:
        pedido.distribuir_gastos_aduana()
    modeladmin.message_user(request, "Gastos de aduana distribuidos.", "success")

@admin.action(description="2. Distribuir coste de envío agrupado")
def distribuir_envio_action(modeladmin, request, queryset):
    for pedido in queryset:
        pedido.distribuir_coste_envio()
    modeladmin.message_user(request, "Coste de envío agrupado distribuido.", "success")

@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',) # Añade una barra de búsqueda

class ArticuloInline(admin.TabularInline):
    model = Articulo
    fields = (
        'marca', 'nombre', 'tipo_articulo', 'id_buyee', 'coste_euro',
        'precio_venta', 'venta_objetiva', 'coste_envio_nacional'
    )
    readonly_fields = ('iva', 'coste_yen', 'aduana_imputada', 'coste_envio_individual')
    autocomplete_fields = ['marca']
    extra = 1

@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('fecha_pedido', 'descripcion', 'gastos_aduana', 'coste_envio_agrupado')
    inlines = [ArticuloInline]
    # Añadimos la nueva acción
    actions = [distribuir_aduana_action, distribuir_envio_action]

@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    # --- CONFIGURACIÓN DE LA LISTA ACTUALIZADA ---
    list_display = (
        'marca',
        'nombre',
        'ver_pedido',
        'tipo_articulo',
        'coste_total_con_simbolo',
        'venta_objetiva_con_simbolo', # <-- AÑADIDO
        'precio_venta',
        'beneficio_columna'
    )
    list_filter = ('pedido', 'marca', 'tipo_articulo')
    search_fields = ('nombre', 'id_buyee', 'pedido__descripcion')
    list_per_page = 25

    # --- MÉTODOS DE FORMATO PARA LAS MONEDAS ---
    def coste_total_con_simbolo(self, obj):
        return f"{obj._coste_total:.2f} €"
    coste_total_con_simbolo.short_description = 'Coste Total (€)'
    coste_total_con_simbolo.admin_order_field = '_coste_total'

    # --- NUEVO MÉTODO PARA VENTA OBJETIVA ---
    def venta_objetiva_con_simbolo(self, obj):
        if obj.venta_objetiva is not None:
            return f"{obj.venta_objetiva:.2f} €"
        return "-"
    venta_objetiva_con_simbolo.short_description = 'Venta Objetiva (€)'
    venta_objetiva_con_simbolo.admin_order_field = 'venta_objetiva'

    # --- (El resto de tus métodos: get_queryset, etc., se quedan igual PERO changelist_view cambia) ---
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        zero = Value(0, output_field=DecimalField())
        coste_total_expr = (
            Coalesce(F('coste_euro'), zero) + Coalesce(F('iva'), zero) + 
            Coalesce(F('coste_envio_individual'), zero) + 
            Coalesce(F('aduana_imputada'), zero) + 
            Coalesce(F('coste_envio_nacional'), zero)
        )
        queryset = queryset.annotate(
            _coste_total=coste_total_expr,
            _beneficio=Case(
                When(precio_venta__isnull=False, then=Coalesce(F('precio_venta'), zero) - coste_total_expr),
                default=None
            )
        )
        return queryset

    def changelist_view(self, request, extra_context=None):
        cl = self.get_changelist_instance(request)
        queryset = cl.get_queryset(request)
        # --- ACTUALIZADO PARA INCLUIR VENTA OBJETIVA ---
        totals = queryset.aggregate(
            total_coste=Sum('_coste_total'), 
            total_venta=Sum('precio_venta'),
            total_objetiva=Sum('venta_objetiva')
        )
        total_coste = totals.get('total_coste') or 0
        total_venta = totals.get('total_venta') or 0
        total_objetiva = totals.get('total_objetiva') or 0

        extra_context = extra_context or {}
        extra_context['total_coste'] = total_coste
        extra_context['total_venta'] = total_venta
        extra_context['total_objetiva'] = total_objetiva
        extra_context['total_beneficio'] = total_venta - total_coste
        return super().changelist_view(request, extra_context=extra_context)

    def ver_pedido(self, obj):
        url = reverse('admin:core_pedido_change', args=[obj.pedido.pk])
        return format_html('<a href="{}">{}</a>', url, obj.pedido.descripcion)
    ver_pedido.short_description = 'Pedido'
    ver_pedido.admin_order_field = 'pedido__descripcion'

    def beneficio_columna(self, obj):
        if hasattr(obj, '_beneficio') and obj._beneficio is not None:
            beneficio_valor = float(obj._beneficio)
            color = 'green' if beneficio_valor >= 0 else 'red'
            texto_del_beneficio = f"{beneficio_valor:.2f} €"
            return format_html('<span style="color: {};">{}</span>', color, texto_del_beneficio)
        return "En Venta"
    beneficio_columna.short_description = 'Beneficio (€)'
    beneficio_columna.admin_order_field = '_beneficio'
    
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False