# Cómo subir "Bandas efímeras" a GitHub

Esta carpeta tiene el proyecto completo, listo para el repositorio (sin `node_modules`, certificados ni el mp3 original).

## Subir

1. En github.com crea un repositorio **Public** (o usa el que ya tienes: en ese caso, sube todo encima y se reemplazan los archivos).
2. **Add file → Upload files**. Abre esta carpeta en el Explorador, selecciona **todo** (Ctrl+A) y arrástralo a la página.
   - Las carpetas deben llegar como carpetas: en la lista de la página tienen que verse rutas como `public/escenario.html` y `public/canciones/tren-al-sur/bajo.ogg`, no `escenario.html` suelto.
   - GitHub acepta hasta 100 archivos por subida; esta carpeta tiene ~33.
3. **Commit changes**.

## Publicar (una sola vez)

**Settings → Pages → Build and deployment**:
- Source: **Deploy from a branch**
- Branch: **main** · carpeta **/ (root)** → **Save**

En la pestaña **Actions** aparece "pages build and deployment"; cuando quede en verde (1–2 min, la primera vez puede tardar hasta ~10), el sitio está en:

- **Inicio:** `https://<tu-usuario>.github.io/<repositorio>/`
- **Pantalla:** `https://<tu-usuario>.github.io/<repositorio>/public/escenario.html`

## Si el repositorio anterior tiene `.github/workflows/node.js.yml`

Es una plantilla de GitHub que falla en cada subida (no hay pruebas en este proyecto). No afecta al sitio; si quieres quitar la marca roja, bórralo en GitHub (ábrelo → ícono de basurero → Commit).

## Antes de publicar

- `public/config.js` es público: usuario y contraseña de EMQX quedan a la vista. Hoy EMQX los rechaza y se usa el broker público de respaldo; cuando los corrijas en la consola de EMQX Cloud, actualízalos ahí.
- Las pistas de `public/canciones/` quedan descargables por cualquiera.
