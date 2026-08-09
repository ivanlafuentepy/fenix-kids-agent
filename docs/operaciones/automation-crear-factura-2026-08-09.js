// AUTOMATION "CREAR FACTURA" — versión Etapa 2 (adiós TUTORES FENIX, 09/08/2026)
// ─────────────────────────────────────────────────────────────────────────────
// CÓMO APLICAR (Iván, ~1 min): Airtable → Automations → CREAR FACTURA →
// abrir el paso "Run script" → borrar todo → pegar ESTE script → Update.
// (La API no permite editar scripts de automations — tiene que ser por la UI.)
//
// QUÉ CAMBIA vs la versión del 03/08:
// 1. Si el pago es de FENIX (FUENTE), la factura linkea TAMBIÉN "TUTOR (ALUMNOS)"
//    → el robot facturador la marca como Fenix y Aurora le entrega el PDF por
//    WhatsApp (el loop de fenix-kids-agent lee OR({TUTOR},{TUTOR (ALUMNOS)})).
//    Hasta ahora las facturas de la GUI quedaban invisibles para ese envío.
// 2. Comentarios al día: Aurora ya NO escribe el link legacy PAGA (→TUTORES);
//    desde el 09/08 escribe PAGA (ALUMNOS). La rama TUTOR legacy queda solo
//    para pagos viejos y muere cuando se borre TUTORES FENIX LEGACY.

let pagosTable = base.getTable("PAGOS");
let facturasTable = base.getTable("FACTURAS");

let inputConfig = input.config();
let recordId = inputConfig.recordId;

if (!recordId) {
    throw new Error("No se recibió el RECORD ID.");
}

let pago = await pagosTable.selectRecordAsync(recordId);

if (!pago) {
    throw new Error("No se encontró el registro en PAGOS.");
}

// =========================
// CAMPOS PAGOS
// =========================
let alumno = pago.getCellValue("ALUMNO");

// PAGA (link legacy a TUTORES FENIX): solo pagos ANTERIORES al 09/08/2026.
// Aurora ya no lo escribe (Etapa 2 adiós-TUTORES) — escribe PAGA (ALUMNOS).
let paga = pago.getCellValue("PAGA");

// PAGA (ALUMNOS) = el adulto que pagó, fila de ALUMNOS. Lo escriben la GUI
// del control de acceso Y Aurora (fenix-kids-agent, desde el 09/08/2026).
// NO se usa el campo ALUMNO para el pagador: ALUMNO alimenta el rollup
// ULTIMO VENCIMIENTO y le abriría el molinete a un papá que no baila.
let pagaAlumnos = pago.getCellValue("PAGA (ALUMNOS)");

let monto = pago.getCellValue("MONTO");

// FUENTE = el negocio. Define la descripción que sale en la factura ante la SET
// (SALSA SOUL STUDIO / FENIX KIDS ACADEMY / IMPULSO IA). Si no se copia, la factura
// nace con el valor por defecto del campo y todo sale como Salsa.
let fuente = pago.getCellValue("FUENTE");

// =========================
// VALIDACIÓN
// =========================
let tieneAlumno = alumno && alumno.length > 0;

let tienePagaAlumnos = pagaAlumnos && pagaAlumnos.length > 0;

let tienePaga = paga && paga.length > 0;

if (!tieneAlumno && !tienePagaAlumnos && !tienePaga) {

    throw new Error(
        "No hay ALUMNO, PAGA (ALUMNOS) ni PAGA (tutor)."
    );
}

// =========================
// CREAR FACTURA
// =========================
let nuevaFactura = {

    "MONTO": monto,

    "PAGO": [
        { id: recordId }
    ],

    "GENERAR FACTURA": true
};

// =========================
// FUENTE (negocio)
// =========================
let esFenix = fuente && fuente.name === "FENIX KIDS ACADEMY";

if (fuente) {

    nuevaFactura["FUENTE"] = {
        name: fuente.name
    };
}

// =========================
// VINCULAR
// =========================
if (tieneAlumno) {

    nuevaFactura["ALUMNO"] = [
        { id: alumno[0].id }
    ];

} else if (tienePagaAlumnos) {

    // El pagador vive en ALUMNOS → va al campo ALUMNO de la factura (su lookup
    // RUC saca el CI de ALUMNOS, mismo camino que las facturas de Salsa).
    nuevaFactura["ALUMNO"] = [
        { id: pagaAlumnos[0].id }
    ];

    // Si el pago es de FENIX, linkear TAMBIÉN TUTOR (ALUMNOS): así el robot
    // marca la factura como Fenix y Aurora le entrega el PDF por WhatsApp.
    if (esFenix) {
        nuevaFactura["TUTOR (ALUMNOS)"] = [
            { id: pagaAlumnos[0].id }
        ];
    }

} else {

    // Camino LEGACY (solo pagos viejos con PAGA → TUTORES FENIX). Muere cuando
    // se borre esa tabla: para entonces ya no debería quedar ningún pago sin
    // PAGA (ALUMNOS) que dispare esta automation.
    nuevaFactura["TUTOR"] = [
        { id: paga[0].id }
    ];
}

// =========================
// CREATE RECORD
// =========================
await facturasTable.createRecordAsync(
    nuevaFactura
);
