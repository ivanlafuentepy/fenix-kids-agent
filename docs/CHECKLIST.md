# CHECKLIST — Control obligatorio antes de cada cambio

> Este archivo se ejecuta cada vez que Ivan dice "checklist" o antes de cualquier
> cambio en prompts.yaml, flujo de main.py, o deploy a producción.
> MOSTRAR los resultados a Ivan antes de implementar. No saltear ningún paso.

---

## ANTES de tocar código

### 1. Leer lo que voy a modificar
- [ ] Leí COMPLETO el archivo/función que voy a tocar (no asumo, leo)
- [ ] Entiendo qué hace cada parte que voy a cambiar/eliminar

### 2. Verificar dependencias
- [ ] Para cada cosa que voy a SACAR o CAMBIAR: hice grep en todo el repo
- [ ] Mostré los resultados del grep a Ivan
- [ ] Si algo depende de lo que voy a tocar → lo dije explícitamente

### 3. Verificar cobertura
- [ ] Si digo "esto ya lo hace el código" → pegué el grep + línea exacta que lo demuestra
- [ ] Si NO hay código que reemplace lo que saco → lo dije explícitamente a Ivan
- [ ] NUNCA afirmo cobertura sin evidencia

### 4. Simular impacto
- [ ] ¿Qué pasa si un lead nuevo escribe "Hola"?
- [ ] ¿Qué pasa si un lead pregunta precio/horario/ubicación?
- [ ] ¿Qué pasa si un lead da nombre y edad del hijo?
- [ ] ¿Qué pasa si un lead dice "sí quiero"?
- [ ] ¿Qué pasa si un lead manda comprobante?
- [ ] ¿Algún escenario queda sin cubrir con mi cambio?

### 5. Presentar a Ivan
- [ ] Listé EXACTAMENTE qué voy a tocar (archivos, líneas, secciones)
- [ ] Listé las dependencias encontradas
- [ ] Listé los escenarios simulados y sus resultados
- [ ] Ivan dio el OK

---

## DURANTE el cambio

### 6. Un cambio por commit
- [ ] No mezclo prompt + código + DB en un solo commit
- [ ] Si toco prompt + código → pusheo código PRIMERO, espero deploy, después prompt

### 7. Verificar que funciona
- [ ] Corrí `python -c "from agent.main import ..."` — compila sin errores
- [ ] Si agregué funciones nuevas → probé con asserts básicos
- [ ] Si modifiqué detectores → probé con casos positivos Y negativos

---

## DESPUÉS del deploy

### 8. Confirmar en producción
- [ ] Esperé que Railway termine el build (~2 min)
- [ ] Probé con endpoint de un lead existente que el agente responde bien
- [ ] Si es cambio de primer mensaje → probé con número nuevo o reset
- [ ] RECIÉN ahí digo "listo"

---

## REGLAS de conducta

- **Si no estoy seguro** → digo "no estoy seguro, dejame verificar"
- **Nunca afirmar** → siempre demostrar (grep, read, output)
- **Si Ivan pregunta "esto va a afectar?"** → verifico primero, opino después
- **Nunca digo "listo"** si no probé que funciona de verdad
- **Si algo falla** → busco causa raíz, no parcheo encima
