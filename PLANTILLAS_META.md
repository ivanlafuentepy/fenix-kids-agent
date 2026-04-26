# Plantillas WhatsApp — Meta Business Manager

> Instrucciones para crear las plantillas en Meta Business Manager.
> Ir a: business.facebook.com → WhatsApp Manager → Message Templates → Create Template

---

## 1. `contenido_diario` — Posteo genérico del día

**Categoría:** Marketing
**Idioma:** Español (es)

**Body:**
```
Hola {{1}}! Mirá nuestro nuevo posteo en {{2}} 👇
{{3}}
```

**Variables:**
- {{1}} = nombre del padre (ej: "Carolina")
- {{2}} = red social (ej: "Instagram")
- {{3}} = link del posteo

---

## 2. `contenido_hijo` — Posteo donde aparece el hijo

**Categoría:** Marketing
**Idioma:** Español (es)

**Body:**
```
Hola {{1}}! {{2}} aparece en nuestro nuevo posteo de {{3}}! Miralo acá 👇
{{4}}
```

**Variables:**
- {{1}} = nombre del padre (ej: "Carolina")
- {{2}} = nombre del hijo (ej: "Benja")
- {{3}} = red social (ej: "Instagram")
- {{4}} = link del posteo

---

## 3. `recordatorio_clase` — Viernes pre-clase

**Categoría:** Utility
**Idioma:** Español (es)

**Body:**
```
Hola {{1}}! Mañana {{2}} tiene clase a las {{3}}h en FENIX Kids. Te esperamos!
```

**Variables:**
- {{1}} = nombre del padre (ej: "Carolina")
- {{2}} = nombre del hijo/a (ej: "Benja y Sofi")
- {{3}} = hora (ej: "9:30")

---

## Notas

- Las plantillas tardan 24-48h en ser aprobadas por Meta
- Categoría "Utility" es más barata que "Marketing" (~$0.02 vs ~$0.04 por mensaje)
- El `recordatorio_clase` califica como Utility porque es un recordatorio de servicio
- Los de contenido son Marketing porque promueven redes sociales
- Probar con el número propio antes de enviar masivo
