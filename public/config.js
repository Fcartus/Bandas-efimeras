// Broker MQTT en línea (el "tracker" que conecta los teléfonos con la pantalla).
//
// · Publicado en GitHub Pages (o sin el servidor): se usa `broker`. Si ese broker rechaza el usuario o la
//   contraseña, se usa `respaldo` (broker público de EMQX, sin cuenta).
// · Con `node server.js` en la misma red: se usa el broker local del servidor (más rápido).
//
// OJO: en GitHub Pages este archivo es público. En EMQX crea un usuario solo para esto, con permiso limitado a tacto/#.
// Si la página del teléfono vive en otro sitio, indica su dirección para el QR con phoneUrl: 'https://…/'.
window.TACTO_CONFIG = {
  broker: 'wss://b80fb118.ala.us-east-1.emqxsl.com:8084/mqtt',
  username: 'Facundo',
  password: 'Tracker123',
  respaldo: 'wss://broker.emqx.io:8084/mqtt',
};
