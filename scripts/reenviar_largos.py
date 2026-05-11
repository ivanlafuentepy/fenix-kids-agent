"""Reenvía mensajes largos: link + mensaje separado para copiar."""
import asyncio
import httpx

TOKEN = "EAAORCCznM1IBRUJXEzeesCyYA8EI2i9P0UixLVzr2QEZA6yXNECmOcf7oBfKt7bmvZAkZBsmBXdjAtby0cZAnZCnMJgw3bFYqGGtDnhmlHG6fgFlB3eJJAv1IvGB0malEUab2Uv5OB2Hn3UyZCqWUEOW9ilhDvSgwcCKOyrgzizNxQpsguuMQyZCHUCsRjkkwZDZD"
PHONE_ID = "1005063086033214"
ADMIN = "595982790407"


async def enviar(texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": ADMIN, "type": "text", "text": {"preview_url": True, "body": texto}}
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers, timeout=15)
        return r.status_code == 200


REENVIAR = [
    ("15/22 \u2014 Laura (Emma - prueba)", "595992535534",
     """Hola Laura! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525

Tengo que contarte algo de Emma que me dej\u00f3 pensando todo el d\u00eda \U0001f49b

Al inicio de la clase Emma no quer\u00eda hacer nada. Se quedaba al costado, miraba, no se animaba. Y eso es totalmente normal \u2014 a los 3 a\u00f1os, un lugar nuevo, gente nueva, da miedo. Pero algo pas\u00f3: de a poquito se fue soltando. Y de repente la vimos en el circuito, haciendo todo, anim\u00e1ndose, ri\u00e9ndose.

Esa transformaci\u00f3n \u2014 pasar del "no puedo" al "mir\u00e1 lo que hago" en una sola clase \u2014 es exactamente lo que buscamos formar ac\u00e1. No es deporte. Es ense\u00f1arles que el miedo se puede atravesar.

Si quieren que Emma siga viviendo esto cada s\u00e1bado, te paso los n\u00fameros:

\U0001f4cb Plan trimestral (3 meses):
\u2022 Trimestral: \u20b2 690.000
\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000
\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba
\u2022 Total: \u20b2 740.000

Lo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa

\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.

Pero te digo algo, Laura: Emma necesita esto. Lo vimos ayer."""),

    ("16/22 \u2014 Patricia (Ezequiel - prueba)", "595985770539",
     """Hola Patricia! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525

Ezequiel dej\u00f3 una huella ayer en Fenix \U0001f525. Lo vimos meterle al circuito, superar sus miedos vuelta tras vuelta, empujado por la tribu. Eso no se aprende mirando una pantalla.

La propuesta es esta: cada s\u00e1bado, una vez por semana, construir juntos esos recuerdos que se quedan para toda la vida. No es solo deporte \u2014 es car\u00e1cter, autoestima, tribu.

Te cuento que si Ezequiel disfrut\u00f3 la experiencia y quieren que la siga viviendo, te paso los n\u00fameros:

\U0001f4cb Plan trimestral (3 meses):
\u2022 Trimestral: \u20b2 690.000
\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000
\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba
\u2022 Total: \u20b2 740.000

Lo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa

\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.

Sin presi\u00f3n \u2014 cuando ustedes decidan. \u00bfQu\u00e9 te parece?"""),

    ("17/22 \u2014 Lili (Alisa+Noa - prueba)", "595984479193",
     """Hola Lili! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525

Fue un gusto recibir a Alisa y Noa ayer.

Alisa la rompi\u00f3 ayer \U0001f525. Con 6 a\u00f1os entr\u00f3 al circuito sin miedo, la vimos empujada por la tribu, ganando confianza vuelta tras vuelta. Esa autoestima que se llev\u00f3 a casa no se compra.

Noa dej\u00f3 todo en el circuito ayer \U0001f525. A los 12 a\u00f1os est\u00e1 entrando en una etapa donde lo que construya hoy le va a servir para toda la vida. Y cr\u00e9eme, ayer construy\u00f3 mucho. Y tenerla acompa\u00f1ando a su hermana menor en la din\u00e1mica suma una capa m\u00e1s \u2014 los lazos que se forman entre ellas en estos espacios se llevan para siempre.

La propuesta es esta: cada s\u00e1bado, una vez por semana, construir juntos esos recuerdos que se quedan para toda la vida. No es solo deporte \u2014 es car\u00e1cter, autoestima, tribu.

Y para familias con 2 hijos tenemos una promo pensada para ustedes \u2014 un descuento de \u20b2 200.000 en la segunda hija. Te paso los n\u00fameros:

\U0001f4cb Plan trimestral para Alisa y Noa (3 meses):
\u2022 Trimestral 1ra hija: \u20b2 690.000
\u2022 Trimestral 2da hija (con \u20b2 200.000 de descuento): \u20b2 490.000
\u2022 Matr\u00edculas (incluyen camiseta Fenix cada una): \u20b2 140.000 x 2 = \u20b2 280.000
\u2022 Menos los \u20b2 120.000 que ya abonaste por la prueba
\u2022 Total: \u20b2 1.340.000

Lo pod\u00e9s abonar en 2 pagos: \u20b2 670.000 ahora y \u20b2 670.000 a fin de mes \U0001f4aa

\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.

\u00bfQu\u00e9 te parece, Lili?"""),

    ("18/22 \u2014 Veronica (Mariano - prueba)", "595992533578",
     """Hola Ver\u00f3nica! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525

Te quer\u00eda escribir espec\u00edficamente sobre Mariano porque s\u00e9 que ayer fue un d\u00eda dif\u00edcil para \u00e9l \U0001f49b

Hablamos en el momento y te lo digo de nuevo ac\u00e1, con calma: no hay ning\u00fan problema. Lo que pas\u00f3 ayer es absolutamente normal. Mariano lleg\u00f3 a un lugar nuevo, con din\u00e1micas nuevas, gente nueva, y su sistema dijo "esto es mucho". El llanto, la resistencia, no querer seguir las instrucciones \u2014 todo eso es informaci\u00f3n valiosa, no es un problema.

Lo que necesita Mariano es exactamente lo que vos ya intuiste: tiempo, espacio, dejarlo adaptarse a su ritmo. Ac\u00e1 en Fenix nuestro trabajo no es forzar \u2014 es acompa\u00f1ar. S\u00e1bado a s\u00e1bado va a ir solt\u00e1ndose, conociendo el lugar, los profes, los compa\u00f1eros. Y un d\u00eda vas a verlo en el circuito como si siempre hubiera estado.

Si quer\u00e9s darle ese proceso, te paso los n\u00fameros:

\U0001f4cb Plan trimestral (3 meses):
\u2022 Trimestral: \u20b2 690.000
\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000
\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba
\u2022 Total: \u20b2 740.000

Lo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa

\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.

Mariano tiene mucho para dar \u2014 solo necesita su tiempo \U0001f525

Ac\u00e1 estamos para acompa\u00f1arlos, Ver\u00f3nica."""),

    ("19/22 \u2014 Dirce (Milagros+Alejandra+Alfredo - 3x2)", "595982138554",
     """Hola Dirce! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525

Fue un gustazo recibir a Milagros, Alejandra y Alfredo ayer \u2014 toda una tribu propia \U0001f49b

Milagros demostr\u00f3 ayer que tiene madera \U0001f525. A los 9 a\u00f1os ya entendi\u00f3 algo que muchos adultos no: que el "no puedo" se cae cuando lo empuj\u00e1s. La vimos crecer en una sola clase.

Alejandra la rompi\u00f3 ayer \U0001f525. Con 6 a\u00f1os entr\u00f3 al circuito sin miedo, la vimos empujada por la tribu, ganando confianza vuelta tras vuelta. Esa autoestima que se llev\u00f3 a casa no se compra.

Ayer Alfredo se la jug\u00f3 de verdad \U0001f525. A los 8 a\u00f1os est\u00e1 en la edad clave donde se forma todo: el car\u00e1cter, la disciplina, la cabeza. Y lo vimos superando sus propios miedos, vuelta tras vuelta.

Lo m\u00e1s lindo fue verlos a los tres ah\u00ed, empuj\u00e1ndose entre ellos, cuid\u00e1ndose. Esa uni\u00f3n que ya traen de casa, ac\u00e1 se potencia much\u00edsimo.

Para familias como la suya tenemos una promo especial: 3x2 \u2014 pag\u00e1s por 2 y los 3 entran. Te paso los n\u00fameros:

\U0001f4cb Plan trimestral para Milagros, Alejandra y Alfredo (3 meses):
\u2022 Trimestrales: \u20b2 690.000 x 2 (pag\u00e1s por 2, llevan 3) = \u20b2 1.380.000
\u2022 Matr\u00edculas (incluyen camiseta Fenix cada uno): \u20b2 140.000 x 3 = \u20b2 420.000
\u2022 Menos los \u20b2 150.000 que ya abonaste por la prueba
\u2022 Total: \u20b2 1.650.000

Lo pod\u00e9s abonar en 2 pagos: \u20b2 825.000 ahora y \u20b2 825.000 a fin de mes \U0001f4aa

\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.

Los 3 quedan cubiertos por todo el trimestre, cada uno con su camiseta Fenix. \u00bfQu\u00e9 te parece, Dirce?"""),

    ("20/22 \u2014 Ruth (Piero+Isaac - prueba)", "595973295552",
     """Hola Ruth! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525

Te quer\u00eda escribir sobre Piero e Isaac, porque ayer me dejaron pensando \U0001f49b

Piero demostr\u00f3 ayer que tiene madera \U0001f525. A los 9 a\u00f1os ya entendi\u00f3 algo que muchos adultos no: que el "no puedo" se cae cuando lo empuj\u00e1s. Lo vimos crecer en una sola clase.

Y de Isaac te tengo que contar aparte. S\u00e9 que el espectro le marca el ritmo de c\u00f3mo procesa lo nuevo. Y por eso lo de ayer me parece todav\u00eda m\u00e1s enorme: lo vimos con miedo, s\u00ed \u2014 pero tambi\u00e9n lo vimos feliz, contento, presente. Y lo m\u00e1s importante: vuelta tras vuelta, en cada circuito, lo vimos animarse a m\u00e1s. Eso es coraje del bueno, del que no se ense\u00f1a en ning\u00fan lado. Y tener a Piero ah\u00ed, siendo su referente, su hermano mayor, suma una capa que no se mide.

Fenix est\u00e1 pensado para acompa\u00f1ar a cada chico en su ritmo, sin forzar, sin comparar. Ac\u00e1 los dos pueden crecer juntos \u2014 cada uno a su tiempo.

Para familias con 2 hijos tenemos una promo pensada para ustedes \u2014 un descuento de \u20b2 200.000 en el segundo hijo. Te paso los n\u00fameros:

\U0001f4cb Plan trimestral para Piero e Isaac (3 meses):
\u2022 Trimestral 1er hijo: \u20b2 690.000
\u2022 Trimestral 2do hijo (con \u20b2 200.000 de descuento): \u20b2 490.000
\u2022 Matr\u00edculas (incluyen camiseta Fenix cada uno): \u20b2 140.000 x 2 = \u20b2 280.000
\u2022 Menos los \u20b2 120.000 que ya abonaste por la prueba
\u2022 Total: \u20b2 1.340.000

Lo pod\u00e9s abonar en 2 pagos: \u20b2 670.000 ahora y \u20b2 670.000 a fin de mes \U0001f4aa

\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.

Los vamos a cuidar a los dos como se merecen, Ruth."""),

    ("21/22 \u2014 Luis (Lucas Peralta - prueba)", "595983273528",
     """Hola Luis! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525

Lucas es un guerrero chiquito \U0001f525. A los 4 a\u00f1os ya se anima a circuitos que muchos grandes esquivar\u00edan. Lo vimos caer, levantarse y volver a intentarlo \u2014 eso, a esa edad, vale oro.

La propuesta es esta: cada s\u00e1bado, una vez por semana, construir juntos esos recuerdos que se quedan para toda la vida. No es solo deporte \u2014 es car\u00e1cter, autoestima, tribu.

Te cuento que si Lucas disfrut\u00f3 la experiencia y quieren que la siga viviendo, te paso los n\u00fameros:

\U0001f4cb Plan trimestral (3 meses):
\u2022 Trimestral: \u20b2 690.000
\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000
\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba
\u2022 Total: \u20b2 740.000

Lo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa

\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.

Sin presi\u00f3n \u2014 cuando ustedes decidan. \u00bfQu\u00e9 te parece?"""),

    ("22/22 \u2014 Hector (Martina - Aurora)", "595972555062",
     """Hola H\u00e9ctor! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525

Martina vuela \U0001f333. Cada s\u00e1bado la vemos un paso m\u00e1s fuerte, m\u00e1s coordinada, m\u00e1s parte de la tribu. Disfrutala porque est\u00e1 atravesando un momento precioso.

Gracias por confiar en nosotros cada semana. Que Martina est\u00e9 ac\u00e1 no es casualidad \u2014 es decisi\u00f3n tuya, y se nota. Nos vemos el pr\u00f3ximo s\u00e1bado \U0001f525"""),
]


async def main():
    for i, (header, tel, msg) in enumerate(REENVIAR, 1):
        # Mensaje 1: header + link
        link_msg = f"{header}\n\nhttps://wa.me/{tel}\n\n\u2b07\ufe0f COPIAR MENSAJE \u2b07\ufe0f"
        ok1 = await enviar(link_msg)
        await asyncio.sleep(1)

        # Mensaje 2: el texto para copiar
        ok2 = await enviar(msg)
        await asyncio.sleep(1.5)

        status = "OK" if (ok1 and ok2) else "FALLO"
        print(f"[{i}/{len(REENVIAR)}] {header}: {status}")

    print(f"\nListo! {len(REENVIAR)} mensajes reenviados.")


if __name__ == "__main__":
    asyncio.run(main())
