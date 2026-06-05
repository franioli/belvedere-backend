# Django Migration Status

## Goal
Migrate the existing project/database to a fully Django-managed application state.

This means:
- models are the authoritative schema definition
- schema changes happen through Django migrations
- production DB structure matches migrations
- legacy/manual drift is identified and eliminated carefully

## Known context
- Existing real database already exists
- Database has been migrated/imported into the new infrastructure
- PostgreSQL/PostGIS is available / required
- Project includes at least two apps:
  - `image_index`
  - `surveys`

## Migration checklist

### 1. Inventory current DB state
TODO / verify:
- list all current tables, views, sequences, constraints, indexes
- identify which belong to `image_index`
- identify which belong to `surveys`
- identify GIS/PostGIS-related tables/columns
- identify legacy/manual tables not yet represented in Django

### 2. Inventory Django model state
TODO / verify:
- ensure all important tables have Django models
- ensure models reflect current DB types, nullability, uniqueness, foreign keys, indexes
- ensure PostGIS/GIS fields are modeled correctly if used in `surveys` or related tables
- mark only truly external tables as unmanaged; target is to reduce unmanaged surface over time

### 3. Migration bootstrap strategy
TODO / verify:
- determine whether initial migrations already exist for both apps
- determine whether any migrations were generated after the DB already existed
- decide where `--fake-initial` is appropriate
- document any manual alignment steps needed before trusting migrations

### 4. Extension / database prerequisites
DONE / verify:
- PostGIS is required for this project context
TODO:
- verify required extensions exist in target DB (`postgis`, maybe others)
- ensure migrations do not assume extensions that are missing

### 5. Drift detection
TODO:
- compare actual DB schema against Django migration graph
- detect missing indexes/constraints/defaults
- detect columns existing in DB but missing from models
- detect model fields not present in DB
- detect mismatched field types

### 6. Ownership and operational cleanup
TODO:
- verify DB roles/ownership/grants are appropriate after migration
- verify app uses the intended DB role
- document which roles are still needed vs leftover legacy roles

### 7. Safe adoption plan
Recommended sequence:
1. inspect current migrations in both apps
2. inspect `showmigrations`
3. inspect actual DB schema
4. align models with reality
5. create missing migrations intentionally
6. apply using fake/fake-initial only where justified
7. test admin/API/commands against real data
8. only then continue new feature work

## Missing / likely incomplete items
Based on prior discussion, these areas still need explicit verification:
- full schema inventory for both `image_index` and `surveys`
- confirmation that both apps are fully covered by migrations
- confirmation that unmanaged/legacy tables have been accounted for
- final drift check between production DB and Django migrations
- extension verification for PostGIS and any GIS-specific model fields
- explicit documentation of what still remains manual vs Django-managed

## Definition of done
The migration is complete when:
- every intended app table is represented by Django models
- migrations exist and accurately describe schema state
- `showmigrations` reflects the intended applied graph
- no critical schema drift exists
- new schema changes can be done safely through Django only