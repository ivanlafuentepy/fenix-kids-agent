"""
Carga mensajes de seguimiento del 9/5 en Airtable (SEGUIMIENTO FENIX)
y envía al admin: mensaje para copiar + botón "Enviado".
"""
import asyncio
import httpx
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from agent.airtable_client import _post, _patch, _headers, _BASE_URL

TOKEN = "EAAORCCznM1IBRUJXEzeesCyYA8EI2i9P0UixLVzr2QEZA6yXNECmOcf7oBfKt7bmvZAkZBsmBXdjAtby0cZAnZCnMJgw3bFYqGGtDnhmlHG6fgFlB3eJJAv1IvGB0malEUab2Uv5OB2Hn3UyZCqWUEOW9ilhDvSgwcCKOyrgzizNxQpsguuMQyZCHUCsRjkkwZDZD"
PHONE_ID = "1005063086033214"
ADMIN = "595982790407"
_SEGUIMIENTO = "SEGUIMIENTO FENIX"


async def enviar_texto(texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": ADMIN, "type": "text", "text": {"body": texto}}
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers, timeout=15)
        return r.status_code == 200


async def enviar_2botones(texto, btn_id1, btn_title1, btn_id2, btn_title2):
    url = f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": ADMIN,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": texto},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": btn_id1, "title": btn_title1}},
                    {"type": "reply", "reply": {"id": btn_id2, "title": btn_title2}},
                ]
            }
        }
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers, timeout=15)
        return r.status_code == 200


# (nombre_display, telefono_padre, turno, mensaje)
DATOS = [
    ("Diana (Paula Leon)", "595991406651", "9:30", "inscripta",
     "Hola Diana! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nPaula ya es oficialmente de la familia Fenix \U0001f525. Gracias por la confianza \u2014 significa todo. Ayer la vimos con esa carita de \"esto es lo m\u00edo\" y eso a los 3 a\u00f1os no tiene precio. Cada s\u00e1bado vamos a construir juntos esos recuerdos que se quedan para siempre.\n\n\u00a1Bienvenida a la tribu! Nos vemos el pr\u00f3ximo s\u00e1bado para seguir sumando vueltas, sudor y sonrisas \U0001f525"),

    ("Laura (Marttina)", "595984179913", "9:30", "prueba",
     "Hola Laura! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nMarttina la rompi\u00f3 ayer \U0001f525. Con 6 a\u00f1os entr\u00f3 al circuito sin miedo, la vimos empujada por la tribu, ganando confianza vuelta tras vuelta. Esa autoestima que se llev\u00f3 a casa no se compra.\n\nLa propuesta es esta: cada s\u00e1bado, una vez por semana, construir juntos esos recuerdos que se quedan para toda la vida. No es solo deporte \u2014 es car\u00e1cter, autoestima, tribu.\n\nTe cuento que si Marttina disfrut\u00f3 la experiencia y quieren que la siga viviendo, te paso los n\u00fameros:\n\n\U0001f4cb Plan trimestral (3 meses):\n\u2022 Trimestral: \u20b2 690.000\n\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000\n\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba\n\u2022 Total: \u20b2 740.000\n\nLo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa\n\n\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.\n\nSin presi\u00f3n \u2014 cuando ustedes decidan. \u00bfQu\u00e9 te parece?"),

    ("Bianca (Ari)", "595981700076", "9:30", "aurora",
     "Hola Bianca! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nAri ya es parte del equipo \U0001f333. A los 10 a\u00f1os trae actitud, foco y compa\u00f1erismo. Esos son los que despu\u00e9s marcan la cancha en cada clase \u2014 y los m\u00e1s chicos los miran.\n\nGracias por confiar en nosotros cada semana. Que Ari est\u00e9 ac\u00e1 no es casualidad \u2014 es decisi\u00f3n tuya, y se nota. Nos vemos el pr\u00f3ximo s\u00e1bado \U0001f525"),

    ("Fabi (Maxi+Carla)", "595981913816", "9:30", "aurora",
     "Hola Fabi! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nQuer\u00eda escribirte espec\u00edficamente sobre Carla y Maxi \U0001f49b\n\nCarla est\u00e1 volando \U0001f333. A los 6 a\u00f1os est\u00e1 en pleno despegue, cada s\u00e1bado la vemos m\u00e1s segura, m\u00e1s metida, m\u00e1s parte de la tribu. Disfrutala porque est\u00e1 atravesando una etapa preciosa.\n\nY Maxi \u2014 Maxi me tiene contento. Te acord\u00e1s cuando arranc\u00f3, con todos esos miedos, con esa duda en cada movimiento. Bueno, ese chico ya no est\u00e1. El que vemos ahora es otro: m\u00e1s firme, m\u00e1s decidido, anim\u00e1ndose a cosas que antes esquivaba. Esa transformaci\u00f3n no es casualidad \u2014 es el trabajo silencioso de cada s\u00e1bado, ladrillo a ladrillo.\n\nGracias por sostener el proceso de los dos, Fabi. Lo que est\u00e1n construyendo es enorme \U0001f525"),

    ("Carolina (Horacio)", "595981541002", "11:00", "prueba",
     "Hola Carolina! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nAyer Horacio se la jug\u00f3 de verdad \U0001f525. A los 8 a\u00f1os est\u00e1 en la edad clave donde se forma todo: el car\u00e1cter, la disciplina, la cabeza. Y lo vimos superando sus propios miedos, vuelta tras vuelta.\n\nLa propuesta es esta: cada s\u00e1bado, una vez por semana, construir juntos esos recuerdos que se quedan para toda la vida. No es solo deporte \u2014 es car\u00e1cter, autoestima, tribu.\n\nTe cuento que si Horacio disfrut\u00f3 la experiencia y quieren que la siga viviendo, te paso los n\u00fameros:\n\n\U0001f4cb Plan trimestral (3 meses):\n\u2022 Trimestral: \u20b2 690.000\n\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000\n\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba\n\u2022 Total: \u20b2 740.000\n\nLo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa\n\n\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.\n\nSin presi\u00f3n \u2014 cuando ustedes decidan. \u00bfQu\u00e9 te parece?"),

    ("Pamela (Rafael)", "595983186863", "11:00", "prueba",
     "Hola Pamela! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nQuer\u00eda tomarme un minuto para hablarte de Rafa con honestidad \U0001f49b\n\nRafa es un amor \u2014 chiquito, valiente, curioso. Pero ayer, vi\u00e9ndolo en el circuito, me di cuenta de algo importante: todav\u00eda es muy peque\u00f1ito para nuestra din\u00e1mica. Los desaf\u00edos que armamos requieren un nivel de concentraci\u00f3n, equilibrio y autonom\u00eda que a los 2 a\u00f1itos reci\u00e9n est\u00e1n empezando a desarrollarse. Forzarlo ahora no le suma \u2014 al contrario, puede frustrarlo.\n\nMi recomendaci\u00f3n honesta: esper\u00e1 unos meses, dale tiempo para crecer un poco m\u00e1s, y cuando est\u00e9 listo lo recibimos con los brazos abiertos. Mientras tanto, te recomiendo actividades de estimulaci\u00f3n temprana, juegos de motricidad en casa, parques. Eso es lo que Rafa necesita ahora.\n\nGracias por traerlo y por la confianza, Pamela. Cuando llegue el momento, ac\u00e1 vamos a estar esper\u00e1ndolo \U0001f525"),

    ("Erika (Tomas)", "595961550099", "11:00", "prueba",
     "Hola Erika! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nTomas es un guerrero chiquito \U0001f525. A los 4 a\u00f1os ya se anima a circuitos que muchos grandes esquivar\u00edan. Lo vimos caer, levantarse y volver a intentarlo \u2014 eso, a esa edad, vale oro.\n\nLa propuesta es esta: cada s\u00e1bado, una vez por semana, construir juntos esos recuerdos que se quedan para toda la vida. No es solo deporte \u2014 es car\u00e1cter, autoestima, tribu.\n\nTe cuento que si Tomas disfrut\u00f3 la experiencia y quieren que la siga viviendo, te paso los n\u00fameros:\n\n\U0001f4cb Plan trimestral (3 meses):\n\u2022 Trimestral: \u20b2 690.000\n\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000\n\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba\n\u2022 Total: \u20b2 740.000\n\nLo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa\n\n\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.\n\nSin presi\u00f3n \u2014 cuando ustedes decidan. \u00bfQu\u00e9 te parece?"),

    ("Liza (Amaro)", "595981277930", "11:00", "aurora",
     "Hola Liza! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nAmaro est\u00e1 volando \U0001f333. A los 9 a\u00f1os trae actitud, foco y compa\u00f1erismo \u2014 es de esos chicos que despu\u00e9s marcan la cancha en cada clase, y los m\u00e1s chicos los miran como referencia. Cada s\u00e1bado lo vemos un paso m\u00e1s arriba.\n\nGracias por confiar en nosotros cada semana. Que Amaro est\u00e9 ac\u00e1 no es casualidad \u2014 es decisi\u00f3n tuya, y se nota. Nos vemos el pr\u00f3ximo s\u00e1bado \U0001f525"),

    ("Jessica (Lucas+Anita)", "595981486156", "11:00", "aurora",
     "Hola Jessica! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nTe quer\u00eda escribir sobre Anita y Lucas \U0001f49b\n\nAnita est\u00e1 volando \U0001f333. A los 5 a\u00f1os est\u00e1 en pleno despegue: anim\u00e1ndose a m\u00e1s, riendo en los desaf\u00edos, solt\u00e1ndose. Eso es exactamente lo que buscamos a esta edad.\n\nY Lucas \u2014 Lucas me emociona. S\u00e9 que el espectro le marca el ritmo, y por eso lo que estamos viendo me parece tan importante: cada s\u00e1bado lo vemos m\u00e1s fuerte, con m\u00e1s autoestima, m\u00e1s confiado. No es solo que est\u00e9 \"mejor\" \u2014 est\u00e1 creciendo en lo que importa: en c\u00f3mo se ve a s\u00ed mismo. Eso se va a quedar con \u00e9l toda la vida.\n\nGracias por sostener este proceso para los dos, Jessica. Lo que est\u00e1n construyendo es grande \U0001f525"),

    ("Yandry (Tito+Cami)", "595972135109", "11:00", "aurora",
     "Hola Yandry! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nFue un gusto tener a Tito y Cami ayer en Aurora.\n\nTito est\u00e1 volando \U0001f333. A los 7 a\u00f1os ya tiene confianza, conoce la din\u00e1mica, y se nota \u2014 ayer lo vimos liderando momentos del circuito sin darse cuenta.\n\nCami est\u00e1 volando \U0001f333. A los 5 a\u00f1os est\u00e1 en pleno despegue: vimos c\u00f3mo se anima a m\u00e1s, c\u00f3mo se r\u00ede entre los desaf\u00edos, c\u00f3mo se suelta. Eso es lo que buscamos.\n\nGracias por confiar en nosotros cada semana. Que Tito y Cami est\u00e9n ac\u00e1 no es casualidad \u2014 es decisi\u00f3n tuya, y se nota. Nos vemos el pr\u00f3ximo s\u00e1bado \U0001f525"),

    ("Victor (Benja+Lu)", "595981529457", "11:00", "aurora",
     "Hola Victor! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nTe quer\u00eda contar espec\u00edficamente sobre Benja \U0001f49b\n\nS\u00e9 que Benja viene cargando algunos miedos desde antes, y ayer tuvo unos momentos donde no quiso hacer ciertas cosas. Y te digo lo mismo que te dir\u00eda en persona: est\u00e1 perfecto. Est\u00e1 en su proceso. Cada s\u00e1bado se est\u00e1 adaptando un poco m\u00e1s, anim\u00e1ndose un poco m\u00e1s, solt\u00e1ndose un poco m\u00e1s. No hay que forzarlo \u2014 hay que dejarlo. Y vamos a ir viendo c\u00f3mo va creciendo a su ritmo.\n\nLu, por otro lado, est\u00e1 volando \U0001f333. A los 5 a\u00f1os est\u00e1 en pleno despegue, anim\u00e1ndose, ri\u00e9ndose, meti\u00e9ndose. Es un placer tenerla.\n\nGracias por sostener el proceso de Benja con paciencia, Victor. Lo que est\u00e1n haciendo va a dar frutos \u2014 lo vemos cada semana un poco m\u00e1s \U0001f525"),

    ("Hilda (Helena)", "595972816687", "11:00", "aurora",
     "Hola Hilda! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nHelena est\u00e1 cada vez mejor \U0001f333. A los 6 a\u00f1os la vemos s\u00e1bado tras s\u00e1bado m\u00e1s suelta, m\u00e1s segura, m\u00e1s metida en el grupo. Ese crecimiento silencioso es lo que despu\u00e9s se ve en todo: en c\u00f3mo enfrenta lo nuevo, en c\u00f3mo se anima.\n\nGracias por confiar en nosotros cada semana. Que Helena est\u00e9 ac\u00e1 no es casualidad \u2014 es decisi\u00f3n tuya, y se nota. Nos vemos el pr\u00f3ximo s\u00e1bado \U0001f525"),

    ("Ilse (Giuli+Ichi)", "595981102495", "11:00", "aurora",
     "Hola Ilse! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nGiuli e Ichi est\u00e1n volando \U0001f333. Las dos a los 6 a\u00f1os est\u00e1n en pleno despegue: anim\u00e1ndose a m\u00e1s, ri\u00e9ndose entre los desaf\u00edos, meti\u00e9ndose de lleno en cada vuelta. Es un placer tenerlas \u2014 y tenerlas juntas suma todav\u00eda m\u00e1s, porque se empujan entre ellas.\n\nGracias por confiar en nosotros cada semana. Que Giuli e Ichi est\u00e9n ac\u00e1 no es casualidad \u2014 es decisi\u00f3n tuya, y se nota. Nos vemos el pr\u00f3ximo s\u00e1bado \U0001f525"),

    ("Anto (Oli)", "595982778542", "11:00", "aurora",
     "Hola Anto! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nOli es imparable \U0001f333. A los 7 a\u00f1os trae una energ\u00eda y un compromiso que contagia al grupo entero. Cada s\u00e1bado lo vemos un paso m\u00e1s arriba \u2014 ayer lo vimos liderando momentos del circuito sin darse cuenta.\n\nGracias por confiar en nosotros cada semana. Que Oli est\u00e9 ac\u00e1 no es casualidad \u2014 es decisi\u00f3n tuya, y se nota. Nos vemos el pr\u00f3ximo s\u00e1bado \U0001f525"),

    ("Laura (Emma)", "595992535534", "15:30", "prueba",
     "Hola Laura! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nTengo que contarte algo de Emma que me dej\u00f3 pensando todo el d\u00eda \U0001f49b\n\nAl inicio de la clase Emma no quer\u00eda hacer nada. Se quedaba al costado, miraba, no se animaba. Y eso es totalmente normal \u2014 a los 3 a\u00f1os, un lugar nuevo, gente nueva, da miedo. Pero algo pas\u00f3: de a poquito se fue soltando. Y de repente la vimos en el circuito, haciendo todo, anim\u00e1ndose, ri\u00e9ndose.\n\nEsa transformaci\u00f3n \u2014 pasar del \"no puedo\" al \"mir\u00e1 lo que hago\" en una sola clase \u2014 es exactamente lo que buscamos formar ac\u00e1. No es deporte. Es ense\u00f1arles que el miedo se puede atravesar.\n\nSi quieren que Emma siga viviendo esto cada s\u00e1bado, te paso los n\u00fameros:\n\n\U0001f4cb Plan trimestral (3 meses):\n\u2022 Trimestral: \u20b2 690.000\n\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000\n\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba\n\u2022 Total: \u20b2 740.000\n\nLo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa\n\n\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.\n\nPero te digo algo, Laura: Emma necesita esto. Lo vimos ayer."),

    ("Patricia (Ezequiel)", "595985770539", "15:30", "prueba",
     "Hola Patricia! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nEzequiel dej\u00f3 una huella ayer en Fenix \U0001f525. Lo vimos meterle al circuito, superar sus miedos vuelta tras vuelta, empujado por la tribu. Eso no se aprende mirando una pantalla.\n\nLa propuesta es esta: cada s\u00e1bado, una vez por semana, construir juntos esos recuerdos que se quedan para toda la vida. No es solo deporte \u2014 es car\u00e1cter, autoestima, tribu.\n\nTe cuento que si Ezequiel disfrut\u00f3 la experiencia y quieren que la siga viviendo, te paso los n\u00fameros:\n\n\U0001f4cb Plan trimestral (3 meses):\n\u2022 Trimestral: \u20b2 690.000\n\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000\n\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba\n\u2022 Total: \u20b2 740.000\n\nLo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa\n\n\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.\n\nSin presi\u00f3n \u2014 cuando ustedes decidan. \u00bfQu\u00e9 te parece?"),

    ("Lili (Alisa+Noa)", "595984479193", "15:30", "prueba",
     "Hola Lili! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nFue un gusto recibir a Alisa y Noa ayer.\n\nAlisa la rompi\u00f3 ayer \U0001f525. Con 6 a\u00f1os entr\u00f3 al circuito sin miedo, la vimos empujada por la tribu, ganando confianza vuelta tras vuelta. Esa autoestima que se llev\u00f3 a casa no se compra.\n\nNoa dej\u00f3 todo en el circuito ayer \U0001f525. A los 12 a\u00f1os est\u00e1 entrando en una etapa donde lo que construya hoy le va a servir para toda la vida. Y cr\u00e9eme, ayer construy\u00f3 mucho. Y tenerla acompa\u00f1ando a su hermana menor en la din\u00e1mica suma una capa m\u00e1s \u2014 los lazos que se forman entre ellas en estos espacios se llevan para siempre.\n\nY para familias con 2 hijos tenemos una promo pensada para ustedes \u2014 un descuento de \u20b2 200.000 en la segunda hija. Te paso los n\u00fameros:\n\n\U0001f4cb Plan trimestral para Alisa y Noa (3 meses):\n\u2022 Trimestral 1ra hija: \u20b2 690.000\n\u2022 Trimestral 2da hija (con \u20b2 200.000 de descuento): \u20b2 490.000\n\u2022 Matr\u00edculas (incluyen camiseta Fenix cada una): \u20b2 140.000 x 2 = \u20b2 280.000\n\u2022 Menos los \u20b2 120.000 que ya abonaste por la prueba\n\u2022 Total: \u20b2 1.340.000\n\nLo pod\u00e9s abonar en 2 pagos: \u20b2 670.000 ahora y \u20b2 670.000 a fin de mes \U0001f4aa\n\n\u23f0 Te cuento que estamos teniendo mucha demanda, nos escriben familias todos los d\u00edas. Esta promo trimestral la estaremos cerrando en estos d\u00edas.\n\n\u00bfQu\u00e9 te parece, Lili?"),

    ("Veronica (Mariano)", "595992533578", "15:30", "prueba",
     "Hola Ver\u00f3nica! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nTe quer\u00eda escribir espec\u00edficamente sobre Mariano porque s\u00e9 que ayer fue un d\u00eda dif\u00edcil para \u00e9l \U0001f49b\n\nHablamos en el momento y te lo digo de nuevo ac\u00e1, con calma: no hay ning\u00fan problema. Lo que pas\u00f3 ayer es absolutamente normal. Mariano lleg\u00f3 a un lugar nuevo, con din\u00e1micas nuevas, gente nueva, y su sistema dijo \"esto es mucho\". El llanto, la resistencia, no querer seguir las instrucciones \u2014 todo eso es informaci\u00f3n valiosa, no es un problema.\n\nLo que necesita Mariano es exactamente lo que vos ya intuiste: tiempo, espacio, dejarlo adaptarse a su ritmo. Ac\u00e1 en Fenix nuestro trabajo no es forzar \u2014 es acompa\u00f1ar. S\u00e1bado a s\u00e1bado va a ir solt\u00e1ndose, conociendo el lugar, los profes, los compa\u00f1eros. Y un d\u00eda vas a verlo en el circuito como si siempre hubiera estado.\n\nSi quer\u00e9s darle ese proceso, te paso los n\u00fameros:\n\n\U0001f4cb Plan trimestral (3 meses):\n\u2022 Trimestral: \u20b2 690.000\n\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000\n\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba\n\u2022 Total: \u20b2 740.000\n\nLo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa\n\nMariano tiene mucho para dar \u2014 solo necesita su tiempo \U0001f525\n\nAc\u00e1 estamos para acompa\u00f1arlos, Ver\u00f3nica."),

    ("Dirce (3 hijos - 3x2)", "595982138554", "15:30", "prueba",
     "Hola Dirce! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nFue un gustazo recibir a Milagros, Alejandra y Alfredo ayer \u2014 toda una tribu propia \U0001f49b\n\nMilagros demostr\u00f3 ayer que tiene madera \U0001f525. A los 9 a\u00f1os ya entendi\u00f3 algo que muchos adultos no: que el \"no puedo\" se cae cuando lo empuj\u00e1s. La vimos crecer en una sola clase.\n\nAlejandra la rompi\u00f3 ayer \U0001f525. Con 6 a\u00f1os entr\u00f3 al circuito sin miedo, la vimos empujada por la tribu, ganando confianza vuelta tras vuelta.\n\nAyer Alfredo se la jug\u00f3 de verdad \U0001f525. A los 8 a\u00f1os est\u00e1 en la edad clave donde se forma todo: el car\u00e1cter, la disciplina, la cabeza.\n\nPara familias como la suya tenemos una promo especial: 3x2 \u2014 pag\u00e1s por 2 y los 3 entran:\n\n\U0001f4cb Plan trimestral (3 meses):\n\u2022 Trimestrales: \u20b2 690.000 x 2 = \u20b2 1.380.000\n\u2022 Matr\u00edculas: \u20b2 140.000 x 3 = \u20b2 420.000\n\u2022 Menos los \u20b2 150.000 de la prueba\n\u2022 Total: \u20b2 1.650.000\n\nEn 2 pagos: \u20b2 825.000 ahora y \u20b2 825.000 a fin de mes \U0001f4aa\n\nLos 3 quedan cubiertos, cada uno con su camiseta Fenix. \u00bfQu\u00e9 te parece, Dirce?"),

    ("Ruth (Piero+Isaac)", "595973295552", "15:30", "prueba",
     "Hola Ruth! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nTe quer\u00eda escribir sobre Piero e Isaac, porque ayer me dejaron pensando \U0001f49b\n\nPiero demostr\u00f3 ayer que tiene madera \U0001f525. A los 9 a\u00f1os ya entendi\u00f3 algo que muchos adultos no: que el \"no puedo\" se cae cuando lo empuj\u00e1s. Lo vimos crecer en una sola clase.\n\nY de Isaac te tengo que contar aparte. S\u00e9 que el espectro le marca el ritmo. Y por eso lo de ayer me parece todav\u00eda m\u00e1s enorme: lo vimos animarse a m\u00e1s, vuelta tras vuelta. Eso es coraje del bueno. Y tener a Piero ah\u00ed, siendo su referente, suma una capa que no se mide.\n\nPara familias con 2 hijos tenemos descuento de \u20b2 200.000 en el segundo hijo:\n\n\U0001f4cb Plan trimestral (3 meses):\n\u2022 1er hijo: \u20b2 690.000\n\u2022 2do hijo (descuento): \u20b2 490.000\n\u2022 Matr\u00edculas: \u20b2 140.000 x 2 = \u20b2 280.000\n\u2022 Menos los \u20b2 120.000 de la prueba\n\u2022 Total: \u20b2 1.340.000\n\nEn 2 pagos: \u20b2 670.000 ahora y \u20b2 670.000 a fin de mes \U0001f4aa\n\nLos vamos a cuidar a los dos como se merecen, Ruth."),

    ("Luis (Lucas Peralta)", "595983273528", "15:30", "prueba",
     "Hola Luis! \U0001f44b Te saluda el profe Iv\u00e1n, de Fenix Kids \U0001f525\n\nLucas es un guerrero chiquito \U0001f525. A los 4 a\u00f1os ya se anima a circuitos que muchos grandes esquivar\u00edan. Lo vimos caer, levantarse y volver a intentarlo \u2014 eso, a esa edad, vale oro.\n\nLa propuesta es esta: cada s\u00e1bado, una vez por semana, construir juntos esos recuerdos que se quedan para toda la vida. No es solo deporte \u2014 es car\u00e1cter, autoestima, tribu.\n\nTe cuento que si Lucas disfrut\u00f3 la experiencia y quieren que la siga viviendo, te paso los n\u00fameros:\n\n\U0001f4cb Plan trimestral (3 meses):\n\u2022 Trimestral: \u20b2 690.000\n\u2022 Matr\u00edcula (incluye camiseta Fenix): \u20b2 140.000\n\u2022 Menos los \u20b2 90.000 que ya abonaste por la prueba\n\u2022 Total: \u20b2 740.000\n\nLo pod\u00e9s abonar en 2 pagos: \u20b2 370.000 ahora y \u20b2 370.000 a fin de mes \U0001f4aa\n\nSin presi\u00f3n \u2014 cuando ustedes decidan. \u00bfQu\u00e9 te parece?"),

    ("Hector (Martina)", "595972555062", "11:00", "aurora",
     "Hola H\u00e9ctor! \U0001f44b Ac\u00e1 te paso un mensaje de Fenix Kids \U0001f525\n\nMartina vuela \U0001f333. Cada s\u00e1bado la vemos un paso m\u00e1s fuerte, m\u00e1s coordinada, m\u00e1s parte de la tribu. Disfrutala porque est\u00e1 atravesando un momento precioso.\n\nGracias por confiar en nosotros cada semana. Que Martina est\u00e9 ac\u00e1 no es casualidad \u2014 es decisi\u00f3n tuya, y se nota. Nos vemos el pr\u00f3ximo s\u00e1bado \U0001f525"),
]


async def main():
    total = len(DATOS)
    records_creados = []

    for i, (nombre, tel, turno, tipo, msg) in enumerate(DATOS, 1):
        # 1. Crear registro en SEGUIMIENTO FENIX
        campos = {
            "FECHA": "2026-05-09",
            "MENSAJE": msg,
            "TELEFONO": tel,
            "TURNO": turno,
            "ENVIADO": False,
        }
        rec = await _post(_SEGUIMIENTO, campos)
        rec_id = rec["id"] if rec else None
        if rec_id:
            records_creados.append(rec_id)

        # 2. Enviar mensaje al admin para copiar
        await enviar_texto(msg)
        await asyncio.sleep(1)

        # 3. Enviar botones con link wa.me
        btn_env = f"seg_enviado_{rec_id}" if rec_id else f"seg_e_{i}"
        btn_desc = f"seg_descartado_{rec_id}" if rec_id else f"seg_d_{i}"
        await enviar_2botones(
            f"{i}/{total} \u2014 {nombre}\nhttps://wa.me/{tel}",
            btn_env, "\u2705 Enviado",
            btn_desc, "\u274c Descartar"
        )
        await asyncio.sleep(1.5)

        print(f"[{i}/{total}] {nombre}: Airtable={'OK' if rec_id else 'FALLO'}")

    print(f"\nListo! {len(records_creados)} registros en SEGUIMIENTO FENIX.")
    print("Cuando clickees 'Enviado' en cada botón, se marca en Airtable.")


if __name__ == "__main__":
    asyncio.run(main())
