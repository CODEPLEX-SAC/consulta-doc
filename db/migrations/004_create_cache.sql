CREATE TABLE IF NOT EXISTS cache_consulta (
  rucdni    CHAR(11)   PRIMARY KEY,
  payload   JSONB      NOT NULL,
  fuentes   VARCHAR(100),
  expira_en TIMESTAMP  NOT NULL,
  creado_en TIMESTAMP  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cache_expira ON cache_consulta (expira_en);
