# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Django 5.2.3 ERP system for managing camera purchases, primarily from Buyee (a Japanese proxy buying service). The system tracks orders (pedidos), individual items (artículos), and their associated costs including exchange rates, customs, shipping, and calculates profit margins.

## Development Environment

### Docker Setup
The project runs in Docker containers defined in [docker-compose.yml](docker-compose.yml):
- `django-buyee`: Main Django application (port 8000)
- `mysql`: MySQL 8.0.43 database (port 33061)

### Starting the Development Environment
```bash
# Start containers
docker-compose up -d

# Access Django container
docker exec -it django-buyee bash

# Inside container, run Django commands from /app/src
cd /app/src
```

### Common Commands

All Django commands must be run from `/app/src`:

```bash
# Run development server (inside container)
cd /app/src && python manage.py runserver 0:8000

# Make migrations
cd /app/src && python manage.py makemigrations

# Apply migrations
cd /app/src && python manage.py migrate

# Create superuser
cd /app/src && python manage.py createsuperuser

# Django shell
cd /app/src && python manage.py shell

# Run tests
cd /app/src && python manage.py test core

# Collect static files
cd /app/src && python manage.py collectstatic --noinput
```

## Architecture

### Project Structure
- `/app/src/buyee/`: Django project settings and configuration
  - `settings.py`: Main configuration (uses environment variables from .env)
  - `urls.py`: Root URL configuration (only admin routes)
  - `wsgi.py` / `asgi.py`: WSGI/ASGI application entry points
- `/app/src/core/`: Main application with all business logic
  - `models.py`: Database models (Pedido, Articulo, Marca)
  - `admin.py`: Django Admin customizations with inline editing and aggregations
  - `templates/admin/core/articulo/change_list.html`: Custom admin template for totals display
- `/app/requirements.txt`: Python dependencies
- `/app/.env`: Environment variables (database credentials, DEBUG, ALLOWED_HOSTS)

### Data Model

**Pedido (Order)**
- Represents a bulk purchase order from Buyee
- Contains exchange rate (EUR/JPY) and IVA rate for the entire order
- Tracks `gastos_aduana` (customs fees) and `coste_envio_agrupado` (grouped shipping cost)
- Has methods to distribute costs proportionally across all items:
  - `distribuir_gastos_aduana()`: Distributes customs fees to `aduana_imputada` field of each Articulo
  - `distribuir_coste_envio()`: Distributes shipping costs to `coste_envio_individual` field of each Articulo

**Articulo (Item)**
- Linked to a Pedido via ForeignKey (related_name='articulos')
- Has tipo_articulo: BODY, LENTE, COMPLETA, OTROS
- Has estado: VENDIDO, COLECCION, DESECHADO
- Automatic calculated fields on save:
  - `coste_yen`: Calculated from `coste_euro` * `pedido.tasa_cambio_eur_jpy`
  - `iva`: Calculated from `coste_euro` * `pedido.tasa_iva`
- Computed properties:
  - `coste_adquisicion_total`: Sum of coste_euro + iva + coste_envio_individual + aduana_imputada + coste_envio_nacional
  - `beneficio`: precio_venta - coste_adquisicion_total - coste_envio_nacional
- Links to a Marca (Brand) via optional ForeignKey

**Marca (Brand)**
- Simple model for camera brands (e.g., Canon, Nikon, Leica)
- Searchable in admin with autocomplete

### Django Admin Customizations

The admin interface is heavily customized and is the primary interface for this application:

- **Custom site branding**: "ERP Camaras" (configured in [admin.py:12-14](src/core/admin.py#L12-L14))
- **PedidoAdmin**: Inline editing of Articulos with custom actions to distribute costs
- **ArticuloAdmin**:
  - Dynamic pagination (shows all if ≤100 items, otherwise paginate by 40)
  - Custom queryset annotations for aggregated totals (coste_total, beneficio)
  - Custom `changelist_view` that calculates and displays totals: total_coste, total_venta, total_objetiva, total_beneficio
  - Color-coded beneficio column (green for profit, red for loss)
  - Most fields are readonly in detail view (only precio_venta and estado can be edited)
  - Custom template at [src/core/templates/admin/core/articulo/change_list.html](src/core/templates/admin/core/articulo/change_list.html) adds JavaScript to display totals row

### Cost Distribution Workflow

When working with costs:
1. Create a Pedido with exchange rate and IVA rate
2. Add Articulos inline with their `coste_euro` values
3. Save the Pedido - this auto-calculates `coste_yen` and `iva` for each Articulo
4. Enter `gastos_aduana` and `coste_envio_agrupado` on the Pedido
5. Use admin actions to distribute these costs proportionally:
   - "1. Distribuir gastos de aduana"
   - "2. Distribuir coste de envío agrupado"
6. The distribution is proportional to each Articulo's `coste_euro`

## Database

- MySQL 8.0.43 via Docker
- Connection configured via environment variables in `.env`
- Database name: `buyee`
- Default user: `myuser`
- Host: `mysql` (Docker service name)
- Port: 3306 (internal), 33061 (host)

## Important Development Notes

- The Django working directory is `/app/src`, not `/app`
- All `manage.py` commands must be run from `/app/src`
- The container by default runs `tail -f /dev/null` (see docker-compose.yml), so you need to manually run `python src/manage.py runserver 0:8000` from `/app` or `python manage.py runserver 0:8000` from `/app/src`
- Admin interface is the only user-facing interface (no custom views/templates except admin customizations)
- When modifying models, always create and run migrations
- Cost distribution logic in Pedido model uses bulk_update for efficiency
- Articulo model overrides save() to auto-calculate derived fields

## Testing

Run tests with:
```bash
cd /app/src && python manage.py test core
```

Currently, there are minimal tests defined in [src/core/tests.py](src/core/tests.py).
