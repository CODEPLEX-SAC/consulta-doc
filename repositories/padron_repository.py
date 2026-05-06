"""Consultas a las tablas padron_reducido_ruc y padron_reducido_local_anexo."""
from db.connection import get_db


def buscar_por_ruc(ruc: str):
    """
    Retorna los datos del Padrón para un RUC.
    Si padron_reducido_ruc no tiene ubigeo/dirección, completa desde padron_reducido_local_anexo.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ruc, nombre_razon, estado_contribuyente, condicion_domicilio,
                       ubigeo, direccion_completa, fecha_inscripcion
                FROM padron_reducido_ruc
                WHERE ruc = %s
                """,
                (ruc,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [
                "ruc", "nombre_razon", "estado_contribuyente", "condicion_domicilio",
                "ubigeo", "direccion_completa", "fecha_inscripcion",
            ]
            datos = dict(zip(cols, row))

            # Si no hay ubigeo/dirección, intentar desde local_anexo
            if not datos.get("ubigeo") or not datos.get("direccion_completa"):
                cur.execute(
                    """
                    SELECT ubigeo, direccion_completa
                    FROM padron_reducido_local_anexo
                    WHERE ruc = %s
                    LIMIT 1
                    """,
                    (ruc,),
                )
                la = cur.fetchone()
                if la:
                    if not datos.get("ubigeo") and la[0]:
                        datos["ubigeo"] = la[0]
                    if not datos.get("direccion_completa") and la[1]:
                        datos["direccion_completa"] = la[1]

            return datos


def buscar_anexos_por_ruc(ruc: str):
    """Retorna la lista de establecimientos anexos de un RUC."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT codigo_establecimiento, tipo_establecimiento,
                       ubigeo, direccion_completa, actividad_economica
                FROM padron_reducido_local_anexo
                WHERE ruc = %s
                ORDER BY codigo_establecimiento
                """,
                (ruc,),
            )
            rows = cur.fetchall()
            cols = ["codigo", "tipo", "ubigeo", "direccion", "actividad"]
            return [dict(zip(cols, r)) for r in rows]
