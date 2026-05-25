# Guía: Cómo manejar sesiones en Claude Code

> Para cualquier persona que trabaje con Claude Code, desde cero.

---

## El problema

Cuando trabajás con Claude Code, es tentador hacer todo en una sola sesión: arreglar un bug, después cambiar el diseño, después agregar una función nueva, después tocar la documentación.

El resultado es un desastre:

- **52 commits mezclados** de 5 temas distintos
- **Imposible escribir un resumen** de lo que se hizo (porque se hizo de todo)
- **La documentación se desactualiza** porque el cierre no puede cubrir tanto
- **Si cerrás la sesión**, perdés el hilo de cada tema
- **Si alguien más retoma**, no entiende qué estaba pasando

Ejemplo real: en una sola sesión se tocaron precios, afiches, detectores, refactor del monolito y modo secretaria. El documento de estado del proyecto quedó 52 commits atrasado porque el cierre no pudo procesarlo todo.

---

## La solución: una sesión = un tema

Cada vez que abrís Claude Code, trabajás en **un solo tema**. Si tenés 3 cosas para hacer, abrís 3 terminales.

```
Terminal 1: "fix precios CTA"        → solo eso
Terminal 2: "refactor monolito"      → solo eso  
Terminal 3: "actualizar docs"        → solo eso
```

Ventajas:
- Cada sesión tiene contexto limpio (Claude no se confunde)
- Los commits salen agrupados por tema
- El cierre de sesión es fácil (un tema = un resumen)
- Podés retomar cualquier sesión después sin perder el hilo

---

## Comandos disponibles

### Desde la terminal (antes de entrar a Claude Code)

| Comando | Qué hace |
|---|---|
| `retomar-sesion` | Te muestra una lista de sesiones anteriores y elegís cuál retomar |
| `continuar-sesion` | Continúa la última sesión, como si nunca la hubieras cerrado |
| `historial-sesion` | Igual que retomar-sesion: muestra la lista de sesiones |

### Dentro de Claude Code (ya estás en una sesión)

| Comando | Qué hace |
|---|---|
| `/rename nombre` | Le pone un nombre a la sesión actual (ej: `/rename fix precios`) |
| `/export` | Copia toda la conversación al clipboard para pegarla donde quieras |

---

## Cómo implementarlo (paso a paso)

### Paso 1: Abrir el archivo .bashrc

El `.bashrc` es un archivo que se ejecuta cada vez que abrís una terminal. Ahí ponemos los atajos.

En Git Bash o terminal, escribí:

```bash
code ~/.bashrc
```

(Si usás otro editor, reemplazá `code` por `nano`, `vim`, o el que uses)

### Paso 2: Agregar los aliases al final del archivo

Copiá y pegá esto al final:

```bash
# === Gestión de sesiones Claude Code ===
alias retomar-sesion='claude -r'
alias continuar-sesion='claude -c'
alias historial-sesion='claude -r'
alias nombrar-sesion='echo "Dentro de Claude Code escribí: /rename nombre-de-la-sesion"'
alias exportar-sesion='echo "Dentro de Claude Code escribí: /export"'
```

### Paso 3: Recargar la terminal

Para que los aliases funcionen sin cerrar y abrir la terminal:

```bash
source ~/.bashrc
```

### Paso 4: Probar

Escribí `retomar-sesion` en la terminal. Debería mostrarte la lista de sesiones anteriores (o decirte que no hay ninguna si es tu primera vez).

---

## Ejemplo de un día de trabajo

### Mañana: 3 temas para hacer

Abrís 3 terminales:

**Terminal 1:**
```bash
cd mi-proyecto
claude -n "fix bug login"
```
Trabajás solo en el bug. Cuando terminás: `/rename fix bug login` (si no le pusiste nombre al arrancar) y cerrás.

**Terminal 2:**
```bash
cd mi-proyecto
claude -n "agregar filtro busqueda"
```
Trabajás solo en el filtro. Cerrás cuando terminás.

**Terminal 3:**
```bash
cd mi-proyecto
claude -n "actualizar readme"
```
Solo documentación. Cerrás.

### Tarde: retomar algo que dejaste a medias

```bash
cd mi-proyecto
retomar-sesion
```

Te muestra:
```
  fix bug login              (hace 3 horas)
  agregar filtro busqueda    (hace 2 horas)
  actualizar readme          (hace 1 hora)
```

Elegís "agregar filtro busqueda" y seguís donde lo dejaste, con todo el contexto intacto.

---

## Dónde se guardan las conversaciones

Claude Code guarda automáticamente cada sesión en:

```
~/.claude/projects/<nombre-del-proyecto>/*.jsonl
```

- Cada archivo `.jsonl` es una sesión completa
- Se guardan para siempre (no se borran solos)
- Claude Code puede leerlos para retomar contexto
- No necesitás hacer nada, es automático

Si querés exportar una conversación a un formato legible (para compartir o documentar), usá `/export` dentro de la sesión.

---

## Regla de oro

**Una sesión = un tema. Si tenés 3 cosas para hacer, abrí 3 terminales.**

Así de simple. Tu yo del futuro te lo va a agradecer.
