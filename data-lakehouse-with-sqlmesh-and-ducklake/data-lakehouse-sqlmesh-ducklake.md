# Data Lakehouse with SQLMesh and DuckLake

## Summary

Now that you can use DuckDB to power your data lakehouse through DuckLake, you'll
also save space on snapshots due to the ability to reference parts of parquet files
(yes, you can keep all old versions, with little impact to storage), and you'll get
improved performance for small change operations due to data inlining, which lets
data be stored directly within the metadata database (PostgreSQL, in our case).

With a little help from SQLMesh, we were able to design a data lakehouse strategy
covering data ingestion, transformation, and exporting, almost exclusively based on
SQL. This is a port of the original
[datalab](https://github.com/DataLabTechTV/datalab) project, which was built on
dbt, MinIO and SQLite, with three substitutions:

| Original | This project |
| --- | --- |
| MinIO (S3-compatible object storage) | **RustFS** |
| dbt (transformations) | **SQLMesh** |
| SQLite (DuckLake metadata catalog, per data mart) | **PostgreSQL** (one database, one schema per catalog) |

Everything else is kept: the dated `raw/` ingestion layout, the `stage` and mart
catalogs, the `dlctl` CLI, the parquet exports, and the full model set (Deezer
social networks, Million Song Dataset, The Atlas of Economic Complexity, depression
detection).

## Architecture

Here's an overview of a Data Lab workflow to retrieve and organize a dataset
(`ingest`), transform it into structured tables tracked by DuckLake (`transform`),
and export them for external use (`export`):

```
        ingest                 transform                   export
   ┌──────────────┐        ┌──────────────────┐      ┌──────────────────┐
   │  RustFS S3   │        │  SQLMesh         │      │  RustFS S3       │
   │  s3://.../raw│──────▶ │  DuckDB engine   │────▶ │  s3://.../exports│
   └──────────────┘        │  DuckLake tables │      └──────────────────┘
                           └────────┬─────────┘
                                    │ metadata (schemas, snapshots, statistics)
                              ┌─────▼──────┐
                              │ PostgreSQL │  DuckLake catalogs: stage,
                              │ lakehouse  │  secure_stage, graphs, analytics
                              └────────────┘
```

- **RustFS** stores raw datasets, the DuckLake-managed parquet files, and the
  exported datasets. It is S3-compatible, so DuckDB's `httpfs` and `boto3` both
  talk to it directly.
- **DuckDB** is the query engine. A local `local/engine.duckdb` file holds the
  SQLMesh state, and the DuckLake catalogs are attached to it on every connection.
- **PostgreSQL** holds DuckLake metadata: one schema per catalog inside the
  `lakehouse` database. This replaces the per-mart SQLite files from the original
  project, and also makes `pg_dump` backups possible.
- **DuckLake** provides ACID tables, snapshots and time travel on top of plain
  parquet files.
- **SQLMesh** runs the transformations and the audits.

### Storage Layout

Let's begin with the storage layout. We use an S3 compatible object store (RustFS),
but you could store your files locally as well (not supported by Data Lab, but easy
to implement, as DuckLake supports it).

```
s3://lakehouse/
├── backups/
│   └── catalog/
│       ├── YYYY_MM_DD/
│       │   └── HH_mm_SS_sss/
│       │       └── lakehouse.dump
│       └── manifest.json
├── raw/
│   └── <dataset-name>/
│       ├── YYYY_MM_DD/
│       │   └── HH_mm_SS_sss/
│       │       ├── *.csv
│       │       ├── *.json
│       │       └── *.parquet
│       └── manifest.json
├── stage/
│   └── ducklake-*.parquet
├── secure-stage/
│   └── ducklake-*.parquet
├── marts/
│   ├── graphs/
│   │   └── ducklake-*.parquet
│   └── analytics/
│       └── ducklake-*.parquet
└── exports/
    └── <domain>/
        └── <dataset-name>/
            ├── YYYY_MM_DD/
            │   └── HH_mm_SS_sss/
            │       ├── nodes/*.parquet
            │       └── edges/*.parquet
            └── manifest.json
```

The directory structure above contains:

- `raw/`, which is where you drop your datasets, as they come (usually
  uncompressed, e.g., if it's a zip file), and you can do this either manually or
  exclusively via the CLI.
- `stage/` is where parquet files for DuckLake are stored for intermediate
  transformations.
- `secure-stage/` is the same, for the encrypted catalog (`ENCRYPTED 1`).
- `marts/` contains a subdirectory per data mart—I set up mine based on types of
  data (e.g., `graphs`) or relevant subjects I'm exploring (e.g., `analytics`), but
  the classical setup is by company department (this shouldn't be your case, as
  this is not production-ready, it's a lab).
- `exports/` contains exported datasets, usually in parquet format (the only one
  supported by Data Lab right now), ready to be used or loaded elsewhere. Tables
  whose names contain `nodes` or `edges` are placed into `nodes/` and `edges/`
  subdirectories.
- `backups/` contains snapshots of the metadata catalog. Because the catalog now
  lives in PostgreSQL, a backup is a single `pg_dump` file rather than a set of
  per-mart SQLite databases.

In some cases, you'll find a path containing a directory representing a date and a
subdirectory representing a time—this is the timestamp from when the associated
operation was started. We call these "dated directories". Each dated directory
contains a `manifest.json` with the dataset name (or snapshot name, for backups),
along with the S3 path with the location of the latest version of that dataset.

### DuckLake catalogs

| Catalog | PostgreSQL schema | Purpose |
| --- | --- | --- |
| `stage` | `stage` | Cleaned, typed source data |
| `secure_stage` | `secure_stage` | Encrypted catalog (`ENCRYPTED 1`) |
| `graphs` | `graphs` | Graph marts: nodes and edges |
| `analytics` | `analytics` | Analytical marts |

Adding a mart only requires two environment variables: a
`PSQL_CATALOG_<NAME>_MART_SCHEMA` and a matching `S3_<NAME>_MART_PREFIX`. Both the
`init.sql` generator and the SQLMesh configuration pick them up automatically, so a
new mart is discovered by name rather than by editing code.

## Tech Stack

### RustFS

We used RustFS, but you can use any S3-compatible object storage. RustFS is a
recent Rust-based S3-compatible store, which is appealing here because the
Community Edition of MinIO recently lost most of its features—yes, sadly this
includes users, groups, and policies as well.

If you're having trouble connecting, the usual culprits are `S3_URL_STYLE` (use
`path` for a local instance) and `S3_REGION` (it must match the store's
configuration, otherwise requests are rejected with a signature error). For the
bundled local services, `.env` looks like this:

```sh
S3_ENDPOINT=localhost:9000
S3_USE_SSL=false
S3_URL_STYLE=path
S3_ACCESS_KEY_ID=rustfsadmin
S3_SECRET_ACCESS_KEY=rustfsadmin
S3_REGION=us-east-1
```

Since RustFS is only an object store, it does not care about DuckLake at all: it
just serves the parquet files that DuckLake writes. You can bring it up with:

```sh
just infra-provision-local   # RustFS (9000/9001) + PostgreSQL (5432) in Docker
```

### DuckDB and DuckLake

While RustFS provides storage, DuckDB provides compute (we call it the "engine"),
and DuckLake provides a catalog layer to manage metadata and external tables,
tracking changes and offering snapshots, schema evolution, and time travel.

Two details are worth calling out, because they shape the rest of the project:

- DuckLake is attached **through** DuckDB, so `ATTACH 'ducklake:' AS graphs (...)`
  turns a PostgreSQL schema into a catalog that DuckDB can query like any other
  database. There is no service to run and no client library to adopt.
- Each catalog keeps its **own snapshot sequence**. `stage` and `graphs` are
  independent DuckLakes that happen to share a PostgreSQL instance and an object
  store, so their snapshot IDs are not comparable.

### SQLMesh

Tools like SQLMesh appear once in a lifetime—much like DuckDB.

SQLMesh is for SQL templating and organization (models), and data documentation
and testing (audits). It provides a few configuration files to help you link up to
external data sources as well, but, overall, this is it. Beautifully simple, yet
extremely useful.

Because SQLMesh connects through DuckDB, it reaches our DuckLake catalogs with no
adapter work at all: the catalogs are declared in the connection as
`DuckDBAttachOptions`, and every model is then addressed by
`<catalog>.<schema>.<table>`. We used pure DuckDB SQL queries to extract our data
from the S3 ingestion bucket (`raw/`) and transform it into usable structured
tables (`stage/` and `marts/`).

The project lives in `transform/`:

```
transform/
├── config.py       # gateways, DuckLake catalogs, RustFS secret, variables
├── audits/         # generic + project audits
├── macros/         # Jinja macros for the Deezer loaders
└── models/
    ├── stage/      # stage.dsn.*, stage.msdsl.*, stage.taoec.*, stage.dd.*
    └── marts/      # graphs.* and analytics.*
```

Model names carry over from the dbt project unchanged, as
`<catalog>.<schema>.<table>`, so `stage.dsn.hr_edges` and
`graphs.music_taste.nodes_genres` are addressed exactly as before.

### PostgreSQL

The catalog backend is a single PostgreSQL database (`lakehouse`) with one schema
per DuckLake catalog. Compared to a SQLite file per mart, this buys us three
things:

1. One connection string instead of a growing pile of files that have to be
   copied, backed up and restored individually.
2. Concurrent writers: DuckLake commits its metadata transactionally, and
   PostgreSQL handles that natively.
3. Backups for free: `pg_dump`/`pg_restore` are battle-tested tools, so
   `dlctl backup` is a thin wrapper around them.

The trade-off is that PostgreSQL becomes a hard dependency of the lakehouse: if it
is down, the catalogs cannot be attached at all. For a lab, having both services in
Docker Compose is a fine exchange.

## Operations

Below is an overview of the main lakehouse-related operations that Data Lab
supports.

When required, the `dlctl` CLI tool will read the manifests and export environment
variables pointing to the S3 path with the latest version for each dataset. For
example, `RAW__DEEZER_SOCIAL_NETWORKS__HR__HR_GENRES` will point to something like
`s3://lakehouse/raw/deezer_social_networks/2025_06_11/11_56_29_470/HR/HR_genres.json`,
where the key point here is the date, `2025-06-11T11:56:29.470`, which points to the
most recent ingestion of that dataset.

Both ingestions (`raw/`) and exports (`exports/`) can be listed using the CLI:

```sh
dlctl ingest ls
dlctl ingest ls -a

dlctl export ls
dlctl export ls -a
```

As well as pruned (i.e., all versions except the last one are deleted, per
dataset):

```sh
dlctl ingest prune

dlctl export prune
```

Other than that, catalog backups can be created (which shells out to `pg_dump`
against the PostgreSQL catalog):

```sh
# Dump the catalog and update manifest.json accordingly
dlctl backup create
```

Listed:

```sh
# List backup root directories
dlctl backup ls

# List all backed up files
dlctl backup ls -a
```

And restored:

```sh
# Restore the latest catalog snapshot into PostgreSQL
dlctl backup restore

# Restore a specific snapshot
dlctl backup restore --source 2025-06-17T16:24:31.349
```

There are also `just` recipes for all of these, so you can run
`just backup-create`, `just backup-ls`, `just backup-restore`, `just ingest-ls`,
`just export-ls`, and so on, without activating anything.

### Ingestion

The `dlctl ingest dataset` command supports directory structure creation for manual
uploads, as well as direct retrieval from Kaggle, Hugging Face, and DataCite-backed
dataset templates.

This will create a dated directory for dataset `snap_facebook_large` (snake case is
always used):

```sh
dlctl ingest dataset --manual "SNAP Facebook Large"
```

And the following commands will ingest two datasets, from Kaggle and Hugging Face,
respectively:

```sh
dlctl ingest dataset "https://www.kaggle.com/datasets/andreagarritano/deezer-social-networks"
dlctl ingest dataset "https://huggingface.co/datasets/ShreyaR/DepressionDetection"
```

A template fetch pulls a curated set of files from the original source, and is
useful when the data is not on Kaggle or Hugging Face:

```sh
dlctl ingest dataset -t atlas "The Atlas of Economic Complexity"
```

### Transformation

The `dlctl transform`, `dlctl test`, and `dlctl docs` commands are wrappers for
SQLMesh, although parametrization is specific to `dlctl` (at least for now).

We can run a specific model (and, therefore, its SQL transformations) as follows:

```sh
dlctl transform -m stage.dsn.hr_edges
dlctl transform -m stage.msdsl.*
```

Note that both runs address models by their catalog and schema, and the second one
uses a glob to cover every table in the Million Song Dataset schema.

Upstream/downstream triggering is also supported:

```sh
# The music taste graph models, plus everything they depend on
dlctl transform -m "+graphs.music_taste.*"
```

`+` means "and its upstream", which is the usual way to run a mart: you rarely want
to transform the mart without the stage models feeding it. The justfile wraps the
common cases:

```sh
just graphrag-transform   # dlctl transform -m "+graphs.music_taste.*"
just econ-compnet-transform
just mlops-transform
```

This is the stage that produces DuckLake catalogs, storing DuckLake-managed parquet
files under the `stage/`, `secure-stage/` and `marts/` S3 directories.

Finally, you can also run all data audits as follows:

```sh
dlctl test
```

And generate and serve model documentation as follows:

```sh
dlctl docs generate
dlctl docs serve
```

The documentation command renders the model DAG to `local/docs/` and serves it over
a small local HTTP server, because SQLMesh's own web UI is deprecated.

### How the port maps dbt concepts to SQLMesh

| dbt | SQLMesh |
| --- | --- |
| `dbt run -m "+marts..."` | `dlctl transform -m "+graphs.music_taste.*"` |
| `dbt test` | `dlctl test` (audits) |
| `not_null`, `unique`, `relationships`, `dbt_utils.unique_combination_of_columns` | `not_null`, `unique_values`, `relationships`, `unique_combination_of_columns` |
| `schema.yml` descriptions | `description` / `column_descriptions` |
| `env_var("RAW__X", "NOT_FOUND")` | `@RAW__X` variables, seeded with a placeholder until the dataset is ingested |
| `profiles.yml` targets | `transform/config.py` gateways |
| `dbt docs generate/serve` | `dlctl docs generate` (DAG) and `dlctl docs serve` |

A model in this project looks like this:

```sql
MODEL (
  name stage.dsn.hr_genres,
  kind FULL,
  description 'Croatia genres per user',
  column_descriptions (
    user_id = 'User ID, also the graph node ID suffix',
    genres = 'List of genres, formatted using title case'
  ),
  audits (
    not_null(columns := (user_id)),
    list_not_empty(column := genres)
  )
);

JINJA_QUERY_BEGIN;

{{ load_deezer_genres(var('RAW__DEEZER_SOCIAL_NETWORKS__HR__HR_GENRES')) }}

JINJA_QUERY_END;
```

Three things to notice:

- **Descriptions and audits are metadata**, not separate YAML files, so the model
  and its tests cannot drift apart.
- **Queries generated by Jinja use `JINJA_QUERY_BEGIN` / `JINJA_QUERY_END`.**
  SQLMesh only evaluates Jinja inside these blocks, so the Deezer loader macros are
  wrapped in them.
- **Ingested paths are SQLMesh variables** (`@RAW__<DATASET>__<FILE>`), resolved by
  `dlctl` from the ingestion manifests before SQLMesh starts. A new ingestion
  changes the variables, so SQLMesh re-renders and re-runs the affected models.
  Datasets that have not been ingested yet fall back to a `NOT_FOUND` placeholder,
  so the project can still be loaded and a single mart can be built on its own.

Two more SQLMesh-specific notes:

- **Mart objects are DuckLake tables.** `virtual_environment_mode` is set to
  `DEV_ONLY`, so in prod every model is materialized under its own name
  (`graphs.music_taste.nodes_genres`), instead of being a view on top of a hidden
  physical layer.
- **Audits run per model**, while the plan is being applied. The original project
  had a cross-model "unique node ids" test; here it is expressed as a
  `unique_values` audit on each node model, plus a Python test that asserts the
  cross-model invariant against real data.

### Export

In order to be able to use a dataset externally, you first need to export it, from
the DuckLake-specific parquet format into a usable format, like parquet (or CSV, or
JSON).

This can be done by running:

```sh
dlctl export dataset graphs music_taste
```

Where `graphs` is a data mart catalog and `music_taste` is the schema. Tables with
names matching `*nodes*` and `*edges*` will be stored in subdirectories—`nodes/`
and `edges/` in this case. A similar logic can be added to the export process in
the future, for other categorizable tables. Otherwise, files will live directly in
the root directory, matching the schema name (e.g., `music_taste`).

## DuckDB Highlights

Most of our SQL code was boring, standard stuff, which is not unusual, but there
were also a few interesting points that we cover next.

### Handling the RustFS Secret

Secrets in DuckDB are ephemeral, and exist only for the active session. As such, we
store them in a `.env` file, which we automatically load via `dlctl`. We also offer
a command to create an `init.sql` file under the `local/` directory, directly
generated from your `.env` configuration, once you set it up.

The generated file is the whole lakehouse in miniature: the extensions, the secrets
for both RustFS and PostgreSQL, and the `ATTACH` statements that turn PostgreSQL
schemas into DuckLake catalogs.

```sql
INSTALL httpfs;
INSTALL parquet;
INSTALL postgres;
INSTALL ducklake;

CREATE OR REPLACE SECRET rustfs (
    TYPE s3,
    PROVIDER config,
    KEY_ID '...',
    SECRET '...',
    ENDPOINT 'localhost:9000',
    USE_SSL false,
    URL_STYLE 'path',
    REGION 'us-east-1'
);

CREATE OR REPLACE SECRET postgres (
    TYPE postgres,
    HOST '127.0.0.1',
    PORT 5432,
    DATABASE lakehouse,
    USER 'postgres',
    PASSWORD '...'
);

CREATE OR REPLACE SECRET (
    TYPE ducklake,
    METADATA_PATH '',
    METADATA_PARAMETERS MAP {
        'TYPE': 'postgres',
        'SECRET': 'postgres'
    }
);

ATTACH 'ducklake:' AS stage (
    METADATA_SCHEMA 'stage',
    DATA_PATH 's3://lakehouse/stage'
);

ATTACH 'ducklake:' AS secure_stage (
    METADATA_SCHEMA 'secure_stage',
    DATA_PATH 's3://lakehouse/secure-stage',
    ENCRYPTED 1
);
```

Note that the DuckLake secret carries no credentials of its own: it points at the
PostgreSQL secret by name, which keeps the per-catalog `ATTACH` statements free of
connection details. Accordingly, you can access your Data Lakehouse locally by
running:

```sh
# Generate local/init.sql from your .env
dlctl tools generate-init-sql

# Connect to the data lakehouse
duckdb -init local/init.sql local/engine.duckdb

# Or, with the justfile doing the same thing
just lakehouse
```

### Useful List Functions

Datasets frequently contain string columns with comma-separated lists of items—in
our case, it was tags—so having access to list functions was extremely useful.
Here's the transformation that we used:

```sql
SELECT
	list_transform(
        string_split(tags, ', '),
        tag -> list_aggregate(
            list_transform(
                string_split(tag, '_'),
                tag_word ->
                    ucase(substring(tag_word, 1, 1)) ||
                    lcase(substring(tag_word, 2))
            ),
            'string_agg',
            ' '
        )
    ) AS tags
FROM
	...
```

Let's go through it.

1. `list_transform` will apply a lambda to each tag, given by `string_split` (we
   split by comma and space).
2. `list_aggregate` just applies `string_agg` to concatenate all words in a tag
   with spaces.
3. Words are obtained from `string_split` on underscore, and `list_transform` is
   used to convert to title case.
4. Title case was achieved by taking the first letter of a word via `substring` and
   converting to `ucase` (upper case). The remaining `substring` was converted to
   `lcase` (lower case)—if not already.

For step 4, we could have used a Python UDF (user-defined function) which took a
`str` and just returned `input.title()`, or we could have implemented it fully in
Python, taking the original comma-separated string of tags as the argument. There
would have been a slight overhead, since C++ is faster than Python, but it would
have been perfectly viable for such tiny data.

With dbt, registering such a function was done on top of the `dbt-duckdb` plugins
API, which let the adapter call `conn.create_function(...)` while it configured the
connection. SQLMesh has no equivalent hook on its DuckDB connection—what it offers
instead is Python macros (`@macro`), which generate SQL rather than registering
engine functions. That makes the Python escape hatch a differently shaped tool, and
it also means the pure SQL implementation above is the path of least resistance.
Either way, I would avoid using Python unless strictly necessary—if a working
implementation exists in pure SQL, it's usually more efficient than Python.

### Abnormally Slow JSON Parsing

One of the datasets we ingested and ran transformations for was
andreagarritano/deezer-social-networks, which is found on Kaggle. It contains user
data and friendship relationships for three subsets of Deezer users from Croatia
(`HR`), Hungary (`HU`), and Romania (`RO`). For each country, there are two files:
`*_edges.csv` and `*_genres.json`. The genres JSON looks something like this, but
unformatted:

```json
{
    "13357": ["Pop"],
    "11543": ["Dance", "Pop", "Rock"],
    "11540": ["International Pop", "Jazz", "Pop"],
	"11541": ["Rap/Hip Hop"]
}
```

These files were extremely slow to parse in DuckDB. The largest genres JSON file is
for Croatia, and is only 4.89 MiB. However, when we tried to load and transform this
file using the following query, we got extremely high memory usage (hitting 14 GiB
for DuckDB), and abnormally slow response time:

```sh
CREATE TABLE users AS
SELECT
    CAST(je.key AS INTEGER) AS user_id,
    CAST(je.value AS VARCHAR[]) AS genres
FROM
    read_json('HR/HR_genres.json') j,
    json_each(j.json) je;
```

```
Run Time (s): real 638.958 user 837.703249 sys 438.916651
```

That's nearly 14m.

So, we tried to turn the JSON object into JSON lines, using:

```sh
jq "to_entries[] | {key: .key, value: .value}" \
	HR/HR_genres.json >HR/HR_genres.jsonl
```

Which ran in sub-second time, as expected, and reading `HR/HR_genres.jsonl` inside
DuckDB was then instant and completely RAM-efficient:

```sh
CREATE TABLE users AS
SELECT
    CAST(j.key AS INTEGER) AS user_id,
    CAST(j.value AS VARCHAR[]) AS genres
FROM
    read_json('HR/HR_genres.jsonl') j;
```

```
Run Time (s): real 0.082 user 0.106543 sys 0.032145
```

At first, since so much RAM was in use, we thought the query was actually a
`CROSS JOIN` that replicated the whole JSON object for each produced line in the
final table, but then we noticed that this is not the case, since `json_each` is a
`LATERAL JOIN`.

Besides parsing and transforming the file outside DuckDB before reading it in SQL,
I don't think there was much else we could do here, which was disappointing, as
this would mean we'd have to add another layer to Data Lab, between ingestion and
transformation, that would also do transformation but now in Python. I decided in
favor of sticking with a pure SQL solution, so we posted a question in the GitHub
Discussion for DuckDB, describing the issue, and one of the users was kind enough
to debug the problem with us.

#### First Proposed Solution

The first suggestion was to use one of the following approaches:

```sql
FROM read_json('HR/HR_genres.json', records=false)
SELECT
  unnest(json_keys(json)) AS user_id,
  unnest(list_value(unpack(columns(json.*)))) AS genres
```

```sql
UNPIVOT (FROM read_json('HR/HR_genres.json')) ON *
```

Let's quickly unpack what is going on with these two queries.

##### Query #1

Let's start with the first one. First, we call `read_json` with `records=false`. By
default, `records` is set to `auto`. For `records=true`, each key will become a
column with its corresponding value. For `records=false`, it will either return a
`map(varchar, varchar[])` or a `struct` with each user ID identified as a field
(the latter is what we want to happen here).

`COLUMNS` is essentially an expansion on column selection, like `j.*, col1, *`, but
where we can apply filtering by, or manipulate, the column name(s), with regular
expressions, with `EXCLUDE` and `REPLACE`, or with lambda functions.

Then, `UNPACK` works essentially like `*lst` would do in Python (i.e., it will
expand the elements of a list into arguments for a function). In this example, the
target function is `list_value`, which takes multiple arguments and returns a list
with those arguments.

Finally, for completion's sake, `unnest` just unwinds a list or array into rows, and
`json_keys` returns the keys in a JSON object.

##### Query #2

For the second query, we're just reading the JSON object using `records=auto`, which
translates into `records=true` for the small sample JSON. Then, we are applying
`UNPIVOT` on all columns (the user IDs), so that each becomes a row of user ID and
list of genres.

Both Query #1 and Query #2 worked fine for the small example that we provided, but
failed for the larger original file.

#### Second Proposed (Working) Solution

We found out that the JSON object was parsed differently from 200 user records
onward, and discovered there is a default of `map_inference_threshold=200` for
`read_json`. For long JSON objects like the one we have, this means that it will
stop parsing object keys as structure fields from 200 keys onward, thus returning a
`map(varchar, varchar[])` instead of a `struct`, making the original query fail.

Knowing this, the suggestion was to disable the threshold for map inference and run
the query:

```sql
FROM read_json(
	'HR/HR_genres.json',
	records=false,
	map_inference_threshold=-1
)
SELECT
  unnest(json_keys(json)) AS user_id,
  unnest(list_value(unpack(columns(json.*)))) AS genres
```

This brought down the run time from 14m to 24s, which is a significant speedup, but
still extremely slow compared to the sub-second run time we got from first parsing
the JSON object via `jq` to turn it into JSON lines.

This also made it possible to run the `UNPIVOT` query, which was even faster,
taking only 6s to run:

```sql
UNPIVOT (
	FROM read_json(
		'HR/HR_genres.json',
		records=true,
		map_inference_threshold=-1
	)
) ON *;
```

#### Third Proposed (Creative) Solution

Finally, a third solution based on a variable to store the JSON object keys was also
proposed:

```sql
SET variable user_ids = (
	FROM read_json_objects('HR/HR_genres.json')
	SELECT json_keys(json)
);

FROM read_json_objects('HR/HR_genres.json')
SELECT
	unnest(
        getvariable('user_ids')
    )::INTEGER AS user_id,
	unnest(
		json_extract(
            json,
            getvariable('user_ids')
	    )::VARCHAR[]
    ) AS genres
```

We find it interesting that such a solution design is possible in DuckDB.
Regardless, this version was less efficient than the `UNPIVOT` query on the second
solution, so we went with that.

The question remains. If the best solution takes 6s to run for a 5 MiB file, is
this something that we might need to address in DuckDB, especially when the same
process can run in milliseconds with a little command line magic?

#### The SQLMesh Twist: `UNPIVOT` Cannot Be Traversed

The port to SQLMesh added a wrinkle to this story. The Deezer loader kept the
`UNPIVOT` query, wrapped in a Jinja macro:

```sql
{% macro load_deezer_genres(s3_path) %}

WITH user_genres AS (
    UNPIVOT (
        FROM read_json(
            '{{ s3_path }}',
            records=true,
            map_inference_threshold=-1
        )
    )
    ON *
    INTO
        NAME user_id
        VALUE genres
)
SELECT CAST(user_id AS INTEGER) AS user_id, genres
FROM user_genres

{% endmacro %}
```

The query ran, and the tables it produced were correct, but every run of
`dlctl transform` printed a wall of warnings:

```
Cannot traverse scope UNPIVOT (SELECT * FROM READ_JSON('s3://lakehouse/raw/.../HR_genres.json',
records = TRUE, map_inference_threshold = -1)) ON * INTO NAME user_id VALUE genres
with type '<class 'sqlglot.expressions.query.Pivot'>'
```

The reason is that SQLMesh is not just a SQL runner: before it runs anything, it
parses each model, resolves the column lineage, and expands macros and variables.
That resolution is done with SQLGlot, and SQLGlot's scope traversal handles
`SELECT`, set operations, subqueries, tables, table functions, DDL and DML—but not
a pivot scope. DuckDB's `UNPIVOT` is parsed as a `Pivot` node, so SQLMesh cannot see
through it: it warns and skips the scope, which costs the column-level lineage for
those three models.

Since the whole point of using a transformation framework is that it understands
your models, we replaced `UNPIVOT` with an equivalent that SQLGlot can traverse:

```sql
{% macro load_deezer_genres(s3_path) %}

-- Each file is a single JSON object mapping user IDs to genre lists. `json_each`
-- expands it into rows; DuckDB's `UNPIVOT` would be the shorter equivalent, but
-- SQLMesh's SQLGlot-based lineage cannot traverse its pivot scope.
WITH user_genres AS (
    SELECT
        CAST(j.key AS INTEGER) AS user_id,
        CAST(j.value AS VARCHAR[]) AS genres
    FROM read_json(
            '{{ s3_path }}',
            records=false,
            columns={'user_genres': 'JSON'}
         ) AS t,
         json_each(t.user_genres) AS j(key, value)
)
SELECT user_id, genres
FROM user_genres

{% endmacro %}
```

Three details make this work:

1. `records=false` with `columns={'user_genres': 'JSON'}` reads the whole file as a
   single JSON value. Because the column type is pinned, the reader never has to
   infer a schema, and `map_inference_threshold` is no longer needed at all—the
   threshold problem simply disappears.
2. `json_each` expands the JSON object into one row per key, which is the same
   lateral expansion `UNPIVOT ... ON *` was doing.
3. The explicit column aliases, `AS j(key, value)`, are not decorative. Without
   them SQLGlot cannot resolve `key` and `value`, and the lineage step fails with
   `Column 'key' could not be resolved`—trading one diagnostic for another.

An equivalent that also qualifies cleanly is to cast the object to a map and unwrap
it with list functions:

```sql
CAST(unnest(map_keys(genres_map)) AS INTEGER) AS user_id,
unnest(map_values(genres_map)) AS genres
```

We verified that the rewritten query returns exactly the same rows and types as the
`UNPIVOT` version against a real ingested file, and `dlctl transform` now runs
without a single warning.

The lesson is a pleasant one for the lakehouse idea: the SQL was never the problem.
DuckDB is perfectly happy with `UNPIVOT`, and the 6s run time stands. What changed
was the number of layers reading the SQL—and a catalog/lineage layer has opinions
about what it can traverse.

### DuckDB and DuckLake Wishlist

While we were working with DuckDB and DuckLake, we created a bit of a wishlist,
which we share with you below.

#### 1. Externally Loadable Parquet Files

Currently, using data from DuckLake tables externally requires exporting (e.g., to
parquet). Maybe there isn't a better solution, but it also defies the purpose of a
data lakehouse, as data won't be ready to use without a DuckLake adapter on target
tools, which doesn't seem reasonable to expect any time soon.

It's not clear whether a DuckLake parquet file can be directly read by external
processes, but it seems unlikely to be the case. Whether this is desirable, or a
solid design choice, it is surely up for discussion, but, if we're building on top
of external storage, shouldn't the stored files be ready to use directly?

If we follow that direction, then there is no clear way to match external files to
the tables in DuckLake, as the current naming schema is not designed for
identifying which parquet files are which.

#### 2. Hierarchical Schemas

Hierarchical schemas would be useful (e.g., `marts.graphs.music.nodes`), as this
comes up a lot.

It is how dbt sets up its model logic—they use an `_` for different levels—and it
is also the way disk storage works (i.e., directories are hierarchical), and the
natural way to organize data.

Some teams are even looking into graph-based structures for data cataloging (e.g.,
Netflix). Maybe that could be interesting as a feature for DuckDB and DuckLake, not
to mention an additional distinguishing factor.

#### 3. Sequences in DuckLake

It would be nice to have access to sequences in DuckLake, if that makes sense
technically as well. For example, while preparing nodes, generating node IDs could
be done using sequences instead of something like:

```sql
WITH other_nodes AS (
	SELECT max(node_id) AS last_node_id
	FROM ...
)
SELECT o.last_node_id + row_number() OVER () AS node_id
FROM ..., other_nodes o
```

This is exactly how the genre nodes are numbered in this project, so that the node
IDs of every graph model come from one shared sequence:

```sql
n AS (
    SELECT max(node_id) + 1 AS start_node_id
    FROM graphs.music_taste.msdsl_nodes_users
)
SELECT
    n.start_node_id + row_number() OVER () AS node_id,
    genre
FROM unique_genres, n
```

It works, but the ordering of `row_number() OVER ()` is not guaranteed, so IDs are
stable only as long as the model is not re-run. A sequence would express the intent
directly, and would let the database own the counter.

## Trying It Out

The project runs through `uv`, so nothing has to be activated in your shell:

```sh
# 1. Install dependencies
uv sync

# 2. Configure the environment
cp .env.example .env

# 3. Create the RustFS bucket and the PostgreSQL catalog database
uv run just init

# 4. Load the small Music Taste fixtures (no Kaggle account needed)
uv run just seed

# 5. Run the pipeline
uv run just graphrag-transform
uv run just graphrag-test
uv run just graphrag-export
```

The fixtures reproduce the exact shape of the real datasets with a handful of rows,
including one table large enough to be written as parquet files by DuckLake instead
of being inlined in the catalog, so the whole pipeline runs in seconds. The real
datasets are ingested the same way, they are just bigger:

```sh
just graphrag-ingest        # Deezer social networks + Million Song Dataset (Kaggle)
just econ-compnet-ingest    # The Atlas of Economic Complexity (DataCite/Dataverse)
just mlops-ingest           # Depression detection datasets (Hugging Face)
```

You can inspect the result with a plain DuckDB session, including the catalog's own
snapshot history:

```
just lakehouse

-- snapshot and version information; the changelog is the `changes` column of
-- snapshots(), which has no `snapshot_changes()` companion
SELECT * FROM graphs.current_snapshot();
SELECT * FROM graphs.snapshots() ORDER BY snapshot_id DESC LIMIT 10;
SELECT snapshot_id, e.key AS change, unnest(e.value) AS object
FROM (
    SELECT snapshot_id, unnest(map_entries(changes)) AS e
    FROM graphs.snapshots()
)
ORDER BY snapshot_id DESC
LIMIT 10;

-- table information, and where the catalog keeps its metadata and files
SELECT * FROM graphs.table_info();
SELECT * FROM graphs.settings();
SELECT * FROM graphs.options();
```

Two things are worth noticing in that output. First, the changelog is only
available as a column of `snapshots()`; there is no `snapshot_changes()` companion
in this DuckLake version. Second, each catalog has its own snapshot sequence, so
`stage` and `graphs` advance independently even though they share a metadata
database.

The test suite covers the storage layer (manifests, dated directories, exports
readable back from S3), the DuckLake catalog, the fixture shapes, and the SQLMesh
project (model names, kinds, audits, variable resolution). Tests that need RustFS
or PostgreSQL are skipped automatically when either is not reachable:

```sh
uv run just pytest
```
