# **Building a data lakehouse with DuckDB and DuckLake**

## Starting with a local Parquet file before joining it to data stored in Amazon S3

This article shows how to develop an effective data lake for free with DuckDB and the DuckLake extension (also free) for DuckDB. 

### A quick recap on Parquet format files, DuckDB and DuckLake

Data lakes of all types rely on Parquet files to store their underlying data. Parquet is a columnar file format designed for analytical data. It stores values from the same column together, which allows query engines to read only the columns needed by a query. Parquet files tend to be immutable and typically need additional metadata files to be useful in data lakes. The metadata records which Parquet files belong to a data table, their locations, partitions and statistics, as well as which files were added or removed during each table version. Additionally, all changes to the data made via SQL, like inserts, updates, deletes and schema changes, are also tracked. This metadata allows a lakehouse system to support efficient queries, transactions, schema evolution and time travel without modifying the underlying Parquet files directly.

I’ve written many times before about DuckDB. One of my favourite third-party Python libraries, it’s a super fast, in-memory analytical database suitable for small to medium databases (say up to a couple of hundred GBs of data).

DuckLake is an extension for DuckDB, developed by the team behind DuckDB and released just over a year ago. It stood the traditional idea of how a data lake file system should be structured on its head.

Several competing table formats are available for managing data in modern data lakes, including Delta Lake, Apache Iceberg, and Apache Hudi. As discussed, they store the underlying data in Parquet format files but differ in how they catalogue those files, record changes to them, and manage transactions. As mentioned previously, Delta, Iceberg and Hudi primarily record table state and change history in metadata files stored with, or close to, the Parquet data. DuckLake, however, stores that type of data in a relational database, and it doesn’t have to be DuckDB. Postgres, SQLite and MySQL are also supported.

DuckLake can ***store*** petabytes of data, but processing it is the bottleneck. Single-node DuckDB is well suited to selective queries that scan only a manageable portion of the lake, but workloads that repeatedly process tens or hundreds of terabytes will require a distributed query engine.

A few months ago, DuckDB released V1.0 of DuckLake, signalling it was ready for production use.

### What we’ll build

In this article, we’ll build an example data lake in two stages, beginning with a single **customer** Parquet file on our local computer and using it to explore the main features of DuckDB and DuckLake. Once the local lakehouse is working, we will add an **orders** Parquet file stored in Amazon S3 and join it to the local customer data.

Now, although the general idea behind data lakes is the storage and processing of large data volumes, the idea behind this particular article is to show the “how to” of building a data lake, so I’m not concerned with the data volumes and the files I’ll be using will be very small.

By the end, we will have demonstrated how to:

* Use DuckDB to query local and remote Parquet files  
* Create a DuckLake to store local data  
* Use DuckDB to query our DuckLake  
* Use SQL to update table data and evolve a table’s schema.  
* Use DuckLake snapshots to examine earlier versions.  
* Perform a join between a DuckLake table and an external S3 file.  
* Create a DuckLake table with our external S3 file data

### Prerequisites

You will need:

* Windows, macOS or a recent Linux distribution. I’m using Windows.  
* A terminal or PowerShell.  
* An internet connection to install the DuckDB CLI and its DuckLake extension.  
* An AWS account for the S3 part of the article.  
* Permission to create or use an S3 bucket.  
* The AWS CLI if you want to follow the command-line upload steps.

The example creates a very small S3 object, but AWS storage and request charges may still apply. Please delete it when you’re done to avoid any unwelcome bills. Note: if you don’t want to use the cloud for the second part of the data example, it’s fine to use local storage again.

### Create our project structure

Our folder structure for our project is going to look like this.

```text
ducklake-demo/
├── data/
│   ├── customers.parquet
│   ├── orders.parquet
│   ├── metadata.ducklake
│   └── lake/
└── duckdb.dev
```

The files have different purposes:

* customers.parquet is our original local source file.  
* orders.parquet is a staging file that we will (optionally) upload to S3.  
* metadata.ducklake contains the DuckLake catalogue.  
* lake/ contains Parquet files managed by DuckLake.  
* duckdb.dev holds the DuckDB session database.

On Windows PowerShell, run:

```powershell
New-Item -ItemType Directory -Force ducklake-demo
Set-Location ducklake-demo
```

on Linux, run:

```bash
mkdir -p ducklake-demo/data/lake
cd ducklake-demo
```

### Installing DuckDB

DuckDB is available as a command-line program for Windows. All methods to install DuckDB are documented at the [official DuckDB installation page](https://duckdb.org/install/). Choose your preference and follow the instructions.

For me, the simplest Windows installation uses winget.

```powershell
winget install DuckDB.cli
Found DuckDB CLI \[DuckDB.cli\] Version 1.5.5
This application is licensed to you by its owner.
Microsoft is not responsible for, nor does it grant any licenses to, third-party packages.
Downloading https://github.com/duckdb/duckdb/releases/download/v1.5.5/duckdb_cli-windows-amd64.zip
 ██████████████████████████████  12.3 MB / 12.3 MB
Successfully verified installer hash
Extracting archive...
Successfully extracted archive
Starting package install...
Path environment variable modified; restart your shell to use the new value.
Command line alias added: "duckdb"
Successfully installed
```

on Linux, run:

```bash
curl https://install.duckdb.org | bash
```

Verify the installation:

```bash
duckdb --version
v2.0.0 (Cyanoptera) d54cbbe3df
```


### Creating our DuckDB database and installing DuckLake

Start DuckDB and create a persistent working database:

```bash
duckdb duckdb.dev
```
You should now see the DuckDB prompt:

```text
duck D
```
DuckLake is distributed as a DuckDB extension. There is no separate desktop application or server to install.

From the DuckDB prompt, run:

```sql
INSTALL ducklake;

LOAD ducklake;
```

### Create the local “customers” Parquet file

We will begin with a small customer dataset. Enter the following statement in DuckDB:

```
duckdb duck.dev
DuckDB v2.0.0 (Cyanoptera)
Enter ".help" for usage hints.
duck D COPY (
          SELECT *
          FROM (
              VALUES
                  (1001, 'Acme Ltd',  'London'),
                  (1002, 'Northwind', 'Leeds'),
                  (1003, 'Globex',    'Glasgow'),
                  (1004, 'Initech',   'Manchester')
          ) AS customers(
              customer_id,
              customer_name,
              region
          )
      )
      TO 'data/customers.parquet'
      (FORMAT PARQUET);
duck D
```

This creates the file **data/customers.parquet**. At this point, the data exists as an ordinary file, not a DuckDB or DuckLake table.

### Query the Parquet file directly

DuckDB doesn’t require Parquet files to be imported to a data lake before they can be queried:

```
duck D SELECT *
      FROM read_parquet('data/customers.parquet');

┌─────────────┬───────────────┬────────────┐
│customer_id  │customer_name  │   region   │
│    int32    │    varchar    │  varchar   │
├─────────────┼───────────────┼────────────┤
│        1001 │ Acme Ltd      │ London     │
│        1002 │ Northwind     │ Leeds      │
│        1003 │ Globex        │ Glasgow    │
│        1004 │ Initech       │ Manchester │
└─────────────┴───────────────┴────────────┘
```

This is all fine, but it doesn’t turn the file into a transactional table. Parquet is an immutable file format from the point of view of normal SQL operations. We can’t treat our original file exactly like a database table and update one row in place, for example. The file would need to be replaced or rewritten. That’s where DuckLake comes into its own.

### Create the local DuckLake

Attach a new DuckLake catalogue:

```sql
ATTACH 'ducklake:data/metadata.ducklake' AS customer_lake (
   DATA_PATH 'data/lake/'
);
```

This statement identifies two storage locations:

```
data/metadata.ducklake    Metadata catalogue
data/lake/                Managed Parquet files
```

If the catalogue doesn’t already exist, DuckLake creates it. The data path is also recorded in the catalogue, so it doesn’t have to be supplied again when reconnecting later.

We can see the databases attached to the current DuckDB session with:

```sql
duck D show databases;

┌────────────────┐
│ database_name  │
│    varchar     │
├────────────────┤
│ customer_lake  │
│ duck           │
└────────────────┘
```

Now we can import our customers file into DuckLake to create a managed table.

```sql
duck D CREATE TABLE customer_lake.customers AS
SELECT *
FROM read_parquet('data/customers.parquet');
```


There are now two copies of the data.

1\) The original data/customers.parquet source file.  
2\) The managed DuckLake table stored under data/lake/.

The original file hasn’t been changed, and we can query the new table just like we would any other database table.

```
duck D SELECT *
      FROM customer_lake.customers;

┌─────────────┬───────────────┬────────────┐
│ customer_id │ customer_name │   region   │
│    int32    │    varchar    │  varchar   │
├─────────────┼───────────────┼────────────┤
│        1001 │ Acme Ltd      │ London     │
│        1002 │ Northwind     │ Leeds      │
│        1003 │ Globex        │ Glasgow    │
│        1004 │ Initech       │ Manchester │
└─────────────┴───────────────┴────────────┘
```

It looks the same as a regular table, and it behaves the same. The important differences are behind the scenes. For example, we can list the physical files used by the table:

```sql
duck D CALL ducklake_flush_inlined_data(
          'customer_lake',
          schema_name => 'main',
          table_name => 'customers'
      );

┌─────────────┬────────────┬──────────────┐
│ schema_name │ table_name │ rows_flushed │
│   varchar   │  varchar   │    int128    │
├─────────────┼────────────┼──────────────┤
│ main        │ customers  │            4 │
└─────────────┴────────────┴──────────────┘

duck D .mode line

duck D FROM ducklake_list_files(
          'customer_lake',
          'customers'
      );
                data_file = data/lake/main/customers/ducklake-019fdb4f-df34-7498-93c2-1f9a521b7c8b.parquet
     data_file_size_bytes = 943
    data_file_footer_size = 674
 data_file_encryption_key = NULL
              delete_file = NULL
   delete_file_size_bytes = NULL
delete_file_footer_size = NULL
delete_file_encryption_key = NULL
```

DuckLake maintains the relationship between the logical customers table and the Parquet files used to store it.

### Examining the DuckDB DuckLake metadata

Behind the scenes, DuckDB is squirrelling away metadata that tracks the status of our data lake. Here’s how you can access that data.

```sql
duck D DETACH customer_lake;

duck D

duck D ATTACH 'data/metadata.ducklake'
      AS customer_metadata (READ_ONLY);

duck D SELECT table_schema, table_name
      FROM information_schema.tables
      WHERE table_catalog = 'customer_metadata'
      ORDER BY table_schema, table_name;

┌──────────────┬───────────────────────────────────────┐
│ table_schema │              table_name               │
│   varchar    │                varchar                │
├──────────────┼───────────────────────────────────────┤
│ main         │ ducklake_column                       │
│ main         │ ducklake_column_mapping               │
│ main         │ ducklake_column_tag                   │
│ main         │ ducklake_data_file                    │
│ main         │ ducklake_delete_file                  │
│ main         │ ducklake_file_column_stats            │
│ main         │ ducklake_file_partition_value         │
│ main         │ ducklake_file_variant_stats           │
│ main         │ ducklake_files_scheduled_for_deletion │
│ main         │ ducklake_inlined_data_1_1             │
│ main         │ ducklake_inlined_data_1_2             │
│ main         │ ducklake_inlined_data_2_3             │
│ main         │ ducklake_inlined_data_3_5             │
│ main         │ ducklake_inlined_data_tables          │
│ main         │ ducklake_inlined_delete_1             │
│ main         │ ducklake_macro                        │
│ main         │ ducklake_macro_impl                   │
│ main         │ ducklake_macro_parameters             │
│ main         │ ducklake_metadata                     │
│ main         │ ducklake_name_mapping                 │
│ main         │ ducklake_partition_column             │
│ main         │ ducklake_partition_info               │
│ main         │ ducklake_schema                       │
│ main         │ ducklake_schema_versions              │
│ main         │ ducklake_snapshot                     │
│ main         │ ducklake_snapshot_changes             │
│ main         │ ducklake_sort_expression              │
│ main         │ ducklake_sort_info                    │
│ main         │ ducklake_table                        │
│ main         │ ducklake_table_column_stats           │
│ main         │ ducklake_table_stats                  │
│ main         │ ducklake_tag                          │
│ main         │ ducklake_view                         │
└──────────────┴───────────────────────────────────────┘

 33 rows                                    2 columns

```
Query any of the tables in column 2 above as you would a regular database table. e.g.

```
duck D select * from customer_metadata.ducklake_table_column_stats;

┌──────────┬───────────┬───────────────┬──────────────┬────────────┬────────────┬─────────────┐
│ table_id │ column_id │ contains_null │ contains_nan │ min_value  │ max_value  │ extra_stats │
│  int64   │   int64   │    boolean    │   boolean    │  varchar   │  varchar   │   varchar   │
├──────────┼───────────┼───────────────┼──────────────┼────────────┼────────────┼─────────────┤
│        1 │         1 │ false         │ NULL         │ 1001       │ 1004       │ NULL        │
│        1 │         2 │ false         │ NULL         │ Acme Ltd   │ Northwind  │ NULL        │
│        1 │         3 │ false         │ NULL         │ Glasgow    │ Yorkshire  │ NULL        │
└──────────┴───────────┴───────────────┴──────────────┴────────────┴────────────┴─────────────┘
```

When finished inspecting them, make sure you switch back your attachment:

```sql
DETACH customer_metadata;

ATTACH 'ducklake:data/metadata.ducklake'
AS customer_lake;
```

### Updating a DuckLake table

Suppose we want to replace London with Greater London in our customers table for customer 1001\. It’s just regular SQL.

```sql
duck D UPDATE customer_lake.customers
SET region = 'Greater London'
WHERE customer_id = 1001;

duck D SELECT *
      FROM customer_lake.customers
      WHERE customer_id = 1001;

customer_id  customer_name  region
-----------  -------------  --------------
1001         Acme Ltd       Greater London

```

The original source file has not been updated. We can demonstrate that by querying it again:

```sql
duck D SELECT *
      FROM read_parquet('data/customers.parquet')
      WHERE customer_id = 1001;

customer_id  customer_name  region
-----------  -------------  --------------
1001         Acme Ltd       London

```
That query still returns London.

DuckLake did not make the original file mutable. It created and now manages a separate representation of the table.

### Inspecting the snapshot history

Every committed change to a DuckLake database is associated with a snapshot. A snapshot is a point-in-time representation of the data lake, including its schemas, tables and underlying data files. Snapshots store metadata about each version rather than creating a complete copy of the data. We can list all the snapshots with this query:

```sql
duck D SELECT
          snapshot_id,
          snapshot_time,
          schema_version,
          changes,
          author,
          commit_message
      FROM customer_lake.snapshots()
      ORDER BY snapshot_id;

snapshot_id  snapshot_time                  schema_version  changes                                                author  commit_message
-----------  -----------------------------  --------------  -----------------------------------------------------  ------  --------------
0            2026-08-07 09:10:35.1368+01    0               {schemas_created=[main]}                               NULL    NULL
1            2026-08-07 09:13:56.142558+01  1               {tables_created=[main.customers], inlined_insert=[1]}  NULL    NULL
2            2026-08-07 09:21:12.625364+01  1               {flushed_inlined=[1]}                                  NULL    NULL
3            2026-08-07 09:24:15.991166+01  1               {inlined_insert=[1], inlined_delete=[1]}               NULL    NULL

```

You should see separate snapshots for operations such as creating tables, data inserts, deletes and updates. Note that an update is treated as a delete followed by an insert. The use of snapshots has one very useful side effect. It means we can go back in time and query table contents as they were at some point in the past as opposed to what they are right now.

### Time-travel queries

Let’s say we’ve forgotten what region was assigned to customer_id 1001 when it was first created. Looking at the above snapshot query we can glean that snapshot_id = 1 should give us that information, so we can use that identifier in the following query.

```sql
duck D SELECT *
      FROM customer_lake.customers
      AT (VERSION => 1)
      WHERE customer_id = 1001;

customer_id  customer_name  region
-----------  -------------  ------
1001         Acme Ltd       London
```


As well as using version numbers, DuckLake can also select a version by timestamp. For example,

```sql
duck D SELECT *
      FROM customer_lake.customers
      AT (
          TIMESTAMP => now() - INTERVAL '2 minutes'
      );

customer_id  customer_name  region
-----------  -------------  ------
1001         Acme Ltd       London
1002         Northwind      Leeds
1003         Globex         Glasgow
1004         Initech        Manchester

```

Whether this returns the earlier or current values for data depends on when you ran the update.

Snapshots can be a life-saver. Let’s say we inadvertantly delete our customer records with ids 1002 and 1004.


```sql
duck D delete from customer_lake.customers where customer_id in (1002,1004);

duck D select * from  customer_lake.customers;

customer_id  customer_name  region
-----------  -------------  ------
1003         Globex         Glasgow
1001         Acme Ltd       Greater London
```

We can get back the original deleted data if we go to a snaphot from before the original delete ws transacted.

```sql
duck D SELECT *
      FROM customer_lake.customers
      AT (VERSION => 1)
      WHERE customer_id in (1002,1004);

┌─────────────┬───────────────┬────────────┐
│ customer_id │ customer_name │   region   │
│    int32    │    varchar    │  varchar   │
├─────────────┼───────────────┼────────────┤
│        1002 │ Northwind     │ Leeds      │
│        1004 │ Initech       │ Manchester │
└─────────────┴───────────────┴────────────┘
```
Now, just re-insert this data into the original customers table and our data is recovered.

```sql
duck D insert into customer_lake.customers
      SELECT *
        FROM customer_lake.customers
        AT (VERSION => 1)
        WHERE customer_id in (1002,1004);

duck D select * from customer_lake.customers;

┌─────────────┬───────────────┬────────────────┐
│ customer_id │ customer_name │     region     │
│    int32    │    varchar    │    varchar     │
├─────────────┼───────────────┼────────────────┤
│        1003 │ Globex        │ Glasgow        │
│        1001 │ Acme Ltd      │ Greater London │
│        1002 │ Northwind     │ Leeds          │
│        1004 │ Initech       │ Manchester     │
└─────────────┴───────────────┴────────────────┘

```

### Adding commit messages

The previous update created a snapshot, but it didn’t explain why the change was made. DuckLake allows an author and commit message to be associated with a transaction.

Run another update inside an explicit transaction:

```sql
duck D begin;

duck D UPDATE customer_lake.customers
      SET region = 'Yorkshire'
      WHERE customer_id = 1002;

duck D CALL customer_lake.set_commit_message(
          'Article demonstration',
          'Updated region to Yorkshire for customer 1002'
      );

Success
-------

duck D commit;
```

Inspect the snapshots again:

```sql
duck D SELECT
          snapshot_id,
          snapshot_time,
          author,
          commit_message
      FROM customer_lake.snapshots()
      ORDER BY snapshot_id;

snapshot_id  snapshot_time                  author                 commit_message
-----------  -----------------------------  ---------------------  ---------------------------------------------
0            2026-08-07 09:10:35.1368+01    NULL                   NULL
1            2026-08-07 09:13:56.142558+01  NULL                   NULL
2            2026-08-07 09:21:12.625364+01  NULL                   NULL
3            2026-08-07 09:24:15.991166+01  NULL                   NULL
4            2026-08-07 09:42:10.67807+01   Article demonstration  Updated region to Yorkshire for customer 1002
duck D
```

The latest snapshot should now include the author and message.

DuckLake provides ACID transactions with snapshot isolation. A successful BEGIN–COMMIT block produces one snapshot containing all the changes in the transaction. If the transaction is rolled back, none of those changes becomes visible.

### Evolving a table schema

We can also alter the table without rewriting our original source file. DuckLake uses field identifiers to track columns and supports compatible schema changes without requiring every existing Parquet file to be rewritten. Let’s say we want to add a new column called customer_status.

```sql
duck D ALTER TABLE customer_lake.customers
      ADD COLUMN customer_status VARCHAR DEFAULT 'active';
```

Inspect the new schema:

```sql
duck D DESCRIBE customer_lake.customers;

column_name      column_type  null  key   default   extra
---------------  -----------  ----  ----  --------  -----
customer_id      INTEGER      YES   NULL  NULL      NULL
customer_name    VARCHAR      YES   NULL  NULL      NULL
region           VARCHAR      YES   NULL  NULL      NULL
customer_status  VARCHAR      YES   NULL  'active'  NULL
```

Query the table:

```sql
duck D SELECT *
      FROM customer_lake.customers;

customer_id  customer_name  region          customer_status
-----------  -------------  --------------  ---------------
1003         Globex         Glasgow         active
1004         Initech        Manchester      active
1001         Acme Ltd       Greater London  active
1002         Northwind      Yorkshire       active
```

Every existing row should have a customer_status of active.

At this point, we have demonstrated the principal DuckLake features locally:

* Managed Parquet storage.  
* SQL queries.  
* Updates.  
* Transactions.  
* Commit information.  
* Snapshots.  
* Time travel.  
* Schema evolution.

### Dealing with cloud based data files

Not all data you work with will be local, in fact for data lakes the opposite is usually true. Most of the data in enterprise data lakes will be held in one form of cloud storage. So that’s what we’ll look at next.

Our customer reference data is managed by DuckLake on the local computer. We will assume that **order** data is produced by another system and delivered to Amazon S3.

The S3 file will contain:

```txt
order_id | customer_id | order_date | quantity | unit_price
---------+-------------+------------+----------+-----------
5001     | 1001        | 2026-07-01 | 4        | 29.50
5002     | 1002        | 2026-07-02 | 2        | 74.00
5003     | 1001        | 2026-07-03 | 5        | 19.99
5004     | 1004        | 2026-07-04 | 3        | 44.50
5005     | 1003        | 2026-07-05 | 1        | 125.00
```

We will create the file locally, upload it and then query the S3 version. You’ll need the AWS CLI tool for this so make sure you’ve installed that if you’re following along.

### Create the orders Parquet file

Return to the DuckDB session. If you closed it, reopen the database from the project directory, re-attach the DuckLake and run this command from the DuckDB CLI

```sql
duck D COPY (
   SELECT *
   FROM (
       VALUES
           (5001, 1001, DATE '2026-07-01', 4,  29.50),
           (5002, 1002, DATE '2026-07-02', 2,  74.00),
           (5003, 1001, DATE '2026-07-03', 5,  19.99),
           (5004, 1004, DATE '2026-07-04', 3,  44.50),
           (5005, 1003, DATE '2026-07-05', 1, 125.00)
   ) AS orders(
       order_id,
       customer_id,
       order_date,
       quantity,
       unit_price
   )
)
TO 'data/orders.parquet'
(FORMAT PARQUET);

```
Check the file data:

```sql
duck D SELECT *
FROM read_parquet('data/orders.parquet');

order_id  customer_id  order_date  quantity  unit_price
--------  -----------  ----------  --------  ----------
5001      1001         2026-07-01  4         29.50
5002      1002         2026-07-02  2         74.00
5003      1001         2026-07-03  5         19.99
5004      1004         2026-07-04  3         44.50
5005      1003         2026-07-05  1         125.00
```

Install AWS cli and configure your credentials.
```bash
sudo pacman -S aws-cli-v2
aws configure
```

for Ubuntu:
```bash
sudo apt-get update
sudo apt-get install awscli
aws configure
```

for Fedora:
```bash
sudo dnf update
sudo dnf install awscli
aws configure
```

for openSUSE:
```bash
sudo zypper update
sudo zypper install awscli
aws configure
```

The file has been created locally, we just need to upload it to a suitable bucket on S3. Open another terminal in the project directory and run:

```bash
/home/users/codebase/ducklake-demo/data\> cd /home/users/codebase/ducklake-demo
/home/users/codebase/ducklake-demo\> aws s3 cp data/orders.parquet s3://my-bucket/source/orders.parquet

upload: data/orders.parquet to s3://my-bucket/source/orders.parquet
```

Note, I've changed my bucket name in the above command for security and privacy reasons.

For DuckDB to read data on S3 we need to install another couple of extensions. Return to the DuckDB prompt and run:


```
duck D INSTALL httpfs;
duck D LOAD httpfs;
```

Next, create a temporary DuckDB secret. I’m using my default AWS profile that contains my credentials to connect to AWS. Choose whichever region you want. I’m using eu-west-2.

```sql
duck D CREATE OR REPLACE SECRET s3_credentials (
          TYPE s3,
          PROVIDER credential_chain,
          CHAIN 'config',
          REGION 'eu-north-1'
      );

Success
-------

true

```

This secret exists for the current DuckDB session. It contains the credentials resolved by the AWS SDK rather than exposing them in the SQL statement.

Now we should be able to query the remote Parquet file

```sql
duck D SELECT *
      FROM read_parquet(
          's3://my-bucket/source/orders.parquet'
      );

order_id  customer_id  order_date  quantity  unit_price
--------  -----------  ----------  --------  ----------
5001      1001         2026-07-01  4         29.50
5002      1002         2026-07-02  2         74.00
5003      1001         2026-07-03  5         19.99
5004      1004         2026-07-04  3         44.50
5005      1003         2026-07-05  1         125.00

duck D
```

### Using the S3 data with our DuckLake

At this stage we have two main options for joining our remote data to our existing DuckLake.

1/ We can keep the DuckLake data and S3 data separate and just join them using SQL like this.

```sql
duck D SELECT
          o.*,
          c.*
      FROM read_parquet(
          's3://my-bucket/source/orders.parquet'
      ) AS o
      LEFT JOIN customer_lake.main.customers AS c
          ON o.customer_id = c.customer_id;

order_id  customer_id  order_date  quantity  unit_price  customer_id  customer_name  region          customer_status
--------  -----------  ----------  --------  ----------  -----------  -------------  --------------  ---------------
5005      1003         2026-07-05  1         125.00      1003         Globex         Glasgow         active
5004      1004         2026-07-04  3         44.50       1004         Initech        Manchester      active
5003      1001         2026-07-03  5         19.99       1001         Acme Ltd       Greater London  active
5002      1002         2026-07-02  2         74.00       1002         Northwind      Yorkshire       active
5001      1001         2026-07-01  4         29.50       1001         Acme Ltd       Greater London  active
```

2/ We can add the S3 data file to our existing DuckLake and subsequent changes to the orders DuckLake table would be tracked locally, just like what happens with the local customers data.

```sql
duck D CREATE TABLE customer_lake.orders AS
      SELECT *
      FROM read_parquet('s3://my-bucket/source/orders.parquet');

duck D SELECT
          o.order_id,
          c.customer_id
      FROM customer_lake.orders AS o
      LEFT JOIN customer_lake.customers AS c
          ON o.customer_id = c.customer_id;

order_id  customer_id
--------  -----------
5003      1001
5002      1002
5001      1001
5005      1003
5004      1004
```

### Summary

We covered a lot in this article but you should now have a deeper understanding of data lakes in general and how DuckLake is different from technologies you may have heard about before, like Iceberg, Delta and Hudi.

We began with one local Parquet file and queried it directly using DuckDB. That required no database server and no ingestion process.

We then imported the data into DuckLake. The managed table could be updated with SQL, modified inside transactions and queried at earlier snapshots. We also changed its schema without altering the original source file.

Only after establishing those local features did we add remote data. DuckDB read an orders file on AWS S3, joined it to the local DuckLake table and materialised the result as another managed DuckLake table.

The example shows the boundary between the two tools. DuckDB is the engine that reads files and executes SQL. DuckLake provides the catalogue and transaction model that turns Parquet files into maintained lakehouse tables.

One important question you might have is: Why use DuckLake at all over the established players in data lake technologies?

The answer comes down to fit. If your data processing requirements are not too onerous and DuckDB is already at the centre of your analytics stack, DuckLake provides transactions, snapshots and schema evolution over Parquet through a familiar SQL catalogue. For teams that value a lightweight, SQL-native lakehouse, using DuckLake could be a no-brainer.

If you’re running an enterprise grade data lake then, sure, proprietary and open-source table formats (Iceberg, Delta etc…) provided by companies like Snowflake, DataBricks and others like them are obvious choices. Those are expensive options though.

A system set up around DuckDB and DuckLake can be done for almost zero cost. If it doesn’t scale, throw it away. All you lost is a bit of of your time.
