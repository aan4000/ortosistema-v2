-- OrtoSistema · esquema PostgreSQL (Neon)
-- Todo es idempotente: se puede ejecutar sobre una base vacía o sobre una que ya existe.

create table if not exists usuarios(
  id serial primary key,
  usuario text unique not null,
  nombre text not null,
  rol text not null check (rol in ('admin','medico','secretaria','fisio')),
  password_hash text not null,
  activo boolean not null default true,
  debe_cambiar_clave boolean not null default false);
alter table usuarios add column if not exists debe_cambiar_clave boolean not null default false;
alter table usuarios add column if not exists modulos jsonb;

create sequence if not exists paciente_codigo_seq start 1;
create sequence if not exists paciente_expediente_seq start 1;
select setval('paciente_expediente_seq', coalesce((select max(id) from pacientes), 1));
create table if not exists pacientes(
  id serial primary key,
  codigo text unique,
  expediente text unique,
  nombre text not null, edad int, cedula text, seguro text,
  alergias text, diagnostico text, ocupacion text,
  etapa int not null default 0,
  creado_en timestamptz not null default now());
alter table pacientes add column if not exists codigo text unique;
alter table pacientes add column if not exists ocupacion text;
alter table pacientes add column if not exists expediente text unique;
alter table pacientes alter column expediente set default ('EXP-' || lpad(nextval('paciente_expediente_seq')::text, 4, '0'));
alter table pacientes alter column codigo set default ('P-' || lpad(nextval('paciente_codigo_seq')::text, 4, '0'));
alter table pacientes add column if not exists antecedentes_morbidos text;
alter table pacientes add column if not exists antecedentes_quirurgicos text;
alter table pacientes add column if not exists medicamentos text;
alter table pacientes add column if not exists antecedentes_familiares text;
alter table pacientes add column if not exists habitos text;
alter table pacientes add column if not exists fecha_nacimiento date;
alter table pacientes add column if not exists sexo text;
alter table pacientes add column if not exists telefono text;
alter table pacientes add column if not exists correo text;
alter table pacientes add column if not exists numero_afiliado text;
-- Estado del episodio: atención, autorización, datos de la autorización e historial de cambios.
alter table pacientes add column if not exists estado_atencion text not null default 'Por agendar';
alter table pacientes add column if not exists estado_autorizacion text not null default 'Por solicitar';
alter table pacientes add column if not exists autorizacion jsonb not null default '{}'::jsonb;
alter table pacientes add column if not exists historial jsonb not null default '[]'::jsonb;

create table if not exists citas(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null, hora time, motivo text);
alter table citas add column if not exists duracion int not null default 30;
alter table citas add column if not exists tipo text default 'Control';
alter table citas add column if not exists medico text;
alter table citas add column if not exists estado text not null default 'Programada';
alter table citas add column if not exists motivo_cancelacion text;

create table if not exists evaluaciones(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, texto text not null);
alter table evaluaciones add column if not exists tipo text;
alter table evaluaciones add column if not exists medico text;
alter table evaluaciones add column if not exists detalle jsonb not null default '{}'::jsonb;
alter table evaluaciones add column if not exists verificado_por text;
alter table evaluaciones add column if not exists verificado_en timestamptz;

create table if not exists estudios_imagenes(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, tipo text, estado text default 'Por revisar', informe text);
alter table estudios_imagenes add column if not exists region text;
alter table estudios_imagenes add column if not exists lado text;
alter table estudios_imagenes add column if not exists miniatura text;
alter table estudios_imagenes add column if not exists verificado_por text;
alter table estudios_imagenes add column if not exists verificado_en timestamptz;

create table if not exists cirugias(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date, procedimiento text not null, estado text default 'Programada');
alter table cirugias add column if not exists hora time;
alter table cirugias add column if not exists lado text;
alter table cirugias add column if not exists duracion text;
alter table cirugias add column if not exists sala text;
alter table cirugias add column if not exists cirujano text;
alter table cirugias add column if not exists anestesia text;
alter table cirugias add column if not exists implantes_previstos text;
alter table cirugias add column if not exists checklist jsonb not null default '[]'::jsonb;
alter table cirugias add column if not exists sin_autorizacion boolean not null default false;
alter table cirugias add column if not exists verificado_por text;
alter table cirugias add column if not exists verificado_en timestamptz;
alter table cirugias add column if not exists tipo_sangre text;
-- Migracion unica: copia el tipo de sangre del paciente a sus cirugias (si la columna vieja aun existe).
do $$ begin
  if exists (select 1 from information_schema.columns
             where table_schema='public' and table_name='pacientes' and column_name='tipo_sangre') then
    update cirugias c set tipo_sangre = p.tipo_sangre
      from pacientes p where c.paciente_id = p.id
        and c.tipo_sangre is null and p.tipo_sangre is not null;
  end if;
end $$;
-- Limpieza final: quitar los campos movidos/eliminados del paciente.
alter table pacientes drop column if exists tipo_sangre;
alter table pacientes drop column if exists direccion;

create table if not exists implantes(
  id serial primary key,
  cirugia_id int references cirugias(id) on delete cascade,
  paciente_id int not null references pacientes(id) on delete cascade,
  descripcion text, lote text);

create table if not exists pt_sesiones(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, descripcion text, dolor int check (dolor between 0 and 10));
alter table pt_sesiones add column if not exists verificado_por text;
alter table pt_sesiones add column if not exists verificado_en timestamptz;

create table if not exists formularios_proms(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, cuestionario text, puntaje int);
alter table formularios_proms add column if not exists verificado_por text;
alter table formularios_proms add column if not exists verificado_en timestamptz;

create table if not exists referimientos(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, detalle text, estado text default 'Pendiente');
alter table referimientos add column if not exists verificado_por text;
alter table referimientos add column if not exists verificado_en timestamptz;

create table if not exists autorizaciones_preauth(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  procedimiento text, seguro text, estado text default 'Por solicitar', vence date);
alter table autorizaciones_preauth add column if not exists verificado_por text;
alter table autorizaciones_preauth add column if not exists verificado_en timestamptz;
alter table autorizaciones_preauth add column if not exists diagnostico text;
alter table autorizaciones_preauth add column if not exists justificacion text;
alter table autorizaciones_preauth add column if not exists monto numeric;
alter table autorizaciones_preauth add column if not exists medico text;
alter table autorizaciones_preauth add column if not exists centro text;

create table if not exists cargos_facturacion(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, codigo text, concepto text,
  monto numeric(12,2) not null default 0, estado text default 'Pendiente');
alter table cargos_facturacion add column if not exists medico text;
alter table cargos_facturacion add column if not exists verificado_por text;
alter table cargos_facturacion add column if not exists verificado_en timestamptz;

create table if not exists documentos(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  nombre text not null, url text);
alter table documentos add column if not exists tipo text;
alter table documentos add column if not exists fecha date default current_date;
alter table documentos add column if not exists archivo bytea;
alter table documentos add column if not exists mime text;
alter table documentos add column if not exists tamano int;
alter table documentos add column if not exists verificado_por text;
alter table documentos add column if not exists verificado_en timestamptz;

create table if not exists tarifario(
  id serial primary key,
  codigo text, nombre text not null, fuente text);
alter table tarifario add column if not exists precio numeric(12,2) not null default 0;
alter table tarifario add column if not exists categoria text;

create table if not exists procedimientos_paciente(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, procedimiento text not null,
  codigo text, categoria text, precio numeric(12,2) not null default 0,
  medico text, estado text default 'Indicado');
alter table procedimientos_paciente add column if not exists verificado_por text;
alter table procedimientos_paciente add column if not exists verificado_en timestamptz;

create table if not exists ortesis_paciente(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, ortesis text not null, categoria text,
  lado text, talla text, indicacion text, medico text, estado text default 'Indicada');
alter table ortesis_paciente add column if not exists verificado_por text;
alter table ortesis_paciente add column if not exists verificado_en timestamptz;

create table if not exists imagenes_estudio(
  id serial primary key,
  estudio_id int not null references estudios_imagenes(id) on delete cascade,
  mime text not null, datos bytea not null,
  creado_en timestamptz not null default now());

create table if not exists auditoria(
  id bigserial primary key,
  usuario text not null, accion text not null, tabla text, registro_id int,
  fecha timestamptz not null default now());

create table if not exists funciones_rol(
  rol text not null, modulo text not null, primary key (rol, modulo));

create index if not exists ix_pac_nombre on pacientes(lower(nombre));
create index if not exists ix_pac_cedula on pacientes(cedula);
create index if not exists ix_citas_fecha on citas(fecha);
create index if not exists ix_estudios_pac on estudios_imagenes(paciente_id);
create index if not exists ix_cirugias_pac on cirugias(paciente_id);
create index if not exists ix_aud_fecha on auditoria(fecha);


-- Recetas (medicamentos ortopedicos y protesis).
create table if not exists recetas(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date,
  tipo text not null check (tipo in ('medicamento','protesis')),
  titulo text,
  items jsonb not null default '[]'::jsonb,
  notas text,
  medico text,
  creado_en timestamptz not null default now());
alter table recetas add column if not exists verificado_por text;
alter table recetas add column if not exists verificado_en timestamptz;
create index if not exists ix_recetas_pac on recetas(paciente_id);

-- Codigo de paciente: rellenar los que no lo tengan y sincronizar la secuencia.
update pacientes set codigo = 'P-' || lpad(id::text, 4, '0') where codigo is null;
select setval('paciente_codigo_seq', coalesce((select max(id) from pacientes), 1));

-- ============================================================
-- Perfiles, seguridad y recuperacion de acceso (actualizacion 2026)
-- ============================================================

-- Roles nuevos: enfermeria (apoyo clinico) y facturacion (gestion de cobros).
-- El bloque solo cambia la restriccion si aun no incluye los roles nuevos.
do $$
declare def text;
begin
  select pg_get_constraintdef(oid) into def
    from pg_constraint where conname = 'usuarios_rol_check';
  if def is null or def not like '%enfermeria%' then
    alter table usuarios drop constraint if exists usuarios_rol_check;
    alter table usuarios add constraint usuarios_rol_check
      check (rol in ('admin','medico','enfermeria','secretaria','fisio','facturacion'));
  end if;
end $$;

-- Datos de perfil y control de sesiones.
alter table usuarios add column if not exists correo text;
alter table usuarios add column if not exists telefono text;
alter table usuarios add column if not exists cargo text;
alter table usuarios add column if not exists ultimo_ingreso timestamptz;
alter table usuarios add column if not exists token_version int not null default 0;
alter table usuarios add column if not exists preguntas_config_en timestamptz;
alter table usuarios add column if not exists bloqueado_hasta timestamptz;

-- Preguntas de seguridad: 3 respuestas por usuario, guardadas como hash bcrypt.
create table if not exists preguntas_seguridad(
  id serial primary key,
  usuario_id int not null references usuarios(id) on delete cascade,
  orden int not null,
  pregunta text not null,
  respuesta_hash text not null,
  creado_en timestamptz not null default now(),
  unique (usuario_id, orden));
create index if not exists ix_preg_usr on preguntas_seguridad(usuario_id);

-- Bitacora de intentos de recuperacion (nunca guarda respuestas ni claves).
create table if not exists recuperaciones(
  id bigserial primary key,
  usuario text not null,
  ip text,
  exito boolean not null default false,
  creado_en timestamptz not null default now());
create index if not exists ix_recup_fecha on recuperaciones(creado_en);
-- backfill expediente para pacientes existentes
update pacientes set expediente='EXP-'||lpad(id::text,4,'0') where expediente is null;
