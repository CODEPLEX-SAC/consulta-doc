CREATE TABLE IF NOT EXISTS ubigeos_sunat (
  ubigeo       CHAR(6)      PRIMARY KEY,
  departamento VARCHAR(50)  NOT NULL,
  provincia    VARCHAR(50)  NOT NULL,
  distrito     VARCHAR(50)  NOT NULL
);
