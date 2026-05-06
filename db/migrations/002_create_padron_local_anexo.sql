CREATE TABLE IF NOT EXISTS padron_reducido_local_anexo (
  id                     UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ruc                    CHAR(11) NOT NULL,
  codigo_establecimiento VARCHAR(10) NOT NULL,
  tipo_establecimiento   VARCHAR(50),
  ubigeo                 CHAR(6),
  tipo_via               VARCHAR(50),
  nombre_via             VARCHAR(200),
  codigo_zona            VARCHAR(100),
  tipo_zona              VARCHAR(200),
  numero                 VARCHAR(30),
  interior               VARCHAR(30),
  lote                   VARCHAR(30),
  departamento_addr      VARCHAR(20),
  manzana                VARCHAR(20),
  kilometro              VARCHAR(20),
  actividad_economica    VARCHAR(500),
  direccion_completa     VARCHAR(500),
  fecha_actualizacion    TIMESTAMP DEFAULT now(),
  UNIQUE (ruc, codigo_establecimiento)
);

CREATE INDEX IF NOT EXISTS idx_pr_la_ruc    ON padron_reducido_local_anexo (ruc);
CREATE INDEX IF NOT EXISTS idx_pr_la_ubigeo ON padron_reducido_local_anexo (ubigeo);
