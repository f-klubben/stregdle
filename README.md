# Stregsystemdle

The daily product-guessing game ("-dle") for the F-Klub stregsystem, running as
its own project.

It was originally an app inside the stregsystemet Django project. It now lives
here so it cannot bloat that project: there are no ORM models, no migrations and
no imports from `stregsystem`. Everything it knows about the shop comes from a
handful of read-only `SELECT`s against the stregsystem database.

## How it talks to the stregsystem

| Read from                     | What for                                        |
| ----------------------------- | ----------------------------------------------- |
| `stregsystem_product`         | id, name, price, alcohol, caffeine              |
| `stregsystem_category`        | category names (via `stregsystem_product_categories`) |
| `stregsystem_room`            | room names (via `stregsystem_product_rooms`)    |
| `stregsystem_namedproduct`    | short names ("alias") used by search            |
| `stregsystem_sale`            | sales of the last 90 days and in total          |

Those are Django's default table names for the stregsystem app, so they survive
as long as that project's models keep their names. The queries live in one
place: `productdle/repository.py`.

Run `python manage.py dbcheck` after deploying or after a schema change - it
executes the same queries and reports what came back.

### Use a read-only database user

The game only ever reads, so give it an account that can only read:

```sql
CREATE USER 'stregdle'@'%' IDENTIFIED BY '<password>';
GRANT SELECT ON stregsystem.* TO 'stregdle'@'%';
```

## Configuration

Everything is set through environment variables:

| Variable               | Default                        | Meaning                                          |
| ---------------------- | ------------------------------ | ------------------------------------------------ |
| `STREG_DB_HOST`        | `127.0.0.1`                    | MySQL/MariaDB host                               |
| `STREG_DB_PORT`        | `3306`                         | Port                                             |
| `STREG_DB_NAME`        | `stregsystem`                  | Database name                                    |
| `STREG_DB_USER`        | `stregdle`                     | Read-only user                                   |
| `STREG_DB_PASSWORD`    | (empty)                        | Password                                         |
| `STREGSYSTEM_URL`      | `http://localhost:8000/`       | Where the header's Menu/Genstart buttons point   |
| `STREGDLE_SECRET_KEY`  | dev key                        | Set a real one in production                     |
| `STREGDLE_ALLOWED_HOSTS` | `localhost,127.0.0.1`        | Comma-separated host names                       |
| `STREGDLE_HTTPS`       | (off)                          | `1` when served over HTTPS (enables redirect, HSTS and secure cookies) |
| `STREGDLE_HSTS_SECONDS` | `31536000` when HTTPS is on   | HSTS lifetime                                    |
| `STREGDLE_DEBUG`       | (off)                          | `1` for Django debug mode                        |

Product data is cached in-process for 60 seconds, so the shop's database is read
at most once a minute per worker regardless of how many people play.

## Running it

```sh
uv sync                                  # or: python -m venv .venv && pip install -e .
python manage.py dbcheck                 # verify the SQL against the database
python manage.py runserver               # development
python manage.py collectstatic --noinput # production: then serve staticfiles/
```

In production, run `stregdle.wsgi:application` behind gunicorn/uwsgi and let the
reverse proxy serve `/static/` from `staticfiles/`. Set `STREGDLE_HTTPS=1` and
`STREGDLE_SECRET_KEY` there, and make the proxy send `X-Forwarded-Proto`:

```sh
STREGDLE_HTTPS=1 STREGDLE_ALLOWED_HOSTS=stregdle.fklub.dk \
STREGDLE_SECRET_KEY=... python manage.py check --deploy
```

That check is clean with the production environment set; leave `STREGDLE_HTTPS`
off for local runs so plain HTTP works.

## The game rules

One product is the answer each day. The pick is deterministic per date (seeded
`stregdle-<date>`), the same seed the in-app version used, so moving the game
here did not change the answer of the day. Guesses are compared attribute by
attribute: price, alcohol, caffeine, sales and total are directional ("higher" /
"lower"), while a shared category or room counts as a match.

## Tests

```sh
python manage.py test
```

The game logic is tested against plain `Product` objects, so the suite needs no
database.

## Provenance

The game logic, page and stylesheet started life in the stregsystemet project
(`productdle/` there, which has been removed). `productdle/static/productdle/stregsystem.css`
is that project's `stregsystem.css`, copied verbatim so the page keeps the
stregsystem look; it is covered by the Limfjords-Porter-Ware licence.
