CREATE TABLE IF NOT EXISTS padron_meta (
  padron_tipo          VARCHAR(50)  PRIMARY KEY,
  ultima_descarga      TIMESTAMP,
  ultima_importacion   TIMESTAMP,
  filas_importadas     BIGINT,
  estado_ultimo_import VARCHAR(20),
  mensaje_error        VARCHAR(500),
  hash_archivo         VARCHAR(64)
);
