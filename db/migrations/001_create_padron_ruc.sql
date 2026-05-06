CREATE TABLE IF NOT EXISTS padron_reducido_ruc (
  ruc                   CHAR(11) PRIMARY KEY,
  nombre_razon          VARCHAR(300),
  estado_contribuyente  VARCHAR(50),
  condicion_domicilio   VARCHAR(50),
  ubigeo                CHAR(6),
  tipo_via              VARCHAR(50),
  nombre_via            VARCHAR(200),
  codigo_zona           VARCHAR(100),
  tipo_zona             VARCHAR(200),
  numero                VARCHAR(30),
  interior              VARCHAR(30),
  lote                  VARCHAR(30),
  departamento_addr     VARCHAR(20),
  manzana               VARCHAR(20),
  kilometro             VARCHAR(20),
  fecha_inscripcion     DATE,
  direccion_completa    VARCHAR(500),
  fecha_actualizacion   TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pr_ruc_ubigeo  ON padron_reducido_ruc (ubigeo);
CREATE INDEX IF NOT EXISTS idx_pr_ruc_estado  ON padron_reducido_ruc (estado_contribuyente);
CREATE INDEX IF NOT EXISTS idx_pr_ruc_nombre  ON padron_reducido_ruc (nombre_razon);
